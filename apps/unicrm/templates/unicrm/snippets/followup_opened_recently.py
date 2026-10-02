# Follow-up example: contacts who opened the previous communication within the last 24 hours.
# `previous_comm` is injected automatically when this segment is used for a follow-up communication.
from django.utils import timezone
from datetime import timedelta


def apply(qs, previous_comm=None):
    if previous_comm is None:
        # No parent selected; return empty set to avoid accidental sends.
        return qs.none()

    window_start = timezone.now() - timedelta(hours=24)
    return qs.filter(
        communications__communication=previous_comm,
        communications__message__opened=True,
        communications__message__time_opened__gte=window_start,
    ).distinct()
