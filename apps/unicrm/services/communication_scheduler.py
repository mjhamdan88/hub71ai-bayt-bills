from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta, datetime
from typing import Iterable, Tuple
import random

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from jinja2 import TemplateError

from unicrm.models import Communication, CommunicationMessage, Contact, UnsubscribeAll
from unicrm.services.contact_interaction_cache import compute_history_for_contact
from unicrm.services.audience import audience_queryset
from unicrm.services.template_renderer import (
    render_template_for_contact,
    get_jinja_environment,
    unprotect_tinymce_markup,
)


@dataclass
class CommunicationPreparationResult:
    communication: Communication
    created: int
    updated: int
    skipped: int
    errors: list[str]


@dataclass
class DeliveryPreparationOutcome:
    delivery: CommunicationMessage
    created: bool
    updated: bool
    skipped: bool
    errors: list[str]


_GP_SAFE_STATUSES = {'valid', 'accept_all', 'risky'}


def _gp_validation_recent_and_safe(contact: Contact) -> bool:
    """
    Return True when the contact has a recent, positive GetProspect validation.
    """
    status = (contact.gp_email_status or '').strip().lower()
    if not status or status not in _GP_SAFE_STATUSES:
        return False
    return _gp_validation_recent(contact)


def _gp_validation_recent(contact: Contact) -> bool:
    """
    Return True when GetProspect validation exists and is within freshness window.
    """
    status = (contact.gp_email_status or '').strip().lower()
    max_age_days = 90
    try:
        max_age_days = int(getattr(settings, 'UNICRM_GP_VALIDATION_MAX_AGE_DAYS', 90))
    except (TypeError, ValueError):
        max_age_days = 90
    max_age_days = max(1, max_age_days)

    checked_at = contact.gp_email_checked_at or contact.gp_requested_at
    if not checked_at:
        return False
    return checked_at >= timezone.now() - timedelta(days=max_age_days)


def _render_subject(subject_template: str, context: dict) -> Tuple[str, list[str]]:
    """
    Render the subject template with the provided context.
    """
    if not subject_template:
        return '', []
    template_string = unprotect_tinymce_markup(subject_template)
    env = get_jinja_environment()
    errors: list[str] = []
    try:
        template = env.from_string(template_string)
        subject = template.render(context)
    except TemplateError as exc:
        subject = subject_template
        errors.append(str(exc))
    return subject.strip(), errors


def _eligible_contacts(communication: Communication) -> Iterable[Contact]:
    """
    Returns contacts matching mailing list/segment; filtering for email happens downstream.
    """
    qs = audience_queryset(communication.segment, communication.mailing_list, communication=communication)
    return qs.exclude(email_bounced=True).distinct()


def _burst_limit() -> int:
    try:
        value = int(getattr(settings, 'UNICRM_DELIVERY_BURST_LIMIT', 4))
    except (TypeError, ValueError):
        return 4
    return max(0, value)


def _drip_window() -> tuple[int, int]:
    try:
        min_minutes = int(getattr(settings, 'UNICRM_DELIVERY_DRIP_MIN_MINUTES', 1))
    except (TypeError, ValueError):
        min_minutes = 1
    try:
        max_minutes = int(getattr(settings, 'UNICRM_DELIVERY_DRIP_MAX_MINUTES', 2))
    except (TypeError, ValueError):
        max_minutes = 2
    min_minutes = max(1, min_minutes)
    max_minutes = max(min_minutes, max_minutes)
    return min_minutes, max_minutes


def _estimate_contact_count(contacts_source) -> int | None:
    """
    Best-effort helper to count contacts without forcing evaluation.
    """
    count_method = getattr(contacts_source, 'count', None)
    if callable(count_method):
        try:
            return int(count_method())
        except Exception:
            return None
    if hasattr(contacts_source, '__len__'):
        try:
            return len(contacts_source)
        except TypeError:
            return None
    return None


def _append_error(metadata: dict, message: str) -> None:
    errors = metadata.setdefault('errors', [])
    if message not in errors:
        errors.append(message)

UNSUBSCRIBED_STATUSES = {'unsubscribed'}


def _parse_iso(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        value = datetime.fromisoformat(dt_str)
        if timezone.is_naive(value):
            return timezone.make_aware(value)
        return value
    except Exception:
        return None


def _guard_contact_for_delivery(contact: Contact, communication: Communication | None = None) -> tuple[bool, str]:
    """
    Returns (should_skip, reason) based on unsubscribe-all or recent engagement rules.
    """
    if communication and getattr(communication, 'skip_antispam_guards', False):
        return False, ''

    if UnsubscribeAll.objects.filter(contact=contact).exists():
        return True, 'Contact unsubscribed from all communications.'

    history = contact.communication_history or []
    if not history:
        history = compute_history_for_contact(contact)

    cooldown_hours = getattr(settings, 'UNICRM_CONTACT_COOLDOWN_HOURS', 24)
    try:
        cooldown_hours = int(cooldown_hours)
    except (TypeError, ValueError):
        cooldown_hours = 24

    unengaged_limit = getattr(settings, 'UNICRM_CONTACT_UNENGAGED_LIMIT', 3)
    try:
        unengaged_limit = int(unengaged_limit)
    except (TypeError, ValueError):
        unengaged_limit = 3

    outbound_entries = [h for h in history if (h.get('direction') or '').lower() == 'outbound']

    def _is_real_send(entry: dict) -> bool:
        status = (entry.get('status') or '').lower()
        if status in {'scheduled', 'pending'}:
            return False
        # Require a message id to avoid counting unsent/scheduled records
        if not entry.get('message_id'):
            return False
        return True

    sent_entries = [h for h in outbound_entries if _is_real_send(h)]

    last_sent = None
    for entry in sent_entries:
        ts = _parse_iso(entry.get('sent_at') or entry.get('created_at'))
        if ts:
            last_sent = ts
            break

    if last_sent:
        delta = timezone.now() - last_sent
        if delta.total_seconds() < cooldown_hours * 3600:
            return True, f'Contacted recently ({delta}).'

    def _is_engaged(entry: dict) -> bool:
        return bool(entry.get('opened_at') or entry.get('clicked_at') or entry.get('replied_at') or entry.get('has_received_reply'))

    last_three = sent_entries[:unengaged_limit]
    if len(last_three) == unengaged_limit:
        if all((e.get('status') or '').lower() == 'sent' for e in last_three) and not any(_is_engaged(e) for e in last_three):
            return True, f'Unengaged after {len(last_three)} attempts.'

    return False, ''


def _persist_delivery(delivery: CommunicationMessage, update_fields: Iterable[str] | None = None) -> None:
    """
    Save helper that handles newly created and existing deliveries consistently.
    """
    if delivery.pk is None:
        delivery.save()
        return

    if not update_fields:
        delivery.save()
        return

    fields = list(dict.fromkeys(list(update_fields) + ['updated_at']))
    delivery.save(update_fields=fields)


def _prepare_delivery_for_contact(
    communication: Communication,
    contact: Contact,
    *,
    send_at,
    existing: CommunicationMessage | None = None,
    allow_resend_sent: bool = False,
) -> DeliveryPreparationOutcome:
    """
    Creates or refreshes a CommunicationMessage for the given contact.
    """
    if not communication.channel:
        raise ValueError("Communication must define a channel before preparing deliveries.")

    subject_template = communication.subject_template or f"Communication {communication.pk}"
    errors: list[str] = []

    with transaction.atomic():
        if existing is not None:
            delivery = (
                CommunicationMessage.objects
                .select_for_update(skip_locked=True)
                .select_related('contact')
                .get(pk=existing.pk)
            )
            created_delivery = False
        else:
            try:
                delivery = (
                    CommunicationMessage.objects
                    .select_for_update(skip_locked=True)
                    .select_related('contact')
                    .get(communication=communication, contact=contact)
                )
                created_delivery = False
            except CommunicationMessage.DoesNotExist:
                delivery = CommunicationMessage(
                    communication=communication,
                    contact=contact,
                    metadata={},
                )
                created_delivery = True

        metadata = delivery.metadata or {}
        current_status = (delivery.status or str(metadata.get('status') or '')).lower()

        if current_status == 'sent' and not allow_resend_sent:
            return DeliveryPreparationOutcome(delivery, False, False, True, errors)
        if current_status in {'failed', 'bounced', 'skipped'}:
            return DeliveryPreparationOutcome(delivery, False, False, True, errors)

        if not contact.email:
            _append_error(metadata, 'No email address on contact.')
            metadata['status'] = 'skipped'
            delivery.metadata = metadata
            delivery.status = 'skipped'
            delivery.scheduled_at = send_at
            _persist_delivery(delivery, ['metadata', 'status', 'scheduled_at'])
            return DeliveryPreparationOutcome(delivery, created_delivery, False, True, errors)

        if getattr(contact, 'email_bounced', False):
            _append_error(metadata, 'Previous delivery bounced; contact suppressed.')
            metadata['status'] = 'bounced'
            delivery.metadata = metadata
            delivery.status = 'bounced'
            delivery.scheduled_at = send_at
            _persist_delivery(delivery, ['metadata', 'status', 'scheduled_at'])
            return DeliveryPreparationOutcome(delivery, created_delivery, False, True, errors)

        gp_status_value = (getattr(contact, 'gp_email_status', '') or '').strip().lower()
        if gp_status_value and _gp_validation_recent(contact):
            metadata['gp_validation_status'] = gp_status_value
            if gp_status_value in _GP_SAFE_STATUSES:
                metadata['skip_reacher'] = True
            else:
                reason = f"GetProspect validation blocked send (status={gp_status_value})."
                _append_error(metadata, reason)
                errors.append(reason)
                metadata['status'] = 'bounced'
                delivery.metadata = metadata
                delivery.status = 'bounced'
                delivery.scheduled_at = send_at
                _persist_delivery(delivery, ['metadata', 'status', 'scheduled_at'])
                return DeliveryPreparationOutcome(delivery, created_delivery, False, True, errors)

        should_skip, reason = _guard_contact_for_delivery(contact, communication=communication)
        if should_skip:
            _append_error(metadata, reason)
            metadata['status'] = 'failed'
            delivery.metadata = metadata
            delivery.status = 'failed'
            delivery.scheduled_at = send_at
            _persist_delivery(delivery, ['metadata', 'status', 'scheduled_at'])
            errors.append(reason)
            return DeliveryPreparationOutcome(delivery, created_delivery, False, True, errors)

        render_result = render_template_for_contact(
            communication.get_renderable_content(),
            contact=contact,
            communication=communication,
        )

        subject, subject_errors = _render_subject(subject_template, render_result.context)
        errors.extend(subject_errors)
        for err in render_result.errors:
            _append_error(metadata, err)
        errors.extend(render_result.errors)

        payload = {
            'to': [contact.email],
            'subject': subject or subject_template or f"Communication {communication.pk}",
            'html': render_result.html,
        }
        if metadata.get('skip_reacher'):
            payload['skip_reacher'] = True

        metadata['status'] = 'scheduled'
        metadata['send_at'] = send_at.isoformat()
        metadata['payload'] = payload
        metadata['variables'] = json.loads(json.dumps(render_result.variables, cls=DjangoJSONEncoder))
        metadata['context'] = json.loads(json.dumps(render_result.context, cls=DjangoJSONEncoder))

        delivery.metadata = metadata
        delivery.status = 'scheduled'
        delivery.scheduled_at = send_at
        _persist_delivery(delivery, ['metadata', 'status', 'scheduled_at'])

        return DeliveryPreparationOutcome(
            delivery=delivery,
            created=created_delivery,
            updated=not created_delivery,
            skipped=False,
            errors=errors,
        )


def ensure_delivery_for_contact(
    communication: Communication,
    contact: Contact,
    *,
    send_at=None,
) -> DeliveryPreparationOutcome:
    """
    Public helper to guarantee a single contact has an up-to-date delivery payload.
    """
    actual_send_at = send_at or communication.scheduled_for or timezone.now()
    outcome = _prepare_delivery_for_contact(
        communication,
        contact,
        send_at=actual_send_at,
    )
    if communication.scheduled_for is None:
        communication.scheduled_for = actual_send_at
        communication.save(update_fields=['scheduled_for', 'updated_at'])
    communication.refresh_status_summary()
    return outcome


def refresh_delivery_for_sending(
    delivery: CommunicationMessage,
    *,
    send_at=None,
) -> DeliveryPreparationOutcome:
    """
    Refresh an existing delivery before attempting to send it.
    """
    communication = delivery.communication
    target_send_at = (
        send_at
        or delivery.scheduled_at
        or communication.scheduled_for
        or timezone.now()
    )
    return _prepare_delivery_for_contact(
        communication,
        delivery.contact,
        send_at=target_send_at,
        existing=delivery,
    )


def prepare_deliveries_for_communication(communication: Communication) -> CommunicationPreparationResult:
    """
    Prepares per-contact payloads for the provided communication.
    """
    if not communication.channel:
        raise ValueError("Communication must define a channel before preparing deliveries.")

    contacts_source = _eligible_contacts(communication)
    total_contacts = _estimate_contact_count(contacts_source)
    contacts = (
        contacts_source.iterator()
        if hasattr(contacts_source, 'iterator')
        else contacts_source
    )
    send_at = communication.scheduled_for or timezone.now()
    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []
    burst_limit = _burst_limit()
    min_gap, max_gap = _drip_window()
    should_throttle = bool(burst_limit and total_contacts and total_contacts > burst_limit)
    cumulative_delay = timedelta(0)
    rng = random.Random(communication.pk or int(send_at.timestamp())) if should_throttle else None

    for index, contact in enumerate(contacts):
        contact_send_at = send_at
        if should_throttle:
            if index < burst_limit:
                contact_send_at = send_at
            else:
                if rng is None:
                    rng = random.Random(communication.pk or int(send_at.timestamp()))
                cumulative_delay += timedelta(minutes=rng.randint(min_gap, max_gap))
                contact_send_at = send_at + cumulative_delay

        outcome = _prepare_delivery_for_contact(
            communication,
            contact,
            send_at=contact_send_at,
        )
        if outcome.created:
            created += 1
        elif outcome.updated and not outcome.skipped:
            updated += 1
        if outcome.skipped:
            skipped += 1
        errors.extend(outcome.errors)

    updates: list[str] = []
    if communication.scheduled_for != send_at:
        communication.scheduled_for = send_at
        updates.append('scheduled_for')
    if communication.auto_enroll_new_contacts:
        communication.evergreen_refreshed_at = timezone.now()
        updates.append('evergreen_refreshed_at')
    if updates:
        communication.save(update_fields=updates + ['updated_at'])
    communication.refresh_status_summary()

    return CommunicationPreparationResult(
        communication=communication,
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
    )
