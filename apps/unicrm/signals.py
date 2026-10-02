from __future__ import annotations

import logging
from typing import Iterable, Sequence

from django.contrib.auth import get_user_model

from django.db.models.signals import post_delete, post_migrate, post_save
from django.dispatch import receiver
from django.utils import timezone

from unicom.models import Message
from unicrm.models import Communication, CommunicationMessage, Contact, Segment
from unicrm.seed_data import ensure_default_segments, ensure_unicrm_bot_assets
from unicrm.services.communication_enrollment import enroll_contact_in_evergreen_communications
from unicrm.services.communication_scheduler import prepare_deliveries_for_communication
from unicrm.services.contact_interaction_cache import refresh_contact_cache
from unicrm.services.user_contact_sync import (
    ensure_contact_for_user,
    sync_all_user_contacts,
)


logger = logging.getLogger(__name__)
_BOUNCE_UPDATE_FIELDS = {'email_bounced', 'email_bounced_at', 'email_bounce_type', 'updated_at'}

def _affected_communications(messages: Iterable[CommunicationMessage]):
    seen = set()
    for item in messages:
        if item.communication_id in seen:
            continue
        seen.add(item.communication_id)
        yield item.communication


def _refresh_communications(objs: Iterable[CommunicationMessage]):
    for communication in _affected_communications(objs):
        communication.refresh_status_summary()


def _refresh_contact_bounce_cache(objs: Sequence[CommunicationMessage]) -> None:
    contact_ids = {obj.contact_id for obj in objs if obj.contact_id}
    if not contact_ids:
        return

    for contact in Contact.objects.filter(pk__in=contact_ids):
        latest_bounce = (
            CommunicationMessage.objects.filter(contact=contact, message__bounced=True)
            .select_related('message')
            .order_by('-message__time_bounced', '-message__time_sent', '-message__timestamp', '-created_at')
            .first()
        )
        has_bounce = bool(latest_bounce and latest_bounce.message)
        bounce_message = latest_bounce.message if latest_bounce else None
        bounce_at = None
        bounce_type = ''
        if bounce_message:
            bounce_at = (
                bounce_message.time_bounced
                or bounce_message.time_sent
                or bounce_message.timestamp
            )
            bounce_type = bounce_message.bounce_type or ''

        updates: list[str] = []
        if contact.email_bounced != has_bounce:
            contact.email_bounced = has_bounce
            updates.append('email_bounced')
        if contact.email_bounced_at != bounce_at:
            contact.email_bounced_at = bounce_at
            updates.append('email_bounced_at')
        normalized_type = bounce_type or ''
        if contact.email_bounce_type != normalized_type:
            contact.email_bounce_type = normalized_type
            updates.append('email_bounce_type')

        if updates:
            contact.save(update_fields=updates + ['updated_at'])


def _mark_deliveries_replied(message: Message) -> list[CommunicationMessage]:
    """
    Identify and update deliveries that have received a reply for the given incoming message.
    """
    if message.is_outgoing is not False:
        return []

    deliveries: list[CommunicationMessage] = []
    if message.reply_to_message_id:
        deliveries = list(
            CommunicationMessage.objects
            .filter(message_id=message.reply_to_message_id)
            .select_related('communication', 'contact')
        )

    if not deliveries and message.chat_id:
        deliveries = list(
            CommunicationMessage.objects
            .filter(message__chat_id=message.chat_id, message__isnull=False)
            .select_related('communication', 'contact')
            .order_by('-message__timestamp')[:1]
        )

    if not deliveries:
        return []

    reply_time = (
        message.timestamp
        or message.time_sent
        or message.time_delivered
        or timezone.now()
    )

    updated: list[CommunicationMessage] = []
    for delivery in deliveries:
        metadata = delivery.metadata or {}
        replies = metadata.setdefault('replies', [])
        changed_fields: set[str] = set()

        if message.id and message.id not in replies:
            replies.append(message.id)
            metadata['replies'] = replies
            changed_fields.add('metadata')

        if message.chat_id and metadata.get('chat_id') != message.chat_id:
            metadata['chat_id'] = message.chat_id
            changed_fields.add('metadata')

        if not delivery.has_received_reply:
            delivery.has_received_reply = True
            changed_fields.add('has_received_reply')

        if reply_time:
            if not delivery.replied_at or reply_time > delivery.replied_at:
                delivery.replied_at = reply_time
                changed_fields.add('replied_at')

        if not changed_fields:
            continue

        if 'metadata' in changed_fields:
            delivery.metadata = metadata
        update_fields = list(dict.fromkeys([field for field in changed_fields if field != 'metadata']))
        # Always persist metadata if we touched it.
        if 'metadata' in changed_fields:
            update_fields.append('metadata')
        update_fields.append('updated_at')
        delivery.save(update_fields=update_fields)
        updated.append(delivery)

    return updated


@receiver(post_save, sender=Contact)
def contact_saved_auto_enroll(sender, instance: Contact, created: bool, update_fields=None, raw=False, **kwargs):
    if raw:
        return

    if update_fields:
        normalized = {field for field in update_fields if field}
        if normalized and normalized.issubset(_BOUNCE_UPDATE_FIELDS):
            return
        # Avoid recursion when only the communication history/cache was updated
        if normalized.issubset({'communication_history', 'updated_at'}):
            return

    enroll_contact_in_evergreen_communications(instance)


@receiver(post_save, sender=CommunicationMessage)
def communication_message_saved(sender, instance: CommunicationMessage, **kwargs):
    _refresh_communications([instance])
    _refresh_contact_bounce_cache([instance])
    if instance.contact_id:
        refresh_contact_cache(instance.contact)


@receiver(post_delete, sender=CommunicationMessage)
def communication_message_deleted(sender, instance: CommunicationMessage, **kwargs):
    _refresh_communications([instance])
    _refresh_contact_bounce_cache([instance])
    if instance.contact_id:
        refresh_contact_cache(instance.contact)


@receiver(post_save, sender=Message)
def message_saved(sender, instance: Message, **kwargs):
    linked = list(CommunicationMessage.objects.filter(message=instance))

    deliveries_to_update: list[CommunicationMessage] = []
    if linked:
        for delivery in linked:
            metadata = delivery.metadata or {}
            current_status = (metadata.get('status') or '').lower()
            if instance.bounced and current_status != 'bounced':
                metadata['status'] = 'bounced'
                delivery.metadata = metadata
                deliveries_to_update.append(delivery)
            elif not instance.bounced and current_status == 'bounced':
                if getattr(instance, 'sent', False):
                    metadata['status'] = 'sent'
                else:
                    metadata.pop('status', None)
                delivery.metadata = metadata
                deliveries_to_update.append(delivery)

        for delivery in deliveries_to_update:
            delivery.save(update_fields=['metadata', 'updated_at'])

        _refresh_communications(linked)
        _refresh_contact_bounce_cache(linked)
        for delivery in deliveries_to_update:
            if delivery.contact_id:
                refresh_contact_cache(delivery.contact)

    replied_updates = _mark_deliveries_replied(instance)
    if replied_updates:
        _refresh_communications(replied_updates)
        for delivery in replied_updates:
            if delivery.contact_id:
                refresh_contact_cache(delivery.contact)


@receiver(post_save, sender=Segment)
def segment_saved_sync_evergreen(sender, instance: Segment, created: bool, raw=False, **kwargs):
    if raw:
        return

    communications = (
        Communication.objects
        .filter(segment=instance, auto_enroll_new_contacts=True)
        .exclude(status='cancelled')
        .select_related('segment', 'channel', 'initiated_by')
    )
    for communication in communications:
        if not communication.channel:
            continue
        try:
            prepare_deliveries_for_communication(communication)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(
                "Failed refreshing deliveries for communication %s after segment update: %s",
                communication.pk,
                exc,
            )


@receiver(post_migrate)
def create_default_segments(sender, **kwargs):
    if sender.label != 'unicrm':
        return

    ensure_default_segments()
    sync_all_user_contacts()
    ensure_unicrm_bot_assets()


UserModel = get_user_model()


@receiver(post_save, sender=UserModel)
def user_saved(sender, instance, **kwargs):
    ensure_contact_for_user(instance)
