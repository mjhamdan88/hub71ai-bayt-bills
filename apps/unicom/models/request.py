from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Q
import uuid


class Request(models.Model):
    """
    Model for incoming message tasks with categorization and metadata.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IDENTIFYING', 'Identifying'),
        ('CATEGORIZING', 'Categorizing'),
        ('CATEGORY_LIST_SENT', 'Category List Sent'),
        ('QUEUED', 'Queued'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey('unicom.Message', on_delete=models.CASCADE)
    display_text = models.TextField(
        help_text="Display version of the message text",
        null=True,
        blank=True
    )
    account = models.ForeignKey('unicom.Account', on_delete=models.CASCADE)
    channel = models.ForeignKey(
        'unicom.Channel',
        on_delete=models.CASCADE,
        help_text="Channel where this request originated"
    )
    member = models.ForeignKey(
        'unicom.Member',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True
    )
    
    # Contact information that might help identify the member
    email = models.EmailField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Email address extracted from the Account"
    )
    phone = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        help_text="Phone number extracted from the Account"
    )
    
    category = models.ForeignKey(
        'unicom.RequestCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        help_text="Current category of the request"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
        db_index=True
    )
    error = models.TextField(
        null=True,
        blank=True,
        help_text="Detailed error message when request fails"
    )
    retry_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of automatic retries already claimed for this request",
    )
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_retried_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Earliest time a worker may atomically retry a transient failure",
    )
    failure_kind = models.CharField(
        max_length=32,
        blank=True,
        help_text="Machine-readable classification of the most recent failure",
    )
    retry_exhausted_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict)
    
    # Hierarchy and LLM tracking fields
    parent_request = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='child_requests',
        help_text="Parent request that spawned this request"
    )
    initial_request = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='descendant_requests',
        help_text="Root request that started this chain"
    )
    tool_call_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of tool calls made from this request"
    )
    llm_calls_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of LLM calls made for this request"
    )
    llm_token_usage = models.PositiveIntegerField(
        default=0,
        help_text="Total tokens used by LLM for this request"
    )
    
    # Timestamps for request lifecycle
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    pending_at = models.DateTimeField(auto_now_add=True)
    identifying_at = models.DateTimeField(null=True, blank=True)
    categorizing_at = models.DateTimeField(null=True, blank=True)
    queued_at = models.DateTimeField(null=True, blank=True)
    processing_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            # Compound index for contact fields
            models.Index(fields=['email', 'phone'], name='request_contact_idx'),
            # Index for status with timestamps for filtering requests in specific states
            models.Index(fields=['status', 'created_at'], name='request_status_created_idx'),
            models.Index(fields=['status', 'completed_at'], name='request_status_completed_idx'),
            # Index for category lookups with status
            models.Index(fields=['category', 'status'], name='request_category_status_idx'),
            # Index for channel-based lookups
            models.Index(fields=['channel', 'status'], name='request_channel_status_idx'),
        ]
        ordering = ['-created_at']  # Most recent first

    def __str__(self):
        text = self.display_text or self.message.text
        preview = text[:50] + "..." if len(text) > 50 else text
        category_name = self.category.name if self.category else "Uncategorized"
        member_name = self.member.name if self.member else "No Member"
        return f"{preview} ({category_name} - {member_name})"

    def save(self, *args, **kwargs):
        # Set channel from message if not set
        if not self.channel and self.message:
            self.channel = self.message.channel

        # Update status timestamps
        if not self.pk:  # New instance
            self.pending_at = timezone.now()
        else:
            try:
                old_instance = type(self).objects.get(pk=self.pk)
                if old_instance.status != self.status:
                    timestamp_field = f"{self.status.lower()}_at"
                    if hasattr(self, timestamp_field):
                        setattr(self, timestamp_field, timezone.now())
            except type(self).DoesNotExist:
                # This is a new instance but with a predefined pk
                self.pending_at = timezone.now()
        
        super().save(*args, **kwargs)

    def get_available_categories(self, parent=None):
        """
        Get categories available to this request at the specified level,
        taking into account permissions and channel restrictions.
        """
        from .request_category import RequestCategory

        # Base query for active categories at this level
        categories = RequestCategory.objects.filter(
            parent=parent,
            is_active=True
        )

        # Filter by channel if category specifies allowed channels
        channel_categories = categories.filter(
            Q(allowed_channels=self.channel) | Q(allowed_channels__isnull=True)
        )

        # Filter by permissions
        if self.member:
            # Get categories the member has access to through:
            # 1. Public categories
            # 2. Direct member authorization (allowed_categories M2M from Member)
            # 3. Direct member authorization (authorized_members M2M from Category)
            # 4. Group membership
            member_categories = channel_categories.filter(
                Q(is_public=True) |  # Public access
                Q(members_with_access=self.member) |  # Via Member.allowed_categories
                Q(authorized_members=self.member) |  # Via Category.authorized_members
                Q(authorized_groups__members=self.member)  # Group-based access
            )
            return member_categories.distinct().order_by('sequence')
        else:
            # Only public categories for non-members
            return channel_categories.filter(is_public=True).order_by('sequence')

    def identify_member(self):
        """
        Identify and link member if not already set.
        Tries multiple methods:
        1. Check if member is already set
        2. Check if account has a member
        3. Look for member with matching email
        4. Look for member with matching phone
        """
        try:
            # Skip if member is already set
            if self.member:
                return True

            # Skip if account doesn't exist
            if not self.account:
                self.error = "No account associated with request"
                self.save(update_fields=['error'])
                return False

            # If account already has a member, use that
            if self.account.member:
                self.member = self.account.member
                self.save()
                return True

            # Try to find member by contact information
            from .member import Member
            matching_member = None

            # Build query for contact matching
            contact_query = Q()
            if self.email:
                contact_query |= Q(email=self.email)
            if self.phone:
                contact_query |= Q(phone=self.phone)

            if contact_query:
                try:
                    matching_member = Member.objects.filter(contact_query).first()
                except Member.MultipleObjectsReturned:
                    self.error = "Multiple members found with matching contact info"
                    self.metadata['member_identification'] = {
                        'error': self.error,
                        'email': self.email,
                        'phone': self.phone
                    }
                    self.save()
                    return False

            if matching_member:
                self.member = matching_member
                self.metadata['member_identification'] = {
                    'method': 'contact_match',
                    'matched_by': 'email' if self.email and self.email == matching_member.email else 'phone'
                }
                self.save()
                
                # Also update the account if found by contact info
                if self.account and not self.account.member:
                    self.account.member = matching_member
                    self.account.save()
                
                return True

            # No member found but this is not an error condition
            self.metadata['member_identification'] = {
                'result': 'no_match',
                'email': self.email,
                'phone': self.phone
            }
            self.save()
            return False

        except Exception as e:
            self.error = f"Error during member identification: {str(e)}"
            self.save(update_fields=['error'])
            return False

    def categorize(self):
        """
        Attempt to categorize the request by running through category functions.
        Updates status based on results.
        """
        print(f"\nStarting categorization for request {self.id}")
        self.status = 'CATEGORIZING'
        self.error = None  # Clear any previous errors
        self.save()

        try:
            # Get top level categories (no parent)
            top_level_categories = self.get_available_categories(parent=None)
            multiple_categories = top_level_categories.count() > 1

            if multiple_categories:
                # Check for explicit category selection in message text
                message_text = self.message.text.lower()
                
                # Check for list-categories or category-menu request
                if 'list-categories' in message_text or 'category-menu' in message_text:
                    self._send_category_list()
                    return True

                # Convert categories to list for indexed access
                categories_list = list(top_level_categories)
                
                # Check for explicit category selection by number
                for i, category in enumerate(categories_list, 1):
                    # Look for number-request pattern (e.g., "1-request", "category 1 request", etc.)
                    if f"{i}-request" in message_text or f"category {i} request" in message_text:
                        self.category = category
                        self.status = 'QUEUED'
                        self.save()
                        return True
                    
                    # Check for default category setting by number
                    if f"default-to-{i}" in message_text or f"set default {i}" in message_text:
                        self.category = category
                        self.account.default_category = category
                        self.account.save()
                        self.status = 'QUEUED'
                        self.save()
                        return True

                # Check for default category if no explicit selection
                if self.account.default_category:
                    # Verify user still has access to the default category
                    if self.account.default_category in top_level_categories:
                        self.category = self.account.default_category
                        self.status = 'QUEUED'
                        self.save()
                        return True
                    else:
                        # Clear default category if user no longer has access
                        self.account.default_category = None
                        self.account.save()

            # Start automated categorization from top level (no parent)
            print(f"Attempting to categorize request {self.id} from top level")
            if self._try_categorize_with_children(None):
                print(f"Successfully categorized request {self.id}")
                return True
            
            # If no category matched and user has multiple categories, send category list
            if multiple_categories:
                self._send_category_list()
                return True
            
            # If no category matched and single category access, that's fine
            print(f"No category matched for request {self.id}, setting to QUEUED")
            self.category = None
            self.status = 'QUEUED'
            self.save()
            return True
            
        except Exception as e:
            print(f"Error during categorization of request {self.id}: {str(e)}")
            self.status = 'FAILED'
            self.error = f"Error during categorization: {str(e)}"
            self.save()
            return False

    def _send_category_list(self):
        """Helper method to send category list to user"""
        categories = self.get_available_categories(parent=None)
        category_list = "\n".join([f"- Category {i}: {cat.name}" for i, cat in enumerate(categories, 1)])
        
        message = (
            "You have access to multiple categories. You can:\n\n"
            f"{category_list}\n\n"
            "To select a category, include either:\n"
            "- '[number]-request' (e.g., '1-request')\n"
            "- 'category [number] request' (e.g., 'category 1 request')\n\n"
            "To set a default category, include either:\n"
            "- 'default-to-[number]' (e.g., 'default-to-1')\n"
            "- 'set default [number]' (e.g., 'set default 1')\n\n"
            "You can view this list anytime by including 'list-categories' or 'category-menu' in your message."
        )
        
        self.message.reply_with({"text": message})
        self.status = 'CATEGORY_LIST_SENT'
        self.save()

    def _try_categorize_with_children(self, parent_category=None):
        """
        Recursive helper for categorization.
        Returns True if a matching category was found and set.
        """
        try:
            # Get permitted categories at current level
            categories = self.get_available_categories(parent_category)
            print(f"\nChecking categories at level {parent_category.name if parent_category else 'root'} for request {self.id}")
            print(f"Found {categories.count()} available categories")
            
            # If exactly one category is available, use it without processing
            if categories.count() == 1:
                category = categories.first()
                print(f"Single category available: {category.name}")
                self.category = category
                
                # Check for subcategories
                has_subcategories = category.subcategories.filter(is_active=True).exists()
                if has_subcategories:
                    print(f"Category {category.name} has subcategories, trying to match them")
                    subcategory_result = self._try_categorize_with_children(category)
                    if not subcategory_result:
                        print(f"No subcategories matched, setting status to QUEUED with category {category.name}")
                        self.status = 'QUEUED'
                        self.save()
                else:
                    print(f"No subcategories exist, setting status to QUEUED with category {category.name}")
                    self.status = 'QUEUED'
                    self.save()
                return True

            # Otherwise process each category
            for category in categories:
                try:
                    print(f"\nProcessing category {category.name} for request {self.id}")
                    # Run category's processing function
                    matches = category.process_request(self)
                    print(f"Category {category.name} processing result: {matches}")
                    
                    # If category matched
                    if matches:
                        print(f"Category {category.name} matched")
                        self.category = category
                        self.save()

                        # Check if category has subcategories
                        has_subcategories = category.subcategories.filter(is_active=True).exists()
                        print(f"Category {category.name} has subcategories: {has_subcategories}")
                        
                        if has_subcategories:
                            # Continue categorizing with subcategories
                            print(f"Continuing categorization with subcategories of {category.name}")
                            subcategory_result = self._try_categorize_with_children(category)
                            if not subcategory_result:
                                # If no subcategory matched, mark as queued with current category
                                print(f"No subcategories matched, setting status to QUEUED with category {category.name}")
                                self.status = 'QUEUED'
                                self.save()
                        else:
                            # No subcategories, mark as queued
                            print(f"No subcategories exist, setting status to QUEUED with category {category.name}")
                            self.status = 'QUEUED'
                            self.save()
                        return True
                except Exception as e:
                    # Log error but continue with next category
                    print(f"Error processing category {category.name}: {str(e)}")
                    self.metadata['categorization_errors'] = self.metadata.get('categorization_errors', [])
                    self.metadata['categorization_errors'].append({
                        'category': category.name,
                        'error': str(e)
                    })
                    self.save()
                    continue

            # No matching category found at this level - that's okay
            print(f"No matching category found at level {parent_category.name if parent_category else 'root'}")
            return False

        except Exception as e:
            print(f"Error during category processing: {str(e)}")
            self.error = f"Error during category processing: {str(e)}"
            self.save(update_fields=['error'])
            return False

    def process_category(self):
        """
        Process the request's category and update metadata.
        """
        # No category is a valid state - just mark as completed
        if not self.category:
            self.status = 'COMPLETED'
            self.save()
            return
        
        self.status = 'PROCESSING'
        self.error = None  # Clear any previous errors
        self.save()

        try:
            self.metadata = self.category.process_request(self)
            self.save()
            
            self.status = 'COMPLETED'
            self.save()
        except Exception as e:
            self.status = 'FAILED'
            self.error = f"Error during category processing: {str(e)}"
            self.save()
            raise
    
    def submit_tool_calls(self, tool_calls_data):
        """
        Submit multiple tool calls atomically from this request.
        
        Args:
            tool_calls_data: List of dicts, each containing:
                - name: str
                - arguments: dict
                - id: str (optional, will be generated if not provided)
        
        Returns:
            List of ToolCall objects created
        """
        import uuid
        from django.db import transaction
        from .tool_call import ToolCall
        
        if not tool_calls_data:
            return []
        
        tool_calls = []
        
        with transaction.atomic():
            locked_request = type(self).objects.select_for_update().get(pk=self.pk)
            initial_request = locked_request.initial_request or locked_request
            if initial_request.message.chat.messages.filter(
                is_outgoing=False,
                timestamp__gt=initial_request.message.timestamp,
            ).exclude(media_type__in=['tool_call', 'tool_response']).exists():
                return []
            for call_data in tool_calls_data:
                tool_name = call_data['name']
                arguments = call_data.get('arguments', {}) or {}
                call_id = call_data.get('id') or f"call_{uuid.uuid4().hex[:8]}"
                auto_params = call_data.pop('auto_params', [])
                logged_args = dict(arguments)
                
                # Create tool call message for LLM context
                tool_call_msg = self.message.log_tool_interaction(
                    tool_call={"name": tool_name, "arguments": logged_args, "id": call_id}
                )
                
                # Capture progress update; strip only if auto-injected (not in original schema)
                progress = arguments.get('progress_updates_for_user')
                if 'progress_updates_for_user' in auto_params:
                    arguments.pop('progress_updates_for_user', None)

                tool_call = ToolCall.objects.create(
                    call_id=call_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    progress_updates_for_user=progress,
                    request=locked_request,
                    tool_call_message=tool_call_msg,  # Link to the tool call message
                    initial_user_message=self.message,  # Link to the original user message
                    status='PENDING'
                )
                
                tool_calls.append(tool_call)
            
            # Update request status and count
            locked_request.tool_call_count += len(tool_calls_data)
            locked_request.status = 'PROCESSING'  # Reuse existing status
            locked_request.save(update_fields=['tool_call_count', 'status'])
            self.tool_call_count = locked_request.tool_call_count
            self.status = locked_request.status
        
        return tool_calls
