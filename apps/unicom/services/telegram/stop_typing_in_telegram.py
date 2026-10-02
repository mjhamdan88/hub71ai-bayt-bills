import requests


def stop_typing_in_telegram(TelegramCredentials, chat_id):
    TELEGRAM_API_TOKEN = TelegramCredentials["TELEGRAM_API_TOKEN"]
    if TELEGRAM_API_TOKEN is None: 
        raise Exception("stop_typing_in_telegram failed as no TELEGRAM_API_TOKEN was defined")
    url = f'https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendChatAction'
    data = {'chat_id': chat_id, 'action': 'cancel'}
    response = requests.post(url, json=data)
    if response.status_code != 200:
        raise Exception(f'Error stopping typing indication: {response.status_code} {response.text}')
