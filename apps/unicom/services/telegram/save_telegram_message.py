from datetime import datetime, timezone as dt_timezone
from django.contrib.auth.models import User
from unicom.services.telegram.get_file_path import get_file_path
from unicom.services.telegram.download_file import download_file
from django.core.files.base import ContentFile
from django.apps import apps
from django.db import models
import mimetypes
from django.utils import timezone


def _namespaced_message_id(channel, chat_id: str, message_id: str) -> str:
    """
    Telegram message_ids are unique only per chat/bot; namespace for DB storage.
    """
    return f"telegram.{channel.id}.{chat_id}.{message_id}"


def save_telegram_message(channel, message_data: dict, user:User=None):
    Message = apps.get_model('unicom', 'Message')
    Chat = apps.get_model('unicom', 'Chat')
    Account = apps.get_model('unicom', 'Account')
    AccountChat = apps.get_model('unicom', 'AccountChat')
    platform = 'Telegram'  # Set the platform name
    sender_id = message_data.get('from')['id']
    sender_name = message_data.get('from')['first_name']
    is_outgoing = message_data.get('from')['is_bot']  # Keep is_bot in message_data for backwards compatibility
    
    # Check if account exists and is blocked
    account = Account.objects.filter(platform=platform, id=sender_id).first()
    if account and account.blocked:
        return None  # Don't save message if account is blocked
        
    chat_id = message_data.get('chat')['id']
    chat_is_private = message_data.get('chat')["type"] == "private"
    chat_name = sender_name if chat_is_private else message_data.get('chat')["title"]
    raw_message_id = str(message_data.get('message_id'))
    message_id = _namespaced_message_id(channel, chat_id, raw_message_id)
    text = message_data.get('text') or message_data.get('caption')
    m_type = 'text'
    media_file_name = None
    media_file_content = None
    if message_data.get("group_chat_created"):
        text = "**Group Chat Created**"
    elif message_data.get("left_chat_member"):
        user_left = message_data.get("left_chat_member")["first_name"]
        text = f"**user {user_left} left the chat**"
    elif message_data.get('new_chat_photo'):
        text = "**Updated Group Photo**"
    elif message_data.get('pinned_message'):
        pinned_msg_id = message_data.get('pinned_message')['message_id']
        text = f"**{sender_name} pinned message <{pinned_msg_id}>**"
    elif message_data.get('voice'):
        m_type = 'audio'
        voice = message_data.get('voice')
        file_id = voice['file_id']
        duration = voice['duration']
        file_size = voice['file_size']
        mime_type = voice.get('mime_type', 'audio/ogg')
        file_unique_id = voice['file_unique_id']
        # Try to use file_name if available (rare for voice, but for consistency)
        file_name = voice.get('file_name')
        if file_name:
            # Use the extension from the file_name
            extension = '.' + file_name.split('.')[-1] if '.' in file_name else mimetypes.guess_extension(mime_type) or '.oga'
        else:
            extension = mimetypes.guess_extension(mime_type)
            if extension is None:
                extension = '.oga'
        media_generated_filename = f'{file_unique_id}{extension}'
        media_file_name = media_generated_filename
        file_path = get_file_path(channel.config, file_id)
        file_content_bytes = download_file(channel.config, file_path)
        file_content = ContentFile(file_content_bytes)
        media_file_content = file_content
        # trascription = transcribe_audio(file_content_bytes, media_generated_filename)
        text = f"**Voice Message**"# \n{trascription}"
    elif message_data.get('photo'):
        m_type = 'image'
        file_id = message_data.get('photo')[-1]['file_id']
        file_size = message_data.get('photo')[-1]['file_size']
        file_unique_id = message_data.get('photo')[-1]['file_unique_id']
        file_path = get_file_path(channel.config, file_id)
        extension = file_path.split('.')[-1]
        media_file_name = f'{file_unique_id}.{extension}'
        file_content_bytes = download_file(channel.config, file_path)
        file_content = ContentFile(file_content_bytes)
        media_file_content = file_content
        if message_data.get('caption'):
            text = message_data.get('caption')
        else:
            text = "**Image**"
    elif message_data.get('audio'):
        m_type = 'audio'
        audio = message_data['audio']
        file_id        = audio['file_id']
        file_name      = audio.get('file_name', f"{audio['file_unique_id']}")
        mime_type      = audio.get('mime_type')
        # Use extension from file_name if present
        if file_name and '.' in file_name:
            extension = '.' + file_name.split('.')[-1]
        else:
            extension = mimetypes.guess_extension(mime_type) or ''
        file_unique_id = audio['file_unique_id']
        media_file_name    = f"{file_unique_id}{extension}"
        file_path       = get_file_path(channel.config, file_id)
        file_bytes      = download_file(channel.config, file_path)
        media_file_content = ContentFile(file_bytes)
        text = f"**Audio File**: {file_name}"
    elif text == None:
        text = "[[[[Unknown User Action!]]]]"
    timestamp = datetime.fromtimestamp(message_data.get('date'))
    timestamp = timezone.make_aware(timestamp, dt_timezone.utc)
    chat = Chat.objects.filter(platform='Telegram', id=chat_id)
    if not chat.exists():
        chat = Chat(channel=channel, platform=platform, id=chat_id, is_private=chat_is_private, name=chat_name)
        chat.save()
    else:
        chat = chat.get()
    if not account:
        account = Account(
            channel=channel,
            platform=platform,
            id=sender_id,
            name=sender_name,
            is_bot=is_outgoing,  # Keep is_bot for Account model
            raw=message_data.get('from')
        )
        account.save()
    account_chat = AccountChat.objects.filter(account=account, chat=chat)
    if not account_chat.exists():
        account_chat = AccountChat(
            account=account, chat=chat
        )
        account_chat.save()
    else:
        account_chat = account_chat.get()
    if message_data.get('reply_to_message'):
        raw_reply_id = str(message_data.get('reply_to_message')['message_id'])
        reply_candidates = [
            _namespaced_message_id(channel, chat_id, raw_reply_id),
            raw_reply_id,
        ]
        reply_to_message = Message.objects.filter(
            platform=platform,
            chat_id=chat_id,
            id__in=reply_candidates
        ).first()
    else:
        reply_to_message = None
    # Save the message to the database or retrieve it if this is a duplicate save
    existing = Message.objects.filter(
        platform=platform,
        chat_id=chat_id,
    ).filter(
        models.Q(id=message_id) |
        models.Q(id=raw_message_id) |
        models.Q(provider_message_id=raw_message_id)
    ).first()
    if existing:
        if not existing.provider_message_id:
            existing.provider_message_id = raw_message_id
            existing.save(update_fields=['provider_message_id'])
        message, created = existing, False
    else:
        message, created = Message.objects.get_or_create(
            platform=platform,
            chat_id=chat_id,
            id=message_id,
            defaults={
                'provider_message_id': raw_message_id,
                'sender': account,
                'channel': channel,
                'sender_name': sender_name,
                'user': user,
                'text': text,
                'media_type': m_type,
                'reply_to_message': reply_to_message,
                'chat': chat,
                'is_outgoing': is_outgoing,
                'timestamp': timestamp,
                'raw': message_data
            }
        )
    if not created:
        print("Duplicate message discarded")
    else:
        if media_file_name:
            print("Attachment being saved as ", media_file_name)
            message.media.save(media_file_name, media_file_content, save=True)
    return message
