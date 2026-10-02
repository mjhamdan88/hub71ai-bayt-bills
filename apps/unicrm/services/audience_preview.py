from __future__ import annotations

from typing import Iterable, Tuple
from types import SimpleNamespace

from unicrm.models import Contact, MailingList, Segment, Subscription, Communication
from unicrm.services.audience import audience_size_and_sample


def _base_contacts(mailing_list: MailingList | None) -> Iterable[Contact]:
    qs = Contact.objects.all()
    if mailing_list:
        qs = qs.filter(
            subscriptions__mailing_list=mailing_list,
            subscriptions__unsubscribed_at__isnull=True,
        )
    qs = qs.exclude(email_bounced=True).exclude(unsubscribe_all_entries__isnull=False)
    return qs


def preview_audience(
    mailing_list_id: int | None,
    segment_id: int | None,
    follow_up_for_id: int | None = None,
    *,
    exclude_follow_up_siblings: bool | None = None,
    limit: int = 10,
) -> Tuple[int, list[dict]]:
    if mailing_list_id is None and segment_id is None:
        return 0, []
    mailing_list = MailingList.objects.filter(pk=mailing_list_id).first() if mailing_list_id else None
    segment = Segment.objects.filter(pk=segment_id).first() if segment_id else None
    follow_up_for = Communication.objects.filter(pk=follow_up_for_id).first() if follow_up_for_id else None
    if follow_up_for:
        if exclude_follow_up_siblings is None:
            exclude_follow_up_siblings = True
        communication_stub = SimpleNamespace(
            follow_up_for=follow_up_for,
            exclude_follow_up_siblings=bool(exclude_follow_up_siblings),
        )
    else:
        communication_stub = None

    return audience_size_and_sample(
        segment,
        mailing_list,
        communication=communication_stub,
        limit=limit,
        apply_guards=False,
    )
