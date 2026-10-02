# unicom.services.telegram.answer_callback_query.py
from __future__ import annotations
from typing import TYPE_CHECKING
import requests

if TYPE_CHECKING:
    from unicom.models import Channel


def answer_callback_query(channel: Channel, callback_query_id: str, text: str = None, show_alert: bool = False) -> bool:
    """
    Answer a Telegram callback query to stop the loading indicator on the button.

    Args:
        channel: The Telegram channel
        callback_query_id: The unique ID of the callback query
        text: Optional notification text to show to the user
        show_alert: If True, shows an alert instead of a notification

    Returns:
        bool: True if successful
    """
    TelegramCredentials = channel.config
    TELEGRAM_API_TOKEN = TelegramCredentials["TELEGRAM_API_TOKEN"]

    if TELEGRAM_API_TOKEN is None:
        raise Exception("answer_callback_query failed as no TELEGRAM_API_TOKEN was defined")

    url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/answerCallbackQuery"

    params = {
        'callback_query_id': callback_query_id
    }

    if text:
        params['text'] = text

    if show_alert:
        params['show_alert'] = True

    try:
        response = requests.post(url, data=params, timeout=5)  # 5 second timeout
        result = response.json()

        if result.get('ok'):
            print(f"✅ Successfully answered callback query {callback_query_id}")
            return True
        else:
            error_desc = result.get('description', 'Unknown error')
            # Don't treat "too old" as a failure - it just means we were slow
            if 'too old' in error_desc.lower():
                print(f"⚠️ Callback query {callback_query_id} was too old (already timed out)")
                return True  # Not an error, just late
            print(f"❌ Failed to answer callback query {callback_query_id}: {error_desc}")
            return False

    except requests.exceptions.Timeout:
        print(f"⚠️ Timeout answering callback query {callback_query_id} (network issue)")
        return False  # Don't block on network issues
    except Exception as e:
        print(f"❌ Error answering callback query {callback_query_id}: {str(e)}")
        return False