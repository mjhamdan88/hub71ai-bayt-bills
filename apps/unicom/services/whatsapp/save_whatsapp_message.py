from datetime import datetime
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.apps import apps
import requests
import mimetypes
import json
import uuid
from django.utils import timezone


def save_whatsapp_message(WhatsAppCredentials, messages_data: dict, user:User=None):
    Message = apps.get_model('unicom', 'Message')
    Chat = apps.get_model('unicom', 'Chat')
    Account = apps.get_model('unicom', 'Account')
    AccountChat = apps.get_model('unicom', 'AccountChat')
    WHATSAPP_ACCESS_TOKEN = WhatsAppCredentials["WHATSAPP_ACCESS_TOKEN"]
    with open("debug_out.json", 'w') as file:
        json.dump(messages_data, file, indent=4)
    platform = 'WhatsApp'  # Set the platform name
    contacts = messages_data.get('contacts')
    if len(contacts) != 1:
        raise ValueError(f"More than one contacts included! {contacts}")
    contact = contacts[0]
    contact_profile = contact.get("profile")
    m_type = 'text'
    media_file_name = None
    media_file_content = None
    # For backwards compatibility, we check both is_bot and is_outgoing
    is_outgoing = messages_data.get("is_outgoing", False) or (messages_data.get("is_bot", False))
    if contact_profile:
        sender_name = contact_profile.get('name')
    elif is_outgoing:
        sender_name = "Bot"
    else:
        sender_name = "[[[[Unknown]]]]"
    chat_id = contact.get("wa_id")
    chat_is_private = True # message_data.get('chat')["type"] == "private"
    chat_name = sender_name
    for message_data in messages_data.get("messages"):
        message_id = f"whatsapp.{message_data.get('id')}"
        sender_id = message_data.get('from')
        image = None
        # text = message_data.get('text') or message_data.get('caption')
        if message_data.get("type") == 'text':
            text = message_data["text"]["body"]
        elif message_data.get("type") == 'button':
            text = message_data["button"]["text"]
        elif message_data.get("type") == 'template':
            template = message_data["template"]
            text = f"[[[[Template Message!]]]]\n\n\n{json.dumps(template, indent=2)}"
        elif message_data.get("type") == "reaction":
            print("Reaction message Ignored")
            return None
        elif message_data.get("type") == "audio":
            m_type = "audio"
            media_id = message_data["audio"]["id"]
            media_api_url = f"https://graph.facebook.com/v20.0/{media_id}/"
            media_details_response = requests.get(media_api_url, headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"})
            if media_details_response.status_code == 200:
                media_details = media_details_response.json()
                media_url = media_details["url"]
                media_mime_type = media_details["mime_type"]
                extension = mimetypes.guess_extension(media_mime_type)
                media_generated_filename = f'{uuid.uuid4()}{extension}'
                media_data_response = requests.get(media_url, headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"})
                if media_data_response.status_code == 200:
                    media_file_name = media_generated_filename
                    media_file_content = ContentFile(media_data_response.content)
                else:
                    text = "[[[Audio Message! Error, failed to retrive media file]]]"
                    print(media_data_response.status_code)
                    print(media_data_response.text)
            else:
                text = "[[[Audio Message! Error, failed to retrive media details]]]"
                print(media_details_response.status_code)
                print(media_details_response.text)
            # TODO: Use the transcribtion API here
            text = "[[[Audio Message]]]"
        elif message_data.get("type") == "image":
            m_type = "image"
            media_id = message_data["image"]["id"]
            media_api_url = f"https://graph.facebook.com/v20.0/{media_id}/"
            media_details_response = requests.get(media_api_url, headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"})
            if media_details_response.status_code == 200:
                media_details = media_details_response.json()
                media_url = media_details["url"]
                media_mime_type = media_details["mime_type"]
                extension = mimetypes.guess_extension(media_mime_type)
                if extension is None:
                    extension = '.jpg'
                media_generated_filename = f'{uuid.uuid4()}{extension}'
                media_data_response = requests.get(media_url, headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"})
                if media_data_response.status_code == 200:
                    media_file_name = media_generated_filename
                    media_file_content = ContentFile(media_data_response.content)
                    if 'caption' in message_data["image"]:
                        text = message_data["image"]["caption"]
                    else:
                        text = ""
                else:
                    text = "[[[Image Message! Error, failed to retrive image file]]]"
                    print(media_data_response.status_code)
                    print(media_data_response.text)
            else:
                text = "[[[Image Message! Error, failed to retrive image details]]]"
                print(media_details_response.status_code)
                print(media_details_response.text)
        else:
            text = f"[[[[Unknown Message Type! {message_data.get('type')} Message]]]]"
        timestamp = datetime.fromtimestamp(int(message_data.get('timestamp'))) if 'timestamp' in message_data else None
        if timestamp is not None:
            timestamp = timezone.make_aware(timestamp, timezone.utc)
        chat = Chat.objects.filter(platform=platform, id=chat_id)
        
        # Check if account exists and is blocked
        account = Account.objects.filter(platform=platform, id=sender_id).first()
        if account and account.blocked:
            continue  # Skip this message if account is blocked
            
        if not chat.exists():
            chat = Chat(platform=platform, id=chat_id, is_private=chat_is_private, name=chat_name)
            chat.save()
        else:
            chat = chat.get()
            if sender_name != chat.name and not is_outgoing:
                chat.name = sender_name
                chat.save()
        if not account:
            account = Account(
                platform=platform,
                id=sender_id,
                name=sender_name,
                is_bot=is_outgoing,  # Keep is_bot for Account model
                raw=messages_data.get('contacts')[0]
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
        if message_data.get('context'):
            reply_to_message_id = f"whatsapp.{message_data.get('context')['id']}"
            try:
                reply_to_message = Message.objects.get(
                    platform=platform, chat_id=chat_id, id=reply_to_message_id)
            except Message.DoesNotExist:
                reply_to_message = None
        else:
            reply_to_message = None
        msg_obj, created = Message.objects.get_or_create(
            platform=platform,
            chat_id=chat_id,
            id=message_id,
            defaults={
                'sender_id': sender_id,
                'sender_name': sender_name,
                'is_outgoing': is_outgoing,
                'user': user,
                'text': text,
                'media_type': m_type,
                'reply_to_message': reply_to_message,
                'timestamp': timestamp,
                'raw': message_data
            }
        )
        if not created:
            print("Duplicate message discarded")
        else:
            if media_file_name:
                msg_obj.media.save(media_file_name, media_file_content, save=True)
            if image is not None:
                # TODO: Fix bug: image_content not defined
                pass
                # msg_obj.image.save(image, image_content, save=True)
    return msg_obj