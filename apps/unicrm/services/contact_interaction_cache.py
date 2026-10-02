from __future__ import annotations

from typing import Iterable, List

from django.utils import timezone

from unicrm.models import CommunicationMessage, Contact


def _status_from_delivery(delivery: CommunicationMessage) -> str:
    metadata = delivery.metadata or {}
    status = (delivery.status or '').strip() or (metadata.get('status') or '').strip()
    if status:
        return status
    if delivery.message_id:
        return 'sent'
    return 'scheduled'


def _entry_from_delivery(delivery: CommunicationMessage) -> dict:
    message = delivery.message
    communication = delivery.communication
    channel = getattr(communication, 'channel', None)
    metadata = delivery.metadata or {}
    payload = metadata.get('payload') or {}

    subject = None
    if message and message.subject:
        subject = message.subject
    elif payload:
        subject = payload.get('subject')
    elif communication and communication.subject_template:
        subject = communication.subject_template

    status = _status_from_delivery(delivery)
    direction = 'outbound'
    if message is not None and message.is_outgoing is False:
        direction = 'inbound'

    sent_at = None
    opened_at = None
    clicked_at = None
    replied_at = None
    bounced_at = None
    has_received_reply = bool(getattr(delivery, 'has_received_reply', False))

    if message:
        sent_at = message.time_sent or message.timestamp
        opened_at = message.time_opened or message.time_seen
        if not opened_at and getattr(message, 'opened', False):
            opened_at = sent_at or message.timestamp

        clicked_at = message.time_link_clicked
        if not clicked_at and (getattr(message, 'link_clicked', False) or getattr(message, 'clicked_links', None)):
            clicked_at = sent_at or message.timestamp

        bounced_at = message.time_bounced
        if delivery.replied_at:
            replied_at = delivery.replied_at
            has_received_reply = True
    else:
        # fall back to scheduled time if no message yet
        sent_at = delivery.scheduled_at or communication.scheduled_for

    return {
        'communication_id': communication.pk if communication else None,
        'communication_status': getattr(communication, 'status', None),
        'message_id': message.pk if message else None,
        'direction': direction,
        'channel': getattr(channel, 'platform', None),
        'status': status,
        'subject': subject,
        'sent_at': sent_at.isoformat() if sent_at else None,
        'opened_at': opened_at.isoformat() if opened_at else None,
        'clicked_at': clicked_at.isoformat() if clicked_at else None,
        'replied_at': replied_at.isoformat() if replied_at else None,
        'bounced_at': bounced_at.isoformat() if bounced_at else None,
        'has_received_reply': has_received_reply,
        'created_at': delivery.created_at.isoformat() if delivery.created_at else None,
    }


def compute_history_for_contact(contact: Contact) -> List[dict]:
    deliveries = (
        CommunicationMessage.objects
        .filter(contact=contact)
        .exclude(status__in=['failed', 'bounced'])
        .select_related('communication', 'communication__channel', 'message')
        .order_by('-created_at')
    )
    history: List[dict] = []
    for delivery in deliveries:
        entry = _entry_from_delivery(delivery)
        if (entry.get('status') or '').lower() in {'failed', 'bounced'}:
            continue
        history.append(entry)
    return history


def refresh_contact_cache(contact: Contact, *, commit: bool = True) -> list[dict]:
    history = compute_history_for_contact(contact)
    contact.communication_history = history
    if commit:
        contact.save(update_fields=['communication_history', 'updated_at'])
    return history


def refresh_contacts_bulk(contacts: Iterable[Contact], *, commit: bool = True) -> None:
    now = timezone.now()
    for contact in contacts:
        contact.communication_history = compute_history_for_contact(contact)
        if commit:
            contact.updated_at = now
            contact.save(update_fields=['communication_history', 'updated_at'])
