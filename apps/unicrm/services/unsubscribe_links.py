from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.core import signing

from unicom.services.get_public_origin import get_public_origin
from unicrm.models import Communication, Contact, MailingList

UNSUBSCRIBE_SALT = 'unicrm.unsubscribe'


def _pick_mailing_list(contact: Contact, mailing_list: MailingList | None = None, communication: Communication | None = None) -> MailingList | None:
    if mailing_list:
        return mailing_list
    if communication and getattr(communication, 'mailing_list_id', None):
        return communication.mailing_list
    subscription = (
        contact.subscriptions
        .select_related('mailing_list')
        .filter(mailing_list__isnull=False)
        .order_by('-subscribed_at')
        .first()
    )
    return subscription.mailing_list if subscription else None


def build_unsubscribe_token(
    contact: Contact,
    *,
    mailing_list: MailingList | None = None,
    communication: Communication | None = None,
) -> str:
    payload = {
        'contact_id': contact.pk,
        'mailing_list_id': None,
        'mailing_list_slug': None,
        'communication_id': communication.pk if communication else None,
    }
    ml = _pick_mailing_list(contact, mailing_list, communication)
    if ml:
        payload['mailing_list_id'] = ml.pk
        payload['mailing_list_slug'] = ml.slug
    return signing.dumps(payload, salt=UNSUBSCRIBE_SALT)


def build_unsubscribe_link(
    contact: Contact,
    *,
    mailing_list: MailingList | None = None,
    communication: Communication | None = None,
    base_path: str | None = None,
) -> str:
    """
    Returns an absolute unsubscribe URL for the given contact (and optional mailing list/communication).
    """
    token = build_unsubscribe_token(contact, mailing_list=mailing_list, communication=communication)
    origin = get_public_origin()
    path = base_path or getattr(settings, 'UNICRM_UNSUBSCRIBE_PATH', '/unicrm/unsubscribe/')
    if not path.startswith('/'):
        path = '/' + path
    if not path.endswith('/'):
        path += '/'
    return f"{origin}{path}?token={token}"
