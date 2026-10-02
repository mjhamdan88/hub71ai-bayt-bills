import logging
from django.conf import settings
from unicom.models import Channel

logger = logging.getLogger(__name__)


def get_system_email_channel() -> Channel:
    """
    Return the Channel used for system-generated emails (signup, resets, transfers).
    Respects SYSTEM_EMAIL_CHANNEL_ID when set, otherwise falls back to the earliest
    active Email channel.
    """
    desired_id = getattr(settings, 'SYSTEM_EMAIL_CHANNEL_ID', None)
    qs = Channel.objects.filter(platform='Email', active=True).order_by('id')

    if desired_id:
        channel = qs.filter(id=desired_id).first()
        if channel:
            return channel
        logger.warning(
            "SYSTEM_EMAIL_CHANNEL_ID=%s not found among active email channels; falling back to first available channel.",
            desired_id,
        )

    channel = qs.first()
    if not channel:
        raise Channel.DoesNotExist("No active Email channels are available for system email delivery.")
    return channel
