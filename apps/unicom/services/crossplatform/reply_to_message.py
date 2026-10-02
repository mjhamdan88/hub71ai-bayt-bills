from __future__ import annotations
from typing import TYPE_CHECKING
from unicom.services.telegram.send_telegram_message import send_telegram_message
from unicom.services.whatsapp.send_whatsapp_message import send_whatsapp_message
from unicom.services.internal.send_internal_message import send_internal_message
from unicom.services.email.send_email_message import send_email_message
from unicom.services.decode_base64_image import decode_base64_media
from unicom.services.webchat.send_webchat_message import send_webchat_message
from unicom.models import Message, Channel
import uuid
import os
import warnings

if TYPE_CHECKING:
    from unicom.models import Message, Channel


def reply_to_message(channel:Channel , message: Message, response: dict) -> Message:
    """
    response can contain:
      - "type": 'text', 'audio', or 'image'
      - "text":   The text or caption
      - "html":   The HTML body for email messages
      - "file_path" or "base64_image" or "base64_audio" or "image_link"

    Special handling:
      - If 'base64_image' is present and type is 'image', decodes and saves the image to media folder, sets 'file_path'.
      - If 'base64_audio' is present and type is 'audio', decodes and saves the audio to media folder, sets 'file_path'.
    """

    tool_call_id = response.pop('_tool_call_id', None)

    # If it's an image in base64, decode it:
    if response.get("type") == "image" and "base64_image" in response:
        from unicom.services.decode_base64_image import decode_base64_media
        # Try to detect extension from base64 header if present, else default to jpg
        import re
        b64 = response["base64_image"]
        ext = "jpg"
        m = re.match(r"^data:image/(\w+);base64,(.*)$", b64)
        if m:
            ext = m.group(1)
            b64 = m.group(2)
        relative_path = decode_base64_media(b64, output_subdir="media", file_ext=ext)
        response["file_path"] = relative_path
        response.pop("base64_image")  # Remove it so we don't pass raw base64 around

    # If it's an audio in base64, decode it:
    if response.get("type") == "audio" and "base64_audio" in response:
        from unicom.services.decode_base64_image import decode_base64_media
        # Try to detect extension from base64 header if present, else default to mp3
        import re
        b64 = response["base64_audio"]
        ext = "mp3"
        m = re.match(r"^data:audio/(\w+);base64,(.*)$", b64)
        if m:
            ext = m.group(1)
            b64 = m.group(2)
        relative_path = decode_base64_media(b64, output_subdir="media", file_ext=ext)
        response["file_path"] = relative_path
        response.pop("base64_audio")  # Remove it so we don't pass raw base64 around

    # Dispatch by platform
    platform = message.platform
    if platform == 'Telegram':
        # Ensure file_path is present for media messages
        if response.get('type') in ['audio', 'image'] and 'file_path' not in response:
            # Fallback: send as text message with warning
            warnings.warn(f"Attempted to send {response.get('type')} message without file_path. Falling back to text.")
            return send_telegram_message(channel, {
                "chat_id": message.chat_id,
                "reply_to_message_id": message.id,
                "parse_mode": "Markdown",
                "text": response.get('text', '[Media file missing]')
            })
        return send_telegram_message(channel, {
            "chat_id": message.chat_id,
            "reply_to_message_id": message.id,
            "parse_mode": "Markdown",
            **response
        })
    elif platform == 'WhatsApp':
        return send_whatsapp_message({
            "chat_id": message.chat_id,
            "reply_to_message_id": message.id,
            **response
        })
    elif platform == 'Internal':
        source_function_call = message.triggered_function_calls.first()
        return send_internal_message({
            "reply_to_message_id": message.id,
            **response
        }, source_function_call=source_function_call)
    elif platform == 'WebChat':
        payload = {**response, 'chat_id': message.chat_id}
        if tool_call_id:
            payload['_tool_call_id'] = tool_call_id
        media_type = payload.pop('type', None)
        if media_type and 'media_type' not in payload:
            payload['media_type'] = media_type
        new_message = send_webchat_message(channel, payload)
        if new_message:
            new_message.reply_to_message = message
            new_message.save(update_fields=['reply_to_message'])
        return new_message
    elif platform == 'Email':
        return send_email_message(channel, {
            'reply_to_message_id' : message.id,
            'text'                : response.get('text', None),
            'html'                : response.get('html', None),
            'cc'                  : getattr(message, 'cc', []),
            'bcc'                 : getattr(message, 'bcc', []),
            'attachments'         : ([response['file_path']]
                                     if response.get('file_path') else []),
            # Enable template rendering for replies as well
            'render_template'     : True,
            'render_variables'    : response.get('render_variables'),
            'render_context'      : response.get('render_context'),
        })
    else:
        print(f"Unsupported platform: {platform}")
        return None
