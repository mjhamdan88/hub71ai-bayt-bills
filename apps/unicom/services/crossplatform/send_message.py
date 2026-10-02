from __future__ import annotations
from typing import TYPE_CHECKING
from unicom.services.telegram.send_telegram_message import send_telegram_message
from unicom.services.whatsapp.send_whatsapp_message import send_whatsapp_message
from unicom.services.email.send_email_message import send_email_message
from unicom.services.webchat.send_webchat_message import send_webchat_message
from django.contrib.auth.models import User

if TYPE_CHECKING:
    from unicom.models import Channel, Message


def send_message(channel: Channel, msg:dict, user:User=None) -> Message:
    """
    The msg dict must include platform-specific required fields:

    For Email:
        New threads:
            - 'to': list of recipient email addresses
            - 'subject': required subject line
        Replies:
            - Either 'chat_id' or 'reply_to_message_id'
            - Subject is optional (derived from parent if not provided)

    For Telegram/WhatsApp/WebChat:
        - 'chat_id' and 'text' are required
    """
    if channel.platform == 'Telegram':
        return send_telegram_message(channel, msg, user)
    elif channel.platform == 'WhatsApp':
        return send_whatsapp_message(channel, msg, user)
    elif channel.platform == 'Email':
        return send_email_message(channel, msg, user)
    elif channel.platform == 'WebChat':
        return send_webchat_message(channel, msg, user)