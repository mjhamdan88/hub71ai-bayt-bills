import requests


def get_template(WhatsAppCredentials, params = {}):
    WHATSAPP_PHONE_NUMBER_ID = WhatsAppCredentials["WHATSAPP_PHONE_NUMBER_ID"]
    WHATSAPP_ACCESS_TOKEN = WhatsAppCredentials["WHATSAPP_ACCESS_TOKEN"]
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/message_templates"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
    }
    response = requests.post(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    print(response.status_code)
    print(response.json())
    raise Exception(f"Failed to get Template")
