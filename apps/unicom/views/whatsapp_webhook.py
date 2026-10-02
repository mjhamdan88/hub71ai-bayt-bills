from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from unicom.models import Update
from unicom.services.whatsapp.save_whatsapp_message import save_whatsapp_message
from unicom.services.whatsapp.save_whatsapp_message_status import save_whatsapp_message_status
from django.db import transaction
import hashlib
import hmac
import json


# TODO: Re-enable signature verification and subscription mechanism
@csrf_exempt
def whatsapp_webhook(request):
    if request.method == 'POST':
        signature = request.headers.get('X-Hub-Signature-256', '').split('=')[1]
        # computed_signature = hmac.new(FACEBOOK_APP_SECRET.encode(), request.body, hashlib.sha256).hexdigest()
        # if not hmac.compare_digest(computed_signature, signature):
        #     print("Invalid Signature!")
        #     JsonResponse({'status': 'verification failed'}, status=403)
        data = request.body.decode('utf-8')
        data_dict = json.loads(data)
        if data_dict.get("object") != "whatsapp_business_account":
            JsonResponse({'status': 'Error 430'}, status=500)
        notification_objects = data_dict.get("entry")
        if len(notification_objects) != 1:
            JsonResponse({'status': 'Error 431'}, status=500)
        update = Update(platform='WhatsApp', id=f'WhatsApp.{signature}', payload=data_dict)
        update.save()
        
    
        for notification_object in notification_objects:
            changes = notification_object["changes"]
            for change in changes:
                if change["field"] == 'messages':
                    change_value = change["value"]
                    if "messages" in change_value:
                        with transaction.atomic():
                            msg = save_whatsapp_message(change_value)
                            update.message = msg
                            # Mark update as from blocked account if no message was saved
                            if msg is None:
                                update.from_blocked_account = True
                            update.save()
                    if "statuses" in change_value:
                        with transaction.atomic():
                            msg = save_whatsapp_message_status(change_value)
                            update.message = msg
                            update.save()

        return JsonResponse({'status': 'Update Received'}, status=200)
    # if request.method == 'GET' and request.GET.get('hub.mode', 'null') == 'subscribe':
    #     if WHATSAPP_VERIFY_TOKEN is not None and WHATSAPP_VERIFY_TOKEN == request.GET.get('hub.verify_token', 'null'):
    #         challenge = request.GET.get('hub.challenge', 'null')
    #         return HttpResponse(challenge)

    return HttpResponse('Invalid request method.')
