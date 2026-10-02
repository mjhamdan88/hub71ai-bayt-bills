import requests


def get_file_path(TelegramCredentials, file_id: str) -> str:
    TELEGRAM_API_TOKEN = TelegramCredentials["TELEGRAM_API_TOKEN"]
    url = f'https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/getFile?file_id={file_id}'
    response = requests.get(url)
    response_json = response.json()
    file_path = response_json['result']['file_path']
    return file_path