import requests
from uuid import uuid4
from unicom.services.get_public_origin import get_public_origin


def set_telegram_webhook(bot_credentials, allowed_updates=None):
    """
    Set the Telegram bot webhook.
    """
    TelegramCredentials = bot_credentials.config
    TELEGRAM_API_TOKEN = TelegramCredentials["TELEGRAM_API_TOKEN"]
    if "TELEGRAM_SECRET_TOKEN" not in TelegramCredentials:
        TelegramCredentials["TELEGRAM_SECRET_TOKEN"] = uuid4().hex
        bot_credentials.config["TELEGRAM_SECRET_TOKEN"] = TelegramCredentials["TELEGRAM_SECRET_TOKEN"]
    TELEGRAM_SECRET_TOKEN = TelegramCredentials["TELEGRAM_SECRET_TOKEN"]
    origin = get_public_origin()
    if not origin:
        raise ValueError("DJANGO_PUBLIC_ORIGIN is not set")
    webhook_url = f"{origin}/unicom/telegram/{bot_credentials.id}"
    print(f"Updating Telegram Webhook to {webhook_url}")
    url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/setWebhook"

    data = {
        "url": webhook_url,
        "secret_token": TELEGRAM_SECRET_TOKEN
    }

    if allowed_updates:
        data["allowed_updates"] = allowed_updates

    response = requests.post(url, data=data)
    if response.status_code == 200:
        bot_credentials.confirmed_webhook_url = webhook_url
    return response.json()  # Returns the API response to check if the webhook was set correctly
