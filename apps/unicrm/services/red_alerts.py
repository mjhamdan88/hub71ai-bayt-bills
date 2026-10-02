from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set, TYPE_CHECKING

from django.db.models import Prefetch, QuerySet

from unicom.models import Account, AccountChat, Chat
from unicom.services.crossplatform.send_message import send_message as unicom_send_message

if TYPE_CHECKING:  # pragma: no cover - typing only
    from django.contrib.auth.models import AbstractBaseUser

logger = logging.getLogger(__name__)

SUPPORTED_ALERT_PLATFORMS: Set[str] = {"Email", "Telegram"}

ACCOUNT_CHAT_PREFETCH = Prefetch(
    "accountchat_set",
    queryset=AccountChat.objects.select_related("chat", "chat__channel"),
)


@dataclass
class RedAlertDelivery:
    account_id: str
    channel_id: int
    platform: str
    status: str
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    error: Optional[str] = None


def send_red_alert(
    *,
    subject: str,
    body: str,
    html: Optional[str] = None,
    initiated_by: Optional["AbstractBaseUser"] = None,
    platforms: Optional[Iterable[str]] = None,
) -> List[RedAlertDelivery]:
    """
    Broadcast an urgent alert message to every active Django staff user.

    Args:
        subject: Short subject/summary for the alert (required for email threads).
        body: Plain-text body of the alert.
        html: Optional HTML body (used for email only).
        initiated_by: Django user responsible for the send (recorded on Message).
        platforms: Optional iterable to limit platforms (defaults to Email + Telegram).
    """
    if not subject:
        raise ValueError("subject is required for red alerts")
    if not body:
        raise ValueError("body is required for red alerts")

    requested_platforms = {p for p in (platforms or SUPPORTED_ALERT_PLATFORMS) if p}
    allowed_platforms = requested_platforms & SUPPORTED_ALERT_PLATFORMS
    if not allowed_platforms:
        raise ValueError(
            f"No supported platforms selected (requested={requested_platforms})."
        )

    staff_accounts = list(_staff_alert_accounts(allowed_platforms))
    if not staff_accounts:
        logger.warning(
            "send_red_alert: No staff accounts found for platforms: %s",
            ", ".join(sorted(allowed_platforms)),
        )
        return []

    deliveries: List[RedAlertDelivery] = []
    for account in staff_accounts:
        if account.platform == "Email":
            deliveries.append(
                _send_email_alert(account, subject, body, html, initiated_by)
            )
        elif account.platform == "Telegram":
            deliveries.append(
                _send_telegram_alert(account, subject, body, initiated_by)
            )
        else:
            reason = f"Unsupported platform {account.platform}"
            logger.info(
                "send_red_alert: Skipping account %s (%s) - %s",
                account.id,
                account.platform,
                reason,
            )
            deliveries.append(
                RedAlertDelivery(
                    account_id=account.id,
                    channel_id=account.channel_id,
                    platform=account.platform,
                    status="skipped",
                    error=reason,
                )
            )

    return deliveries


def _staff_alert_accounts(allowed_platforms: Set[str]) -> QuerySet[Account]:
    return (
        Account.objects.select_related("channel", "member", "member__user")
        .prefetch_related(ACCOUNT_CHAT_PREFETCH)
        .filter(
            member__isnull=False,
            member__user__isnull=False,
            member__user__is_staff=True,
            member__user__is_active=True,
            blocked=False,
            is_bot=False,
            channel__active=True,
            platform__in=allowed_platforms,
            channel__platform__in=allowed_platforms,
        )
        .order_by("member__user__id", "platform", "id")
    )


def _send_email_alert(
    account: Account,
    subject: str,
    body: str,
    html: Optional[str],
    initiated_by: Optional["AbstractBaseUser"],
) -> RedAlertDelivery:
    payload = {"to": [account.id], "subject": subject, "text": body}
    if html:
        payload["html"] = html

    try:
        message = unicom_send_message(account.channel, payload, initiated_by)
        message_id = getattr(message, "id", None)
        logger.info(
            "send_red_alert: Sent email alert to %s via channel %s",
            account.id,
            account.channel_id,
        )
        return RedAlertDelivery(
            account_id=account.id,
            channel_id=account.channel_id,
            platform=account.platform,
            status="sent",
            message_id=message_id,
        )
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.exception(
            "send_red_alert: Email delivery failed for %s on channel %s: %s",
            account.id,
            account.channel_id,
            exc,
        )
        return RedAlertDelivery(
            account_id=account.id,
            channel_id=account.channel_id,
            platform=account.platform,
            status="failed",
            error=str(exc),
        )


def _send_telegram_alert(
    account: Account,
    subject: str,
    body: str,
    initiated_by: Optional["AbstractBaseUser"],
) -> RedAlertDelivery:
    chat = _select_chat_for_account(account)
    if not chat:
        reason = "No chat associated with Telegram account"
        logger.warning(
            "send_red_alert: %s (%s) skipped - %s",
            account.id,
            account.platform,
            reason,
        )
        return RedAlertDelivery(
            account_id=account.id,
            channel_id=account.channel_id,
            platform=account.platform,
            status="skipped",
            error=reason,
        )

    payload = {"chat_id": chat.id, "text": _format_instant_text(subject, body)}
    try:
        message = unicom_send_message(account.channel, payload, initiated_by)
        message_id = getattr(message, "id", None)
        logger.info(
            "send_red_alert: Sent Telegram alert to %s via chat %s",
            account.id,
            chat.id,
        )
        return RedAlertDelivery(
            account_id=account.id,
            channel_id=account.channel_id,
            platform=account.platform,
            chat_id=chat.id,
            status="sent",
            message_id=message_id,
        )
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.exception(
            "send_red_alert: Telegram delivery failed for %s/%s: %s",
            account.id,
            chat.id,
            exc,
        )
        return RedAlertDelivery(
            account_id=account.id,
            channel_id=account.channel_id,
            platform=account.platform,
            chat_id=chat.id,
            status="failed",
            error=str(exc),
        )


def _select_chat_for_account(account: Account) -> Optional[Chat]:
    chats = [
        link.chat
        for link in account.accountchat_set.all()
        if link.chat and link.chat.channel_id == account.channel_id
    ]
    if not chats:
        return None

    preferred = [
        chat for chat in chats if not chat.is_archived and chat.is_private
    ] or [chat for chat in chats if not chat.is_archived]

    return (preferred or chats)[0]


def _format_instant_text(subject: str, body: str) -> str:
    header = f"[RED ALERT] {subject}".strip()
    if body:
        return f"{header}\n\n{body}"
    return header
