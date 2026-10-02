import random
import time
from typing import Any, Dict

from django.dispatch import receiver

from unicom.signals import interactive_button_clicked, telegram_callback_received
from unicrm.models import Contact, MailingList, Subscription
from unibot.models import EncryptedCredential


def _handle(button_data: Dict[str, Any], clicking_account, original_message, tool_call):
    if not isinstance(button_data, dict):
        return
    if button_data.get("tool") != "save_new_leads":
        return

    action = button_data.get("action")
    insight_ids = button_data.get("insight_ids") or []
    mailing_list_slug = (button_data.get("mailing_list_slug") or "").strip()
    mailing_list_name = button_data.get("mailing_list_name") or ""
    mailing_list_public_name = button_data.get("mailing_list_public_name") or ""
    mailing_list_description = button_data.get("mailing_list_description") or ""

    if action == "cancel":
        original_message.reply_with({"text": "Cancelled. No leads were saved."})
        if tool_call:
            tool_call.respond({"error": "User cancelled.", "saved": 0}, status="ERROR")
        return True

    if action != "confirm":
        original_message.reply_with({"text": "Unknown action for save_new_leads."})
        if tool_call:
            tool_call.respond({"error": "Unknown action.", "saved": 0}, status="ERROR")
        return True

    if not mailing_list_slug:
        msg = "mailing_list_slug is required."
        original_message.reply_with({"text": f"❌ {msg}"})
        if tool_call:
            tool_call.respond({"error": msg, "saved": 0}, status="ERROR")
        return True

    contacts = list(Contact.objects.filter(insight_id__in=insight_ids))
    found_ids = {c.insight_id for c in contacts}
    missing = [iid for iid in insight_ids if iid not in found_ids]
    if missing:
        msg = f"Missing contacts for insight_ids: {', '.join(missing)}"
        original_message.reply_with({"text": f"❌ {msg}"})
        if tool_call:
            tool_call.respond({"success": False, "error": msg, "saved": 0})
        return True

    mailing_list = MailingList.objects.filter(slug=mailing_list_slug).first()
    created_list = False
    if not mailing_list:
        name = mailing_list_name or mailing_list_public_name or mailing_list_slug.replace("-", " ").title() or mailing_list_slug
        public_name = mailing_list_public_name or mailing_list_name or name
        mailing_list = MailingList.objects.create(
            name=name,
            public_name=public_name,
            slug=mailing_list_slug,
            description=mailing_list_description,
        )
        created_list = True

    # Add/activate subscriptions
    added_to_list = 0
    already_on_list = 0
    for contact in contacts:
        sub, created_sub = Subscription.objects.get_or_create(contact=contact, mailing_list=mailing_list)
        if created_sub or sub.unsubscribed_at is not None:
            sub.unsubscribed_at = None
            sub.unsubscribe_feedback = ""
            sub.save(update_fields=["unsubscribed_at", "unsubscribe_feedback", "updated_at"])
            added_to_list += 1
        else:
            already_on_list += 1

    contacts_missing_email = [c for c in contacts if not c.email]

    cred = EncryptedCredential.objects.filter(account=clicking_account, key="GETPROSPECT_API_KEY").first()
    api_key = cred.decrypted_value if cred else None
    if not api_key:
        msg = "GETPROSPECT_API_KEY is not configured for this account. Contacts were added to the mailing list, but no email requests were sent."
        original_message.reply_with({"text": f"❌ {msg}"})
        if tool_call:
            tool_call.respond(
                {
                    "error": msg,
                    "saved": 0,
                    "mailing_list_id": mailing_list.id,
                    "mailing_list_slug": mailing_list.slug,
                    "added_to_list": added_to_list,
                    "already_on_list": already_on_list,
                    "created_mailing_list": created_list,
                    "credits_used": 0,
                },
                status="WARNING",
            )
        return True

    success_count = 0
    for c in contacts_missing_email:
        attrs = c.attributes or {}
        attrs['email_request_queued'] = True
        Contact.objects.filter(pk=c.pk).update(attributes=attrs)
        success_count += 1

    total_active = mailing_list.subscriptions.filter(unsubscribed_at__isnull=True).count()
    msg = (
        f"Mailing list '{mailing_list.name}' (slug: {mailing_list.slug}) "
        f"{'created and ' if created_list else ''}updated.\n"
        f"Added/activated: {added_to_list} | Already on list: {already_on_list} | Active total: {total_active}.\n"
        f"Queued {success_count} lead(s) for email requests (skipped {len(contacts) - len(contacts_missing_email)} already with email)."
    )
    original_message.reply_with({"text": msg})

    if tool_call:
        tool_call.respond(
            {
                "saved": success_count,
                "mailing_list_id": mailing_list.id,
                "mailing_list_slug": mailing_list.slug,
                "added_to_list": added_to_list,
                "already_on_list": already_on_list,
                "created_mailing_list": created_list,
                "credits_used": 0,  # Will be updated by background process
            }
        )
    return True


@receiver(telegram_callback_received)
def handle_save_new_leads_telegram(sender, callback_execution, clicking_account, original_message, tool_call, **kwargs):
    _handle(callback_execution.callback_data, clicking_account, original_message, tool_call)


@receiver(interactive_button_clicked)
def handle_save_new_leads_webchat(sender, callback_execution, clicking_account, original_message, platform, tool_call, **kwargs):
    _handle(callback_execution.callback_data, clicking_account, original_message, tool_call)
