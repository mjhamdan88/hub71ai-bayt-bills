"""
Save incoming WebChat messages and create Request objects.
"""
from django.apps import apps
from django.utils import timezone
from django.core.files.base import ContentFile
from unicom.services.webchat.get_or_create_account import get_or_create_account


def save_webchat_message(channel, message_data, request, user=None):
    """
    Save a WebChat message and create Request for processing.

    Args:
        channel: WebChat Channel instance
        message_data: Dict with message details
            {
                'text': str,  # Required
                'chat_id': str,  # Optional - if not provided, use Account.id
                'reply_to_message_id': str,  # Optional - for message editing/branching
                'media_type': str,  # 'text', 'image', 'audio' (default: 'text')
                'file': UploadedFile,  # Optional - for media messages
            }
        request: Django HTTP request object
        user: User instance (optional, for internal messages)

    Returns:
        Message instance
        
    Note: When reply_to_message_id is provided, creates a conversation branch by
    setting the new message's reply_to_message to the same value as the target message.
    This enables message "editing" from the user's perspective while maintaining
    conversation history and enabling branch navigation.
    """
    Message = apps.get_model('unicom', 'Message')
    Chat = apps.get_model('unicom', 'Chat')
    AccountChat = apps.get_model('unicom', 'AccountChat')
    Request = apps.get_model('unicom', 'Request')

    platform = 'WebChat'

    # Get or create account
    account = get_or_create_account(channel, request)

    # Check if account is blocked
    if account.blocked:
        return None

    # Get or create chat
    chat_id = message_data.get('chat_id')

    if chat_id:
        # Use existing chat
        try:
            chat = Chat.objects.get(id=chat_id, platform=platform, channel=channel)
            # Verify account has access to this chat
            if not AccountChat.objects.filter(account=account, chat=chat).exists():
                # Account doesn't have access - this shouldn't happen
                return None
            created = False
        except Chat.DoesNotExist:
            return None
    else:
        # Create new chat with UUID
        import uuid
        chat_id = f"webchat_{uuid.uuid4()}"

        # Extract metadata for chat (if provided)
        chat_metadata = message_data.get('metadata', {})

        chat = Chat.objects.create(
            id=chat_id,
            platform=platform,
            channel=channel,
            is_private=True,
            name=f"Chat with {account.name}",
            metadata=chat_metadata
        )
        created = True

    # Link account to chat if not already linked
    AccountChat.objects.get_or_create(account=account, chat=chat)

    # Extract message details
    text = message_data.get('text', '').strip()
    media_type = message_data.get('media_type', 'text')
    media_file = message_data.get('file')
    reply_to_message_id = message_data.get('reply_to_message_id')

    # Generate message ID
    import uuid
    message_id = f"webchat_{chat_id}_{uuid.uuid4()}"

    # Create message
    message = Message(
        id=message_id,
        channel=channel,
        platform=platform,
        sender=account,
        user=user,
        chat=chat,
        is_outgoing=False,  # Incoming message from user
        sender_name=account.name,
        text=text or f"**{media_type.title()}**",
        media_type=media_type,
        timestamp=timezone.now(),
        raw={
            'source': 'webchat',
            'account_id': account.id,
            'user_id': user.id if user else None,
        }
    )

    # Set reply_to_message for context chain and branching
    if reply_to_message_id:
        # User specified a message to reply to - use it directly
        try:
            target_msg = Message.objects.get(id=reply_to_message_id, chat=chat)
            # Verify user has access to this message's chat
            if not AccountChat.objects.filter(account=account, chat=chat).exists():
                reply_to_message_id = None  # Fallback to normal mode
            else:
                message.reply_to_message = target_msg  # Reply to the specified message
        except Message.DoesNotExist:
            # Invalid message ID - fallback to normal chain
            reply_to_message_id = None
    
    if not reply_to_message_id:
        # NORMAL MODE: Reply to last assistant message to maintain context chain
        last_assistant_msg = Message.objects.filter(
            chat=chat, 
            is_outgoing=True
        ).order_by('-timestamp').first()
        
        if last_assistant_msg:
            message.reply_to_message = last_assistant_msg

    # Handle media file
    if media_file:
        message.media.save(media_file.name, media_file, save=False)

    message.save()

    # Update chat cache fields
    if not chat.first_message:
        chat.first_message = message
    if not chat.first_incoming_message:
        chat.first_incoming_message = message
    chat.last_message = message
    chat.last_incoming_message = message
    chat.save(update_fields=[
        'first_message', 'first_incoming_message',
        'last_message', 'last_incoming_message'
    ])

    # Auto-generate chat title from first message if needed
    if created and chat.name == f"Chat with {account.name}":
        from unicom.services.webchat.generate_chat_title import generate_chat_title
        generate_chat_title(chat)

    # Create Request object for incoming messages
    # Check if request already exists for this message (avoid duplicates)
    request_obj, request_created = Request.objects.get_or_create(
        message=message,
        defaults={
            'account': account,
            'channel': channel,
            'email': account.member.email if account.member else None,
            'phone': account.member.phone if account.member else None,
            'member': account.member,
            'display_text': text,
            'metadata': {
                'source': 'webchat',
                'chat_id': chat_id
            }
        }
    )

    # Trigger request processing asynchronously (only if newly created)
    if request_created:
        from django.db import transaction
        transaction.on_commit(lambda: _process_request_async(request_obj.id))

    return message


def _process_request_async(request_id):
    """
    Process request asynchronously (identify member, categorize).
    """
    Request = apps.get_model('unicom', 'Request')

    try:
        request = Request.objects.get(id=request_id)

        # Identify member (if not already set)
        if not request.member:
            request.status = 'IDENTIFYING'
            request.save(update_fields=['status'])
            request.identify_member()

        # Categorize request
        request.status = 'CATEGORIZING'
        request.save(update_fields=['status'])
        request.categorize()

    except Request.DoesNotExist:
        print(f"Request {request_id} not found")
    except Exception as e:
        print(f"Error processing request {request_id}: {e}")
        Request.objects.filter(id=request_id).update(
            status='FAILED',
            error=str(e)
        )
