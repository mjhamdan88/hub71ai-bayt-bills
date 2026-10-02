from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from unicom.models import Update, Channel
from unicom.services.telegram.save_telegram_message import save_telegram_message
from unicom.services.telegram.handle_telegram_callback import handle_telegram_callback
from django.db import transaction
import json


@csrf_exempt
def telegram_webhook(request, bot_id: int):
    # Only accept POST requests
    if request.method != 'POST':
        return HttpResponse('Invalid request method.', status=405)

    # Lookup the Channel for this webhook
    channel = get_object_or_404(Channel, pk=bot_id, platform='Telegram')

    # Verify the request using the optional secret token
    secret_token = channel.config.get('TELEGRAM_SECRET_TOKEN')
    if secret_token:
        header_token = request.META.get('HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN')
        if header_token != secret_token:
            return HttpResponseForbidden('Invalid secret token.')

    # Parse JSON payload
    try:
        data_dict = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponse('Invalid JSON.', status=400)

    # Save the raw update (use get_or_create to handle duplicate updates from Telegram)
    update, created = Update.objects.get_or_create(
        id=f'Telegram.{data_dict.get("update_id")}',
        defaults={
            'channel': channel,
            'platform': 'Telegram',
            'payload': data_dict
        }
    )

    if not created:
        print(f"⚠️ Duplicate update received: {update.id}")
        # If it's a duplicate, just return success without reprocessing
        return HttpResponse('Duplicate update ignored.', status=200)

    # Handle callback queries (buttons)
    if 'callback_query' in data_dict:
        with transaction.atomic():
            processed = handle_telegram_callback(channel, data_dict['callback_query'])
            update.callback_processed = processed
            update.save()
        return HttpResponse('Callback processed.' if processed else 'Callback ignored.', status=200)

    # Handle incoming messages
    if 'message' in data_dict:
        with transaction.atomic():
            msg = save_telegram_message(channel, data_dict['message'])
            update.message = msg
            # Mark update as from blocked account if no message was saved
            if msg is None:
                update.from_blocked_account = True
            update.save()
        return HttpResponse('Message received and saved.', status=200)

    # Fallback for other update types
    print(f"Received unknown update type: {update.id}")
    return HttpResponse('Update received.', status=200)
