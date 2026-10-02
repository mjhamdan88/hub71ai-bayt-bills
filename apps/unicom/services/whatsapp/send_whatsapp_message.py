import requests
import time
from unicom.services.whatsapp.save_whatsapp_message import save_whatsapp_message
from django.contrib.auth.models import User

def send_whatsapp_message(WhatsAppCredentials, params: dict, user: User=None, retry_interval=60, max_retries=10):
    """
    Params must include (chat_id or send_to) and either:
        - "text" for text message
        - "template" for template message
        - OR "type":"image" with "image_link" or some reference
      Optionally reply_to_message_id
    """
    WHATSAPP_PHONE_NUMBER_ID = WhatsAppCredentials["WHATSAPP_PHONE_NUMBER_ID"]
    WHATSAPP_ACCESS_TOKEN = WhatsAppCredentials["WHATSAPP_ACCESS_TOKEN"]
    WHATSAPP_PHONE_NUMBER = WhatsAppCredentials["WHATSAPP_PHONE_NUMBER"]
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    if "send_to" in params:
        send_to = params["send_to"]
    elif "chat_id" in params:
        send_to = params["chat_id"]  # For WhatsApp, chat_id is typically the phone number
    else:
        raise Exception("send_message failed: no recipient (send_to or chat_id) provided")

    data = {
        "messaging_product": "whatsapp",
        "to": send_to,
    }

    # Distinguish message types
    if params.get("type") == "image":
        # Example usage with "image_link" for the actual media
        data["type"] = "image"
        if "image_link" not in params:
            raise ValueError("WhatsApp image message requires 'image_link' in params")
        data["image"] = {"link": params["image_link"]}
        # Add optional caption
        if "text" in params:
            data["image"]["caption"] = params["text"]

    elif "text" in params:
        # Plain text message
        data["type"] = "text"
        data["text"] = {"body": params["text"]}

    elif "template" in params:
        # Template message
        data["type"] = "template"
        data["template"] = params["template"]

    else:
        raise ValueError("Invalid params for sending WhatsApp message: provide type='image' + image_link, or 'text', or 'template'")

    # Handle replies
    if "reply_to_message_id" in params:
        # For WhatsApp, remove the prefix if stored with "whatsapp."
        data["context"] = {"message_id": params["reply_to_message_id"].removeprefix("whatsapp.")}

    if WHATSAPP_PHONE_NUMBER_ID is None or WHATSAPP_ACCESS_TOKEN is None:
        raise Exception("WhatsApp send_message failed due to missing credentials.")

    retries = 0
    while retries < max_retries:
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            ret = response.json()
            # Mark this as an outgoing message
            ret["is_outgoing"] = True
            # Add contacts array to match incoming message format
            ret["contacts"] = [{
                "profile": {"name": "Bot"},
                "wa_id": WHATSAPP_PHONE_NUMBER
            }]
            return save_whatsapp_message(WhatsAppCredentials, ret, user)
        except requests.exceptions.RequestException as e:
            retries += 1
            if retries == max_retries:
                raise Exception(f"Failed to send WhatsApp message after {max_retries} retries: {str(e)}")
            print(f"Retry {retries}/{max_retries} after {retry_interval}s...")
            time.sleep(retry_interval)
