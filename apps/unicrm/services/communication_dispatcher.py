from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List
from datetime import timedelta

from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from unicrm.models import Communication, CommunicationMessage
from django.conf import settings

from unicrm.services.communication_scheduler import (
    prepare_deliveries_for_communication,
    refresh_delivery_for_sending,
)

try:  # pragma: no cover - optional dependency during migrations
    from unicom.services.email.IMAP_thread_manager import imap_manager
except Exception:  # pragma: no cover - fallback when email module unavailable
    imap_manager = None

MessageModel = CommunicationMessage._meta.get_field('message').remote_field.model

logger = logging.getLogger(__name__)


@dataclass
class CommunicationDispatchSummary:
    communications_examined: int = 0
    communications_processed: int = 0
    messages_sent: int = 0
    messages_failed: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            'communications_examined': self.communications_examined,
            'communications_processed': self.communications_processed,
            'messages_sent': self.messages_sent,
            'messages_failed': self.messages_failed,
        }


def _refresh_evergreen_communications(
    *,
    current_time,
    communications_examined_ids: set[int],
    touched_communications: Dict[int, Communication],
    details: List[Dict[str, Any]],
) -> None:
    """
    Periodically re-run auto-enroll segments so time-based criteria stay in sync.
    """
    try:
        interval_seconds = int(getattr(settings, 'UNICRM_EVERGREEN_REFRESH_INTERVAL_SECONDS', 300))
    except (TypeError, ValueError):
        interval_seconds = 300
    interval_seconds = max(0, interval_seconds)

    try:
        batch_size = int(getattr(settings, 'UNICRM_EVERGREEN_REFRESH_BATCH_SIZE', 25))
    except (TypeError, ValueError):
        batch_size = 25
    batch_size = max(1, batch_size)

    evergreen_qs = (
        Communication.objects
        .filter(auto_enroll_new_contacts=True)
        .exclude(status='cancelled')
        .filter(
            Q(status='ongoing') |
            Q(status='scheduled', scheduled_for__gt=current_time)
        )
        .filter(channel__isnull=False)
    )

    if interval_seconds > 0:
        threshold = current_time - timedelta(seconds=interval_seconds)
        evergreen_qs = evergreen_qs.filter(
            Q(evergreen_refreshed_at__lt=threshold) | Q(evergreen_refreshed_at__isnull=True)
        )

    evergreen_ids = list(
        evergreen_qs
        .order_by('evergreen_refreshed_at', 'pk')
        .values_list('pk', flat=True)[:batch_size]
    )

    for communication_id in evergreen_ids:
        with transaction.atomic():
            try:
                communication = (
                    Communication.objects
                    .select_for_update(skip_locked=True)
                    .select_related('segment')
                    .prefetch_related('channel', 'initiated_by')
                    .get(pk=communication_id)
                )
            except Communication.DoesNotExist:
                continue

            if (
                not communication.auto_enroll_new_contacts
                or communication.status == 'cancelled'
                or not communication.channel
            ):
                continue

            if (
                communication.status == 'scheduled'
                and communication.scheduled_for
                and communication.scheduled_for <= current_time
            ):
                continue

            communications_examined_ids.add(communication.pk)
            touched_communications[communication.pk] = communication

            try:
                result = prepare_deliveries_for_communication(communication)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception(
                    "Failed refreshing evergreen communication %s: %s",
                    communication.pk,
                    exc,
                )
                details.append({
                    'communication_id': communication.pk,
                    'contact_id': None,
                    'contact_email': None,
                    'status': 'preparation_error',
                    'subject': None,
                    'html': None,
                    'errors': [str(exc)],
                    'note': 'evergreen_refresh_error',
                })
                continue

            if result.errors:
                for err in result.errors:
                    details.append({
                        'communication_id': communication.pk,
                        'contact_id': None,
                        'contact_email': None,
                        'status': 'preparation_error',
                        'subject': None,
                        'html': None,
                        'errors': [err],
                        'note': 'evergreen_refresh_error',
                    })


def process_scheduled_communications(now=None, verbosity: int = 0) -> Dict[str, int]:
    """Send communications that are due, preparing each delivery on demand."""
    summary = CommunicationDispatchSummary()

    current_time = now or timezone.now()
    communications_examined_ids: set[int] = set()
    communications_stats: Dict[int, Dict[str, int]] = defaultdict(lambda: {'sent': 0, 'failed': 0})
    details: List[Dict[str, Any]] = []
    touched_communications: Dict[int, Communication] = {}

    _refresh_evergreen_communications(
        current_time=current_time,
        communications_examined_ids=communications_examined_ids,
        touched_communications=touched_communications,
        details=details,
    )

    due_ids = list(
        Communication.objects
        .filter(status='scheduled', scheduled_for__isnull=False, scheduled_for__lte=current_time)
        .values_list('id', flat=True)
    )

    for communication_id in due_ids:
        with transaction.atomic():
            try:
                communication = (
                    Communication.objects
                    .select_for_update(skip_locked=True)
                    .select_related('segment')
                    .prefetch_related('channel', 'initiated_by')
                    .get(pk=communication_id)
                )
            except Communication.DoesNotExist:
                continue

            if (
                communication.status != 'scheduled'
                or communication.scheduled_for is None
                or communication.scheduled_for > current_time
            ):
                continue

            communications_examined_ids.add(communication.pk)
            communications_stats[communication.pk]  # prime entry
            touched_communications[communication.pk] = communication

            if not communication.channel:
                logger.warning(
                    "Communication %s has no channel assigned; skipping dispatch.",
                    communication.pk,
                )
                details.append({
                    'communication_id': communication.pk,
                    'contact_id': None,
                    'contact_email': None,
                    'status': 'skipped',
                    'subject': None,
                    'html': None,
                    'errors': ['Channel missing'],
                    'note': 'no_channel',
                })
                continue

            result = prepare_deliveries_for_communication(communication)
            if result.errors:
                for err in result.errors:
                    details.append({
                        'communication_id': communication.pk,
                        'contact_id': None,
                        'contact_email': None,
                        'status': 'preparation_error',
                        'subject': None,
                        'html': None,
                        'errors': [err],
                        'note': 'delivery_preparation_error',
                    })
            touched_communications[communication.pk] = communication

            if (
                imap_manager is not None
                and getattr(settings, 'ENABLE_IMAP_AUTOSTART', True)
                and communication.channel
                and communication.channel.platform == 'Email'
            ):
                imap_manager.start(communication.channel)

            communication.refresh_status_summary()

    batch_size = getattr(settings, 'UNICRM_DISPATCH_BATCH_SIZE', 100)
    pending_queryset = (
        CommunicationMessage.objects
        .filter(status='scheduled')
        .filter(
            Q(scheduled_at__isnull=True) | Q(scheduled_at__lte=current_time)
        )
        .order_by('scheduled_at', 'pk')
    )

    while True:
        pending_ids = list(pending_queryset.values_list('pk', flat=True)[:batch_size])
        if not pending_ids:
            break

        for message_id in pending_ids:
            with transaction.atomic():
                base_qs = (
                    CommunicationMessage.objects
                    .select_for_update(skip_locked=True)
                    .select_related('communication', 'communication__segment', 'contact')
                    .prefetch_related('communication__channel', 'communication__initiated_by')
                )
                try:
                    delivery = base_qs.get(pk=message_id)
                except CommunicationMessage.DoesNotExist:
                    continue

                communication = delivery.communication
                communications_examined_ids.add(communication.pk)
                touched_communications[communication.pk] = communication
                stats = communications_stats[communication.pk]

                metadata: Dict[str, Any] = delivery.metadata or {}
                payload: Dict[str, Any] = metadata.get('payload') or {}

                record: Dict[str, Any] = {
                    'communication_id': communication.pk,
                    'contact_id': delivery.contact_id,
                    'contact_email': getattr(delivery.contact, 'email', None),
                    'status': delivery.status,
                    'subject': payload.get('subject'),
                    'html': payload.get('html'),
                    'errors': list(metadata.get('errors', [])),
                }

                if delivery.status != 'scheduled':
                    record['note'] = f"already_{delivery.status}"
                    details.append(record)
                    continue

                if delivery.scheduled_at and delivery.scheduled_at > current_time:
                    record['note'] = 'scheduled_in_future'
                    details.append(record)
                    continue

                if communication.status == 'cancelled' or not communication.channel:
                    errors = metadata.setdefault('errors', [])
                    if 'Channel missing' not in errors and not communication.channel:
                        errors.append('Channel missing')
                    metadata['status'] = 'failed'
                    delivery.metadata = metadata
                    delivery.status = 'failed'
                    delivery.scheduled_at = delivery.scheduled_at or current_time
                    delivery.save(update_fields=['metadata', 'status', 'scheduled_at', 'updated_at'])
                    stats['failed'] += 1
                    record['status'] = 'failed'
                    record['errors'] = list(errors)
                    record['note'] = 'no_channel' if not communication.channel else 'communication_cancelled'
                    details.append(record)
                    continue

                outcome = refresh_delivery_for_sending(
                    delivery,
                    send_at=delivery.scheduled_at or communication.scheduled_for or current_time,
                )
                delivery = outcome.delivery
                metadata = delivery.metadata or {}
                payload = metadata.get('payload') or {}

                record['status'] = delivery.status
                record['subject'] = payload.get('subject')
                record['html'] = payload.get('html')
                record['errors'] = list(metadata.get('errors', []))

                if delivery.status in {'skipped', 'bounced'}:
                    record['note'] = f'auto_{delivery.status}'
                    delivery.save(update_fields=['metadata', 'status', 'scheduled_at', 'updated_at'])
                    details.append(record)
                    continue

                if not payload:
                    record['note'] = 'no_payload'
                    details.append(record)
                    continue

                if (
                    imap_manager is not None
                    and getattr(settings, 'ENABLE_IMAP_AUTOSTART', True)
                    and communication.channel.platform == 'Email'
                ):
                    imap_manager.start(communication.channel)

                try:
                    message_instance = communication.channel.send_message(
                        payload,
                        user=communication.initiated_by,
                    )
                    metadata['status'] = 'sent'
                    metadata.pop('errors', None)
                    delivery.status = 'sent'
                    delivery.scheduled_at = delivery.scheduled_at or current_time
                    if isinstance(message_instance, MessageModel):
                        delivery.message = message_instance
                        if getattr(message_instance, 'chat_id', None):
                            metadata['chat_id'] = message_instance.chat_id
                    stats['sent'] += 1
                    record['status'] = 'sent'
                    record['errors'] = []
                except Exception as exc:  # pragma: no cover - defensive
                    errors = metadata.setdefault('errors', [])
                    err_text = str(exc)
                    if err_text not in errors:
                        errors.append(err_text)
                    metadata['status'] = 'failed'
                    delivery.status = 'failed'
                    delivery.scheduled_at = delivery.scheduled_at or current_time
                    stats['failed'] += 1
                    record['status'] = 'failed'
                    record.setdefault('errors', []).append(err_text)
                    logger.exception(
                        "Failed sending payload for communication %s (contact %s).",
                        communication.pk,
                        delivery.contact_id,
                    )

                delivery.metadata = metadata
                delivery.save(update_fields=['metadata', 'status', 'message', 'scheduled_at', 'updated_at'])
                details.append(record)

    for communication in touched_communications.values():
        communication.refresh_status_summary()

    summary.communications_examined = len(communications_examined_ids)
    summary.messages_sent = sum(stats['sent'] for stats in communications_stats.values())
    summary.messages_failed = sum(stats['failed'] for stats in communications_stats.values())
    summary.communications_processed = sum(
        1 for stats in communications_stats.values() if stats['sent'] or stats['failed']
    )

    result = summary.to_dict()
    result['details'] = details
    return result
