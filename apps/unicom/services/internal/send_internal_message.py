from unicom.models import Message, Chat
from unicom.services.internal.save_internal_message import save_internal_message
from unicom.services.internal.generate_text_message_data import generate_text_message_data
from django.contrib.auth.models import User


def send_internal_message(params: dict, user: User=None):
    msg_type = params.pop("type", None)
    file_path = params.pop("file_path", None)

    if "text" in params:
        params["msg"] = params.pop("text")

    if "reply_to_message_id" in params and Message.objects.filter(id=params["reply_to_message_id"]).exists():
        quoted_message = Message.objects.get(id=params["reply_to_message_id"])
        if quoted_message.target_function:
            params["sender_id"] = f"function.{quoted_message.target_function.id}"
            params["sender_name"] = quoted_message.target_function.name
        if "chat_id" not in params:
            params["chat_id"] = quoted_message.chat_id
        if "chat_name" not in params:
            try:
                chat = Chat.objects.get(id=params["chat_id"])
                params["chat_name"] = chat.name
            except Exception:
                print(f"send_internal_message failed to retrieve chat_name. "
                      f"Chat object with id {params['chat_id']} not found")

    # For backwards compatibility, we set is_bot in the from data
    # but the save_internal_message will use it as is_outgoing
    if "is_outgoing" not in params:
        params["is_outgoing"] = True

    msg_data = generate_text_message_data(**params)

    # If it was an image or audio, attach them
    if msg_type:
        msg_data["media_type"] = msg_type  # 'text', 'image', or 'audio'

    if file_path:
        # This is the relative path "media/<filename>"
        msg_data["media"] = file_path

    return save_internal_message(msg_data, user)
