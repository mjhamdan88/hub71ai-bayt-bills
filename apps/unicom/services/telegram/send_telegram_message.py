# robopower.services.telegram.send_telegram_message.py
from __future__ import annotations
from typing import TYPE_CHECKING
from unicom.services.telegram.save_telegram_message import save_telegram_message
from unicom.services.telegram.escape_markdown import escape_markdown
from django.contrib.auth.models import User
from django.conf import settings
import requests
import time
import os
import tempfile
import subprocess
import shutil
import uuid

if TYPE_CHECKING:
    from unicom.models import Channel


def _extract_telegram_message_id(message_id):
    """
    Strip internal namespace (telegram.<channel>.<chat>.<message>) back to provider id.
    """
    if message_id is None:
        return None
    if isinstance(message_id, str) and message_id.startswith("telegram."):
        return message_id.split(".")[-1]
    return message_id


def send_telegram_message(channel: Channel, params: dict, user: User=None, retry_interval=60, max_retries=7):
    """
    Params must include at least chat_id and text (if sending a text message or caption).
    If 'type' == 'audio', we send an audio file.
    If 'type' == 'image', we send a photo, with optional caption in 'text'.
    If 'reply_markup' is provided, it will be sent as inline keyboard buttons.
    """
    if not "parse_mode" in params:
        params["parse_mode"] = "Markdown"
    TelegramCredentials = channel.config
    TELEGRAM_API_TOKEN = TelegramCredentials["TELEGRAM_API_TOKEN"]
    if TELEGRAM_API_TOKEN is None:
        raise Exception("send_telegram_message failed as no TELEGRAM_API_TOKEN was defined")

    files = None
    url = None

    if 'type' in params:
        msg_type = params['type']
        # Sending audio
        if msg_type == 'audio':
            file_path = params['file_path']
            ext = os.path.splitext(file_path)[-1].lower()
            if ext in ['.oga', '.ogg']:
                url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendVoice"
                files = {"voice": open(file_path, 'rb')}
                # Store audio_id before popping file_path
                audio_id = params.get('audio_id')
                params.pop('file_path', None)
                params.pop('type', None)
            else:
                url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendAudio"
                files = {"audio": open(file_path, 'rb')}
                # Store audio_id before popping file_path
                audio_id = params.get('audio_id')
                params.pop('file_path', None)
                params.pop('type', None)

        # Sending image
        elif msg_type == 'image':
            url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendPhoto"
            # Expecting a local file_path to open, or adapt if you have a direct URL
            absolute_path = params['file_path']
            if not os.path.isabs(absolute_path):
                absolute_path = os.path.join(settings.MEDIA_ROOT, absolute_path)
            if 'file_path' in params:
                files = {"photo": open(absolute_path, 'rb')}
                params.pop('file_path', None)
            # If there's textual caption
            if 'text' in params:
                params['caption'] = params['text']
                params.pop('text', None)
            params.pop('type', None)
            params.pop('image_base64', None)

        # Otherwise fallback to a basic text message
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage"

    else:
        # If 'type' not present, treat it like a standard text message
        url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage"
        msg_type = 'text'

    retries = 0
    while retries <= max_retries:
        print(f"DEBUG: Attempt {retries} to send telegram message with params: {params}")

        # Convert reply_markup to JSON string for the API call if it exists
        request_params = params.copy()
        if 'reply_to_message_id' in request_params:
            request_params['reply_to_message_id'] = _extract_telegram_message_id(request_params['reply_to_message_id'])
        if 'reply_markup' in request_params:
            import json
            request_params['reply_markup'] = json.dumps(request_params['reply_markup'])

        response = requests.post(url, data=request_params, files=files)
        ret = response.json()

        if ret.get('ok'):
            # Preserve audio_id if it exists
            if msg_type == 'audio' and 'audio_id' in locals():
                ret['result']['audio_id'] = audio_id
            # If media was sent, ensure the file is saved to media folder and pass its path
            # locals() returns a dictionary of the current local symbol table, containing all local variables.
            # Here we check if 'file_path' exists as a local variable in the current function scope
            if 'type' in params and 'file_path' in locals():
                msg_type = params['type']
                if msg_type in ['audio', 'image']:
                    # Save a copy to media folder if not already there
                    orig_path = file_path
                    # If not already in media folder, copy it
                    if not orig_path.startswith('media/'):
                        ext = os.path.splitext(orig_path)[-1]
                        new_name = f"{uuid.uuid4()}{ext}"
                        dest_path = os.path.join(settings.MEDIA_ROOT, 'media', new_name)
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        shutil.copy2(orig_path, dest_path)
                        media_file_path = f"media/{new_name}"
                    else:
                        media_file_path = orig_path
                    # Add to result dict for save_telegram_message
                    ret['result']['media_file_path'] = media_file_path
            
            return save_telegram_message(channel, ret.get('result'), user)
        elif 'error_code' in ret and ret['error_code'] == 429:  # Rate limit
            time.sleep(retry_interval)
            retries += 1
        elif 'error_code' in ret and ret['error_code'] == 400 and params.get("parse_mode") == "Markdown":
            text_field_key = "caption" if msg_type == "image" else "text"
            # Common "can't parse" error, so try escaping or cropping
            print("Send telegram message failed with status 400 while parse_mode is Markdown", ret)
            if 'message is too long' in ret.get('description', ''):
                print(f"Message length: {len(params[text_field_key])}")
                cropping_footer = "\n\n… Message Cropped"
                params[text_field_key] = params[text_field_key][:4095 - len(cropping_footer)] + cropping_footer
            elif "Can't find end of the entity starting at byte offset" in ret.get('description', ''):
                # Extract mentioned byte offset from error message
                byte_offset = int(ret['description'].split("byte offset")[1].split()[0])
                print(f"Byte offset: {byte_offset}")
                mentioned_char = params[text_field_key][byte_offset]
                print(f"Mentioned char that's causing the error: \"{mentioned_char}\"")
                if text_field_key in params:
                    params[text_field_key] = escape_markdown(params[text_field_key])
            elif "file must be non-empty" in ret.get('description', ''):
                # Handle empty file case
                print("Empty file error, files: ", files)
            else:
                if text_field_key in params:
                    params[text_field_key] = escape_markdown(params[text_field_key])
            retries += 1
        else:
            print(params)
            print(ret)
            raise Exception("Failed to send telegram message")

    raise Exception("Failed to send telegram message after maximum retries")
