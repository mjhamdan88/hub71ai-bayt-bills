# Example segment filter snippet.
# Define a function named `apply(qs)` where `qs` is a QuerySet of `unicrm.Contact`.
# You must return a modified QuerySet (do not evaluate it too early).

from django.db.models import Q


def apply(qs):
    """
    Sample filter: contacts subscribed to the newsletter mailing list.
    """
    return qs.filter(
        subscriptions__mailing_list__slug='newsletter',
        subscriptions__unsubscribed_at__isnull=True,
    ).distinct()

