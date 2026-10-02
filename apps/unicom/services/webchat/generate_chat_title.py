"""
Auto-generate chat titles from first message.
"""
from django.apps import apps


def generate_chat_title(chat):
    """
    Auto-generate chat title from first user message.

    Args:
        chat: Chat instance

    Returns:
        str: Generated title
    """
    Message = apps.get_model('unicom', 'Message')

    # Get first message from user (not outgoing)
    first_message = Message.objects.filter(
        chat=chat,
        is_outgoing=False
    ).order_by('timestamp').first()

    if not first_message or not first_message.text:
        return "New Chat"

    # Use first 50 characters of first message as title
    text = first_message.text.strip()

    # Clean up common message prefixes
    for prefix in ['hello', 'hi', 'hey']:
        if text.lower().startswith(prefix):
            # Skip greeting and use rest of message if long enough
            words = text.split()
            if len(words) > 1:
                text = ' '.join(words[1:])

    # Truncate to 50 chars
    if len(text) > 50:
        title = text[:47] + "..."
    else:
        title = text if text else "New Chat"

    # Update chat name
    chat.name = title
    chat.save(update_fields=['name'])

    return title
