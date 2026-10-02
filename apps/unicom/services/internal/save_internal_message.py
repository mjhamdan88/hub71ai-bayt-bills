from unicom.models import Message, Chat, Account, AccountChat
from datetime import datetime
from django.contrib.auth.models import User
from django.utils import timezone

def save_internal_message(message_data: dict, user: User=None,):
    platform = 'Internal'
    sender_id = message_data.get('from')['id']
    sender_name = message_data.get('from')['first_name']
    is_outgoing = message_data.get('from')['is_bot']
    chat_id = message_data.get('chat')['id']
    chat_is_private = message_data.get('chat')["type"] == "private"
    chat_name = message_data.get('chat')["title"]
    message_id = message_data.get('message_id')
    media_type = message_data.get('media_type', 'text')  # or 'image', 'audio'
    media_file = message_data.get('media')  # might be a path, or None
    text = message_data.get('text') or message_data.get('caption')
    timestamp = datetime.fromtimestamp(message_data.get('date'))
    timestamp = timezone.make_aware(timestamp, timezone.utc)
    chat = Chat.objects.filter(platform=platform, id=chat_id)
    account = Account.objects.filter(platform=platform, id=sender_id)
    if not chat.exists():
        chat = Chat(platform=platform, id=chat_id, is_private=chat_is_private, name=chat_name)
        chat.save()
    else:
        chat = chat.get()

    if not account.exists():
        account = Account(
            platform=platform,
            id=sender_id,
            name=sender_name,
            is_bot=is_outgoing,
            raw=message_data.get('from')
        )
        account.save()
    else:
        account = account.get()

    account_chat = AccountChat.objects.filter(account=account, chat=chat)
    if not account_chat.exists():
        account_chat = AccountChat(account=account, chat=chat)
        account_chat.save()
    else:
        account_chat = account_chat.get()

    if message_data.get('reply_to_message'):
        reply_to_message_id = message_data.get('reply_to_message')['message_id']
        try:
            reply_to_message = Message.objects.get(platform=platform, chat_id=chat_id, id=reply_to_message_id)
        except Message.DoesNotExist:
            reply_to_message = None
    else:
        reply_to_message = None

    message, created = Message.objects.get_or_create(
        platform=platform,
        chat_id=chat_id,
        id=message_id,
        defaults={
            'sender': account,
            'channel': chat.channel,
            'sender_name': sender_name,
            'user': user,
            'text': text,
            'reply_to_message': reply_to_message,
            'timestamp': timestamp,
            'raw': message_data,
            'media_type': media_type,
            'media': media_file,
            'is_outgoing': is_outgoing,
        }
    )
    if not created:
        print("Duplicate message discarded")
    return message
