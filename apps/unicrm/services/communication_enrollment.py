from __future__ import annotations

import logging

from django.db import transaction

from unicrm.models import Communication, Contact
from unicrm.services.communication_scheduler import ensure_delivery_for_contact
from unicrm.services.audience import audience_queryset

logger = logging.getLogger(__name__)


def enroll_contact_in_evergreen_communications(contact: Contact) -> None:
    """
    Ensures evergreen communications prepare delivery payloads for the provided contact.
    """
    communications = (
        Communication.objects
        .filter(auto_enroll_new_contacts=True)
        .exclude(status='cancelled')
        .select_related('segment', 'channel')
    )

    for communication in communications:
        segment = communication.segment
        channel = communication.channel
        if not segment or not channel:
            continue

        try:
            matches = audience_queryset(segment, communication.mailing_list, communication=communication).filter(pk=contact.pk)
            if not matches.exists():
                continue
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(
                "Failed evaluating segment %s for contact %s during evergreen enrolment: %s",
                getattr(segment, 'pk', None),
                contact.pk,
                exc,
            )
            continue

        try:
            with transaction.atomic():
                ensure_delivery_for_contact(communication, contact)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(
                "Failed to prepare evergreen delivery for communication %s contact %s: %s",
                communication.pk,
                contact.pk,
                exc,
            )
