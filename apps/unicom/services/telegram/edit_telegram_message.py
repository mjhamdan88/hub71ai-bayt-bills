# unicom.services.telegram.edit_telegram_message.py
from __future__ import annotations
from typing import TYPE_CHECKING
import requests
import json

if TYPE_CHECKING:
    from unicom.models import Channel, Message


def edit_telegram_message(channel: Channel, message: Message, params: dict) -> bool:
    """
    Edit an existing Telegram message with new content and/or buttons.

    Args:
        channel: The Telegram channel
        message: The message to edit
        params: Dictionary with new content:
            - text: New message text
            - reply_markup: New inline keyboard buttons

    Returns:
        bool: True if edit was successful
    """
    TelegramCredentials = channel.config
    TELEGRAM_API_TOKEN = TelegramCredentials["TELEGRAM_API_TOKEN"]

    if TELEGRAM_API_TOKEN is None:
        raise Exception("edit_telegram_message failed as no TELEGRAM_API_TOKEN was defined")

    # Get the original message data from raw field
    if not message.raw or 'message_id' not in message.raw:
        print(f"Cannot edit message {message.id}: no message_id in raw data")
        return False

    # Prepare edit parameters
    edit_params = {
        'chat_id': message.raw.get('chat', {}).get('id'),
        'message_id': message.raw.get('message_id'),
    }

    # Add new content
    if 'text' in params:
        edit_params['text'] = params['text']
        edit_params['parse_mode'] = params.get('parse_mode', 'Markdown')

    # Add new buttons if provided
    if 'reply_markup' in params:
        edit_params['reply_markup'] = json.dumps(params['reply_markup'])

    # Make the API call to edit the message
    url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/editMessageText"

    try:
        response = requests.post(url, data=edit_params)
        result = response.json()

        if result.get('ok'):
            print(f"Successfully edited message {message.id}")
            return True
        else:
            print(f"Failed to edit message {message.id}: {result.get('description', 'Unknown error')}")
            return False

    except Exception as e:
        print(f"Error editing message {message.id}: {str(e)}")
        return False