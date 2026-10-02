import requests


def start_typing_in_telegram(TelegramCredentials, chat_id):
    TELEGRAM_API_TOKEN = TelegramCredentials["TELEGRAM_API_TOKEN"]
    if TELEGRAM_API_TOKEN is None: 
        raise Exception("start_typing_in_telegram failed as no TELEGRAM_API_TOKEN was defined")
    url = f'https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendChatAction'
    data = {'chat_id': chat_id, 'action': 'typing'}
    response = requests.post(url, json=data)
    if response.status_code != 200:
        raise Exception(f'Error starting typing indication: {response.status_code} {response.text}')
