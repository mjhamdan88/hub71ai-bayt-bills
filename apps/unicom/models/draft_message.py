from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone


class DraftMessage(models.Model):
    """Model for storing draft messages and scheduled messages."""
    
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('scheduled', _('Scheduled')),
        ('sent', _('Sent')),
        ('failed', _('Failed')),
    ]

    # Basic Fields
    channel = models.ForeignKey(
        'Channel',
        on_delete=models.CASCADE,
        verbose_name=_('Channel'),
        help_text=_('Channel to send the message through')
    )

    # For email messages
    to = models.JSONField(
        _('To'),
        default=list,
        blank=True,
        help_text=_('List of recipient email addresses')
    )
    cc = models.JSONField(
        _('CC'),
        default=list,
        blank=True,
        help_text=_('List of CC email addresses')
    )
    bcc = models.JSONField(
        _('BCC'),
        default=list,
        blank=True,
        help_text=_('List of BCC email addresses')
    )
    subject = models.CharField(
        _('Subject'),
        max_length=512,
        blank=True,
        help_text=_('Subject line for email messages')
    )
    
    # For chat-based messages (Telegram, WhatsApp)
    chat_id = models.CharField(
        _('Chat ID'),
        max_length=500,
        blank=True,
        help_text=_('Chat ID for messaging platforms')
    )
    
    # Common message content
    text = models.TextField(
        _('Text Content'),
        blank=True,
        help_text=_('Plain text content of the message')
    )
    html = models.TextField(
        _('HTML Content'),
        blank=True,
        help_text=_('HTML content for email messages')
    )
    skip_reacher_validation = models.BooleanField(
        _('Skip Reacher validation'),
        default=False,
        help_text=_('Skip Reacher email validation when sending this draft')
    )
    
    # Scheduling and status
    send_at = models.DateTimeField(
        _('Send At'),
        null=True,
        blank=True,
        help_text=_('When this message should be sent')
    )
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )
    is_approved = models.BooleanField(
        _('Approved'),
        default=False,
        help_text=_('Whether this message is approved for sending')
    )
    
    # Link to sent message
    sent_message = models.ForeignKey(
        'Message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='draft_message',
        verbose_name=_('Sent Message'),
        help_text=_('The actual message that was sent from this draft')
    )
    
    # Metadata
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='draft_messages',
        verbose_name=_('Created by')
    )
    created_at = models.DateTimeField(
        _('Created at'),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _('Updated at'),
        auto_now=True
    )
    sent_at = models.DateTimeField(
        _('Sent at'),
        null=True,
        blank=True
    )
    error_message = models.TextField(
        _('Error Message'),
        blank=True,
        help_text=_('Error message if sending failed')
    )
    
    class Meta:
        verbose_name = _('Draft Message')
        verbose_name_plural = _('Draft Messages')
        ordering = ['-updated_at']
    
    def __str__(self):
        if self.subject:
            return self.subject
        elif self.text:
            return self.text[:50] + ('...' if len(self.text) > 50 else '')
        return f"Message {self.id}"
    
    def clean(self):
        """Validate the draft message based on channel platform."""
        if not self.channel_id:
            raise ValidationError(_('Channel is required'))
            
        platform = self.channel.platform
        
        if platform == 'Email':
            if not self.to and not self.chat_id:
                raise ValidationError(_('Either recipients or chat ID is required for email messages'))
            if not self.chat_id and not self.subject:
                raise ValidationError(_('Subject is required for new email threads'))
        else:  # Telegram, WhatsApp
            if not self.chat_id:
                raise ValidationError(_('Chat ID is required for messaging platforms'))
            if not self.text:
                raise ValidationError(_('Message text is required'))
    
    def get_message_dict(self):
        """Convert draft to message parameters for sending."""
        msg_dict = {}
        
        if self.channel.platform == 'Email':
            if self.to:
                msg_dict['to'] = self.to
            if self.cc:
                msg_dict['cc'] = self.cc
            if self.bcc:
                msg_dict['bcc'] = self.bcc
            if self.subject:
                msg_dict['subject'] = self.subject
            if self.html:
                msg_dict['html'] = self.html
            if self.chat_id:
                msg_dict['chat_id'] = self.chat_id
            if self.skip_reacher_validation:
                msg_dict['skip_reacher'] = True
            # Enable template rendering with the built-in Unicom context.
            msg_dict['render_template'] = True
        else:
            msg_dict['chat_id'] = self.chat_id
            msg_dict['text'] = self.text
            
        return msg_dict
    
    def send(self):
        """Attempt to send the draft message."""
        if not self.is_approved:
            raise ValidationError(_('Message must be approved before sending'))
            
        if self.send_at and self.send_at > timezone.now():
            raise ValidationError(_('Cannot send scheduled message before scheduled time'))
            
        try:
            message = self.channel.send_message(self.get_message_dict(), user=self.created_by)
            self.status = 'sent'
            self.sent_at = timezone.now()
            self.sent_message = message
            self.save()
            return message
        except Exception as e:
            self.status = 'failed'
            self.error_message = str(e)
            self.save()
            raise 
