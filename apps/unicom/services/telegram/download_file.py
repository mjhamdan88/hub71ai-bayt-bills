import requests


def download_file(TelegramCredentials, file_path: str) -> bytes:
    TELEGRAM_API_TOKEN = TelegramCredentials["TELEGRAM_API_TOKEN"]
    url = f'https://api.telegram.org/file/bot{TELEGRAM_API_TOKEN}/{file_path}'
    response = requests.get(url)
    return response.content