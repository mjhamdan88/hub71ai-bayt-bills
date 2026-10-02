from __future__ import annotations
from typing import TYPE_CHECKING
from django.db import models
from .constants import channels
from django.core.exceptions import ValidationError
from unicom.services.telegram.set_telegram_webhook import set_telegram_webhook
from unicom.services.email.validate_email_config import validate_email_config
from unicom.services.email.listen_to_IMAP import listen_to_IMAP
from unicom.services.crossplatform.send_message import send_message
from django.contrib.auth.models import User

if TYPE_CHECKING:
    from unicom.models import Message


class Channel(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100)
    platform = models.CharField(max_length=100, choices=channels)
    config = models.JSONField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='channels', verbose_name='Created by')

    active = models.BooleanField(default=False, editable=False)
    confirmed_webhook_url = models.CharField(max_length=500, null=True, blank=True, editable=False) # Used for Telegram and WhatsApp to check if the URL changed and update the service provided if it did
    error = models.CharField(max_length=500, null=True, blank=True, editable=False) # Used for Telegram and WhatsApp to check if the URL changed and update the service provided if it did
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    def send_message(self, msg: dict, user=None) -> Message:
        """
        Send a message using the channel's platform.
        
        For email channels:
            - New threads require:
                - 'to' list with at least one recipient
                - 'subject' for the email thread
            - Replies require:
                - Either 'reply_to_message_id' or 'chat_id'
                - Subject is optional (derived from parent if not provided)
        
        For other platforms:
            - Requires 'chat_id' and 'text'
        """
        if not self.active:
            raise ValidationError("Channel must be active to send messages.")
        
        try:
            return send_message(self, msg, user)
        except Exception as e:
            raise ValidationError(f"Failed to send message: {str(e)}")

    def listen_to_IMAP(self):
        """
        Start listening to IMAP for new emails.
        This method is called when the channel is validated and active.
        """
        if not self.active:
            raise ValidationError("Channel must be active to listen to IMAP.")

        if not self.platform == 'Email':
            raise ValidationError("IMAP listener can only be started for Email channels.")
        
        try:
            print(f"Listening to IMAP for channel {self.name} on platform {self.platform}")
            listen_to_IMAP(self)
        except Exception as e:
            raise ValidationError(f"IMAP IDLE listener exited: {str(e)}")

    def validate_SMTP_and_IMAP(self) -> bool:
        """
        Normalize and validate email client settings. Updates self.config, sets error/active flags.
        """
        try:
            normalized = validate_email_config(self.config or {})
            # Update config with normalized settings
            self.config = normalized
            self.error = None
            self.active = True
            return True
        except ValidationError as e:
            self.error = str(e)
            self.active = False
            return False

    def validate(self):
        print(f"Validating {self.name} ({self.platform})")
        attributes_monitored_for_change = ('active', 'error', 'confirmed_webhook_url', 'config')
        # Snapshot old values for comparison
        old = type(self).objects.filter(pk=self.pk).values(
            *attributes_monitored_for_change
        ).first() or {}

        # Reset status
        self.confirmed_webhook_url = None
        self.active = False

        if self.platform == 'Telegram':
            try:
                result = set_telegram_webhook(self)
                if not result.get('ok'):
                    self.error = result.get('description', 'Could not update webhook URL')
                else:
                    self.active = True
                    self.error = None
            except Exception as e:
                self.error = f"Failed to set Telegram webhook: {str(e)}"

        elif self.platform == 'WhatsApp':
            return True

        elif self.platform == 'Email':
            self.validate_SMTP_and_IMAP()

        elif self.platform == 'WebChat':
            # WebChat doesn't need external validation
            # Just mark as active
            self.active = True
            self.error = None

        # Determine changed fields and update via QuerySet.update() to avoid signals
        changes = {}
        for field in attributes_monitored_for_change:
            old_value = old.get(field)
            new_value = getattr(self, field)
            if old_value != new_value:
                changes[field] = new_value

        if changes:
            print(f"Changes detected for {self.name} ({self.platform}): {changes}")
            type(self).objects.filter(pk=self.pk).update(**changes)
        else:
            print(f"No changes detected for {self.name} ({self.platform})")

        print(f"Webhook URL: {self.confirmed_webhook_url}")
        print(f"Active: {self.active}")
        print(f"Error: {self.error}")
        return self.active

    def __str__(self):
        status_emoji = "✅" if self.active else ( "❌" if self.error is not None else "⚪️" )
        if self.error:
            status_emoji = "⚠️"
        return f"{status_emoji} {self.name} ({self.platform})" if self.error is None else f"{status_emoji} {self.name} ({self.platform}) - {self.error}"

