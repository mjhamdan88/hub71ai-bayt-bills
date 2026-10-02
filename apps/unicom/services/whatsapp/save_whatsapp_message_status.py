from unicom.models import Message
from datetime import datetime
from django.utils import timezone


def save_whatsapp_message_status(messages_data: dict):
    platform = 'WhatsApp'  # Set the platform name
    last_message = None
    for status_data in messages_data.get("statuses"):
        message_id = f"whatsapp.{status_data.get('id')}"
        message = Message.objects.filter(platform=platform, id=message_id).first()
        timestamp = datetime.fromtimestamp(int(status_data.get('timestamp'))) if 'timestamp' in status_data else None
        if timestamp is not None:
            timestamp = timezone.make_aware(timestamp, timezone.utc)
        if not message:
            continue
        last_message = message
        status = status_data.get("status")
        if status == 'sent':
            message.timestamp = timestamp
            message.sent = True
            message.time_sent = timestamp
        elif status == 'delivered':
            message.delivered = True
            message.time_delivered = timestamp
        elif status == 'read':
            message.seen = True
            message.time_seen = timestamp
        else:
            print(f"Unknown Message Status: {status}")
        message.save()
    return last_message
