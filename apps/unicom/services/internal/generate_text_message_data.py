import uuid
from time import time


def generate_text_message_data(sender_id:str, sender_name:str, is_outgoing:bool, chat_id:str, chat_name:str, msg:str, reply_to_message_id=None):
    message_data = {
        "from": {
            "id": sender_id,
            "first_name": sender_name,
            "is_bot": is_outgoing  # Keep is_bot in from data for backwards compatibility
        },
        "chat": {
            "id": chat_id,
            "type": "private",
            "title": chat_name
        },
        "message_id": f"internal.{chat_id}.{sender_id}.{uuid.uuid4()}",
        "text": msg,
        "date": time()
    }
    if reply_to_message_id is not None:
        message_data["reply_to_message"] = {"message_id": reply_to_message_id}
    return message_data