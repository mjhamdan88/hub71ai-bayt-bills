"""
Send outgoing WebChat messages (from bots/system to users).
"""
import logging

from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.files import File
from django.utils import timezone

logger = logging.getLogger(__name__)


def _message_body(msg):
    text = msg.get('text', '').strip()
    html = msg.get('html', '').strip()
    if not text and not html and msg.get('file_path'):
        text = {
            'image': 'Generated image',
            'audio': 'Audio attachment',
        }.get(msg.get('media_type'), 'File attachment')
    return text, html


def send_webchat_message(channel, msg, user=None):
    """
    Send a WebChat message (save to database).
    Used by bots/system to send messages to users.

    Args:
        channel: WebChat Channel instance
        msg: Dict with message details
            {
                'chat_id': str,  # Required
                'text': str,  # Required (or html)
                'html': str,  # Optional - rich HTML content
                'file_path': str,  # Optional - path to media file
                'media_type': str,  # 'text', 'html', 'image', 'audio'
            }
        user: User instance (optional)

    Returns:
        Message instance
    """
    Message = apps.get_model('unicom', 'Message')
    Chat = apps.get_model('unicom', 'Chat')
    Account = apps.get_model('unicom', 'Account')
    AccountChat = apps.get_model('unicom', 'AccountChat')
    ToolCall = apps.get_model('unicom', 'ToolCall')

    platform = 'WebChat'

    # Extract optional metadata
    tool_call_id = msg.pop('_tool_call_id', None)
    message_raw = msg.pop('_message_raw', None)
    if message_raw is not None and not isinstance(message_raw, dict):
        raise ValueError("_message_raw must be a dictionary")

    # Get required fields
    chat_id = msg.get('chat_id')
    if not chat_id:
        raise ValueError("chat_id is required")

    # WebChat messages may consist only of generated/attached media. The
    # Message model still needs a textual representation for history and
    # accessibility, so provide one when callers omit a caption.
    text, html = _message_body(msg)

    if not text and not html:
        raise ValueError("Either text or html is required")

    # Get chat
    try:
        chat = Chat.objects.get(id=chat_id, platform=platform, channel=channel)
    except Chat.DoesNotExist:
        raise ValueError(f"Chat {chat_id} not found")

    # Get sender account (system/bot account)
    # For WebChat, outgoing messages are from the channel's "bot" account
    sender_account_id = f"webchat_bot_{channel.id}"
    sender_account, created = Account.objects.get_or_create(
        id=sender_account_id,
        defaults={
            'platform': platform,
            'channel': channel,
            'name': channel.name,
            'is_bot': True,
            'raw': {'channel_id': channel.id}
        }
    )

    # Determine media type
    media_type = msg.get('media_type', 'html' if html else 'text')

    # Generate message ID
    import uuid
    message_id = f"webchat_{chat_id}_{uuid.uuid4()}"

    # Create message
    message = Message(
        id=message_id,
        channel=channel,
        platform=platform,
        sender=sender_account,
        user=user,
        chat=chat,
        is_outgoing=True,  # Outgoing message to user
        sender_name=sender_account.name,
        text=text or html,
        html=html if html else None,
        media_type=media_type,
        timestamp=timezone.now(),
        raw={
            'source': 'webchat_outgoing',
            'channel_id': channel.id,
            'user_id': user.id if user else None,
            **(message_raw or {}),
        }
    )

    # Handle media file
    file_path = msg.get('file_path')
    if file_path:
        try:
            with open(file_path, 'rb') as f:
                file_content = File(f)
                import os
                filename = os.path.basename(file_path)
                message.media.save(filename, file_content, save=False)
        except Exception as e:
            print(f"Warning: Could not attach media file: {e}")

    message.save()

    # Resolve tool call reference if provided
    tool_call_obj = None
    if tool_call_id:
        try:
            tool_call_obj = ToolCall.objects.filter(id=tool_call_id).first()
        except (ValueError, ValidationError):
            tool_call_obj = None

        if not tool_call_obj:
            # Some callers pass the OpenAI-style call_id (e.g., "call_abc123").
            tool_call_obj = ToolCall.objects.filter(call_id=tool_call_id).first()
            if tool_call_obj:
                logger.debug(
                    "Resolved tool_call via call_id fallback (call_id=%s, pk=%s)",
                    tool_call_id,
                    tool_call_obj.id
                )

    # Handle interactive buttons
    buttons = msg.get('buttons')
    if buttons:
        from unicom.models import CallbackExecution, AccountChat
        
        # Get intended account (recipient)
        account_chat = AccountChat.objects.filter(chat=chat).first()
        intended_account = account_chat.account if account_chat else None
        
        if intended_account:
            # Process buttons and create CallbackExecution records
            processed_buttons = []
            for row in buttons:
                processed_row = []
                for button in row:
                    if button.get('type') == 'callback':
                        execution = CallbackExecution.objects.create(
                            original_message=message,
                            callback_data=button['callback_data'],
                            intended_account=intended_account,
                            tool_call=tool_call_obj,
                            expires_at=button.get('expires_at')
                        )
                        button = button.copy()
                        button['callback_execution_id'] = str(execution.id)
                    processed_row.append(button)
                processed_buttons.append(processed_row)
            
            # Store in message raw data
            if not message.raw:
                message.raw = {}
            message.raw['interactive_buttons'] = processed_buttons
            message.save(update_fields=['raw'])

    # Update chat cache fields
    if not chat.first_message:
        chat.first_message = message
    if not chat.first_outgoing_message:
        chat.first_outgoing_message = message
    chat.last_message = message
    chat.last_outgoing_message = message
    chat.save(update_fields=[
        'first_message', 'first_outgoing_message',
        'last_message', 'last_outgoing_message'
    ])

    return message
