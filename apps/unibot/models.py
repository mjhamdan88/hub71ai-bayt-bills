from django.db import models, transaction
import os
from django.conf import settings
from unicom.models import RequestCategory, Message, Account
from unibot.services.llm_handler import run_llm_handler
from typing import Callable, Dict, List, Optional, Type
import types
import traceback
from openai import OpenAI
import reversion
from django.utils import timezone
from datetime import timedelta
from unibot.services.tool_exceptions import ToolHandlerError, ToolHandlerWarning
from cryptography.fernet import Fernet
import base64
import uuid
import json
from django.core.validators import RegexValidator, EmailValidator
from django.core.exceptions import ValidationError
import logging


def _request_was_superseded(request):
    initial_request = request.initial_request or request
    return initial_request.message.chat.messages.filter(
        is_outgoing=False,
        timestamp__gt=initial_request.message.timestamp,
    ).exclude(media_type__in=['tool_call', 'tool_response']).exists()

# Create your models here.

def get_encryption_key():
    """Get or create the encryption key from Django settings"""
    key = getattr(settings, 'CREDENTIAL_ENCRYPTION_KEY', None)
    if key is None:
        # Generate a new key if none exists
        key = Fernet.generate_key().decode()
        logging.warning(f"[DEBUG] Generated fallback key: {repr(key)} (length: {len(key)})")
    # Do NOT decode here! Fernet expects the base64 string.
    return key

class CredentialFieldType(models.TextChoices):
    TEXT = 'text', 'Text'
    EMAIL = 'email', 'Email'
    NUMBER = 'number', 'Number'
    PHONE = 'phone', 'Phone Number'
    PASSWORD = 'password', 'Password'
    PIN = 'pin', 'PIN'

@reversion.register()
class CredentialFieldDefinition(models.Model):
    """Defines the structure and validation rules for a credential field"""
    key = models.CharField(
        max_length=255,
        unique=True,
        help_text="Globally unique identifier for this credential (e.g., 'GOOGLE_PLACES_API_KEY', 'STRIPE_SECRET_KEY_LIVE')"
    )
    field_type = models.CharField(
        max_length=20,
        choices=CredentialFieldType.choices,
        default=CredentialFieldType.TEXT
    )
    label = models.CharField(max_length=255)
    help_text = models.TextField(blank=True)
    placeholder = models.CharField(max_length=255, blank=True)
    regex_pattern = models.CharField(
        max_length=255, 
        blank=True,
        help_text="Optional regex pattern for validation"
    )
    min_length = models.IntegerField(null=True, blank=True)
    max_length = models.IntegerField(null=True, blank=True)
    required = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.label} ({self.key})"

    @classmethod
    def get_available_fields_info(cls) -> str:
        """Returns a human-readable list of available credential fields"""
        fields = cls.objects.all().order_by('order', 'key')
        if not fields:
            return "No credential fields defined yet."
        
        field_descriptions = []
        for field in fields:
            constraints = []
            if field.min_length:
                constraints.append(f"min={field.min_length}")
            if field.max_length:
                constraints.append(f"max={field.max_length}")
            if field.regex_pattern:
                constraints.append("has pattern")
            
            constraints_str = f" ({', '.join(constraints)})" if constraints else ""
            field_descriptions.append(
                f"- {field.key}: {field.field_type}{constraints_str}"
            )
        
        return "Available credential fields:\n" + "\n".join(field_descriptions)

    def clean(self):
        super().clean()
        # Validate regex pattern if provided
        if self.regex_pattern:
            try:
                import re
                re.compile(self.regex_pattern)
            except re.error:
                raise ValidationError({'regex_pattern': 'Invalid regular expression pattern'})
        
        # Enforce key naming convention
        if not self.key.isupper() or '_' not in self.key or len(self.key) < 12:
            raise ValidationError({
                'key': 'Key must be uppercase, contain underscores, and be at least 12 characters long (e.g., GOOGLE_PLACES_API_KEY)'
            })

    def validate_value(self, value: str) -> tuple[bool, Optional[str]]:
        """Validate a value against this field's rules"""
        if not value and self.required:
            return False, "This field is required"

        if value:
            if self.min_length and len(value) < self.min_length:
                return False, f"Minimum length is {self.min_length} characters"
            
            if self.max_length and len(value) > self.max_length:
                return False, f"Maximum length is {self.max_length} characters"

            if self.regex_pattern:
                import re
                if not re.match(self.regex_pattern, value):
                    return False, "Value does not match the required pattern"

            if self.field_type == CredentialFieldType.EMAIL:
                try:
                    EmailValidator()(value)
                except ValidationError:
                    return False, "Enter a valid email address"

            elif self.field_type == CredentialFieldType.NUMBER:
                try:
                    float(value)
                except ValueError:
                    return False, "Enter a valid number"

            elif self.field_type == CredentialFieldType.PHONE:
                # Basic phone validation - can be enhanced based on requirements
                if not re.match(r'^\+?[\d\s-]+$', value):
                    return False, "Enter a valid phone number"

            elif self.field_type == CredentialFieldType.PIN:
                if not value.isdigit():
                    return False, "PIN must contain only digits"

        return True, None

    class Meta:
        ordering = ['order', 'key']

@reversion.register()
class CredentialSetupSession(models.Model):
    """Manages a time-limited session for setting multiple credentials"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    field_definitions = models.ManyToManyField(CredentialFieldDefinition)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    max_attempts = models.IntegerField(default=3)
    attempts = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    @property
    def can_attempt(self) -> bool:
        return not self.is_expired and not self.is_completed and self.attempts < self.max_attempts

    def mark_completed(self):
        self.completed_at = timezone.now()
        self.save(update_fields=['completed_at'])

    def increment_attempts(self):
        self.attempts += 1
        self.save(update_fields=['attempts'])

    @classmethod
    def create_session(
        cls,
        account: Account,
        field_definitions: List[CredentialFieldDefinition],
        expires_in_minutes: int = 30,
        max_attempts: int = 3,
        metadata: Optional[Dict] = None
    ) -> 'CredentialSetupSession':
        """Create a new credential setup session"""
        session = cls.objects.create(
            account=account,
            expires_at=timezone.now() + timedelta(minutes=expires_in_minutes),
            max_attempts=max_attempts,
            metadata=metadata or {}
        )
        session.field_definitions.set(field_definitions)
        return session

    def __str__(self):
        return f"Credential Setup for {self.account} ({self.id})"

@reversion.register()
class EncryptedCredential(models.Model):
    """Model for storing encrypted key-value pairs"""
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='credentials')
    key = models.CharField(max_length=255)
    value = models.BinaryField(editable=False)  # Stores the encrypted value
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['account', 'key']
        indexes = [
            models.Index(fields=['account', 'key']),
        ]

    def __str__(self):
        return f"{self.account} - {self.key}"

    @property
    def decrypted_value(self) -> Optional[str]:
        """Get the decrypted value"""
        if not self.value:
            return None
        f = Fernet(get_encryption_key())
        if isinstance(self.value, memoryview):
            decrypted = f.decrypt(self.value.tobytes())
        else:
            decrypted = f.decrypt(self.value)
        return decrypted.decode()


    def save(self, *args, **kwargs):
        if hasattr(self, '_value'):
            # Encrypt the value before saving
            f = Fernet(get_encryption_key())
            self.value = f.encrypt(self._value.encode())
            del self._value
        super().save(*args, **kwargs)

@reversion.register()
class Tool(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # Store the implementation code, which must define a `tool_definition` dict
    code = models.TextField(
        blank=True,
        help_text="Python implementation including a top-level `tool_definition` dict"
    )

    def __str__(self):
        return self.name

    @property
    def info(self) -> str:
        """Returns structured information about the tool"""
        return (
            f"Tool ID: {self.id}\n"
            f"Name: {self.name}\n"
            f"Code: \n{self.code}\n"
        )

    def get_definition(self, bot=None, message=None, openai_client=None, request=None, tool_call=None):
        """
        Execute the tool's code in isolation and return its `tool_definition` dict.
        Injects bot, message, request, tool_call, and openai_client into the tool's global context if provided.

        Available globals in tool code:
        - bot: The Bot instance processing this request
        - message: The Message object being processed
        - account: The Account/user from the request (request.account, fallback to message.sender)
        - request: The Request object containing status, category, etc.
        - member: The Member object if available (request.member)
        - tool_call: The ToolCall instance for this tool execution (available during execution)
        - openai_client: OpenAI client instance
        """
        # Use request.account (correctly propagated for child requests) instead of message.sender
        if request is not None and hasattr(request, 'account') and request.account is not None:
            account = request.account
        elif message is not None:
            account = message.sender
        else:
            account = None
        module = types.ModuleType('tool_module')
        # Inject globals if provided
        if bot is not None:
            module.__dict__["bot"] = bot
        if message is not None:
            module.__dict__["message"] = message
        if account is not None:
            module.__dict__["account"] = account
        if request is not None:
            module.__dict__["request"] = request
            # Also inject member if available
            if hasattr(request, 'member') and request.member is not None:
                module.__dict__["member"] = request.member
        if tool_call is not None:
            module.__dict__["tool_call"] = tool_call
        if openai_client is not None:
            module.__dict__["openai_client"] = openai_client
        # Provide ToolHandlerError so tools can signal handled failures
        module.__dict__["ToolHandlerError"] = ToolHandlerError
        module.__dict__["ToolHandlerWarning"] = ToolHandlerWarning
        exec(self.code, module.__dict__)
        return getattr(module, 'tool_definition', None)

    @staticmethod
    def get_default_code():
        template_path = os.path.join(settings.BASE_DIR, 'unibot', 'templates', 'unibot', 'default_tool.py')
        with open(template_path, 'r') as f:
            return f.read()

    @classmethod
    def get_template_readme(cls) -> str:
        """Returns the contents of TOOL_TEMPLATES_README.md"""
        readme_path = os.path.join(settings.BASE_DIR, 'unibot', 'templates', 'unibot', 'TOOL_TEMPLATES_README.md')
        try:
            with open(readme_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return "Tool template documentation not found."

@reversion.register()
class Bot(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255)
    code = models.TextField()
    request_category = models.OneToOneField(RequestCategory, on_delete=models.CASCADE, null=True, blank=True)
    # New many-to-many relationship to attach tools
    tools = models.ManyToManyField(Tool, blank=True, related_name='bots')

    def __str__(self):
        return self.name

    @property
    def info(self) -> str:
        """Returns structured information about the bot"""
        # Get tools info
        tools_info = ", ".join([f"{tool.name} (ID: {tool.id})" for tool in self.tools.all()])
        
        # Get recent error if any
        recent_error = ""
        if self.request_category:
            # Assuming Request model has status, created_at, and error fields
            twelve_hours_ago = timezone.now() - timedelta(hours=24)
            recent_failed_request = (
                self.request_category.request_set
                .filter(status='FAILED', created_at__gte=twelve_hours_ago)
                .order_by('-created_at')
                .first()
            )
            if recent_failed_request:
                recent_error = f"\nLast Recent Error: {recent_failed_request.error}"

        return (
            f"Bot ID: {self.id}\n"
            f"Name: {self.name}\n"
            + (f"Tools: {tools_info}\n" if tools_info else "")
            + f"Code: \n{self.code}\n"
            + (f"Recent Error: {recent_error}\n" if recent_error else "")
        )

    @classmethod
    def get_template_readme(cls) -> str:
        """Returns the contents of BOT_TEMPLATES_README.md"""
        readme_path = os.path.join(settings.BASE_DIR, 'unibot', 'templates', 'unibot', 'BOT_TEMPLATES_README.md')
        try:
            with open(readme_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            return "Bot template documentation not found."

    @staticmethod
    def get_default_code():
        template_path = os.path.join(settings.BASE_DIR, 'unibot', 'templates', 'unibot', 'default_bot.py')
        with open(template_path, 'r') as f:
            return f.read()

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.request_category:
            rc = RequestCategory.objects.create(
                name=self.category,
                sequence=1000 + self.id
            )
            self.request_category = rc
            super().save(update_fields=['request_category'])

    def delete(self, *args, **kwargs):
        rc = self.request_category
        super().delete(*args, **kwargs)
        if rc:
            rc.delete()

    def reply_using_llm(
        self,
        message: Message,
        tools_list: List[Tool],
        model_audio: str = "gpt-4o-audio-preview",
        model_default: str = "o4-mini-2025-04-16",
        system_instruction: Optional[str] = None,
        depth: int = 129,
        mode: str = "thread",
        max_function_calls: int = 7,
        openai_client: OpenAI = None,
        request=None,
        api_mode: str = "chat_completions",
        stream: bool = False,
        stream_event_sink=None,
        native_responses_tools: Optional[List[dict]] = None,
    ):
        if openai_client is None:
            openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return run_llm_handler(
            self,
            message,
            tools_list,
            model_audio=model_audio,
            model_default=model_default,
            system_instruction=system_instruction,
            max_function_calls=max_function_calls,
            as_llm_chat_params={
                "depth": depth,
                "mode": mode,
            },
            debug=True,
            openai_client=openai_client,
            request=request,
            api_mode=api_mode,
            stream=stream,
            stream_event_sink=stream_event_sink,
            native_responses_tools=native_responses_tools,
        )

    def process_request(self, req):
        """
        Process a single Request object using this bot's code, updating status and error fields as needed.
        Passes the bot instance and its associated tools to the handler.
        """
        from unicom.models import ToolCall
        from unibot.services.request_retries import schedule_retry

        req.last_attempt_at = timezone.now()
        req.save(update_fields=['last_attempt_at'])

        # New user input always wins over unfinished work in the same chat.
        if req.message.is_outgoing is False and req.message.media_type not in ['tool_call', 'tool_response']:
            with transaction.atomic():
                interrupted = ToolCall.objects.select_for_update().filter(
                    tool_call_message__chat=req.message.chat,
                    tool_call_message__timestamp__lt=req.message.timestamp,
                    status__in=['PENDING', 'IN_PROGRESS', 'ACTIVE'],
                )
                ToolCall.interrupt_unresolved(interrupted)
                type(req).objects.filter(
                    message__chat=req.message.chat,
                    message__timestamp__lt=req.message.timestamp,
                    parent_request__isnull=False,
                    status__in=[
                        'PENDING', 'IDENTIFYING', 'CATEGORIZING',
                        'CATEGORY_LIST_SENT', 'QUEUED',
                    ],
                ).update(status='COMPLETED')
        elif req.parent_request and _request_was_superseded(req):
            req.status = 'COMPLETED'
            req.save(update_fields=['status'])
            return True

        if hasattr(req, 'parent_request') and req.parent_request:
            print(f"[DEBUG] Processing child request {req.id} from parent {req.parent_request.id}")
        bot_code = self.code or Bot.get_default_code()
        module = types.ModuleType('bot_code')
        openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        module.__dict__.update({
            "openai_client": openai_client,
            "bot": self,
            "message": req.message,
            "account": req.account,  # Use req.account (correctly propagated) instead of req.message.sender
            "request": req
        })
        # Also add member if available
        if hasattr(req, 'member') and req.member is not None:
            module.__dict__["member"] = req.member
        tools_list = list(self.tools.all())
        try:
            exec(bot_code, module.__dict__)
            handler = getattr(module, 'handle_incoming_message', None)
            if not handler:
                # Use default handler from default_bot.py
                default_code = Bot.get_default_code()
                exec(default_code, module.__dict__)
                handler = getattr(module, 'handle_incoming_message', None)
            if not handler:
                req.status = 'FAILED'
                req.error = f'No handle_incoming_message function defined for bot {self.id}'
                req.save(update_fields=['status', 'error'])
                return False
            # Pass message, bot instance, and tools list
            handler(req.message, self, tools_list)
            req.status = 'COMPLETED'
            req.error = None
            req.failure_kind = ''
            req.next_retry_at = None
            req.retry_exhausted_at = None
            req.save(update_fields=[
                'status', 'error', 'failure_kind', 'next_retry_at',
                'retry_exhausted_at',
            ])
            return True
        except Exception as e:
            req.status = 'FAILED'
            req.error = traceback.format_exc()
            schedule_retry(req, e)
            req.save(update_fields=[
                'status', 'error', 'failure_kind', 'next_retry_at',
                'retry_exhausted_at',
            ])
            return False
