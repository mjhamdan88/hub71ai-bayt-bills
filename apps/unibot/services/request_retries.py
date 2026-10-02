"""Conservative automatic retry policy for transient Unicom request failures."""

from __future__ import annotations

import random
from datetime import timedelta

import httpx
import openai
from django.conf import settings
from django.utils import timezone


DEFAULT_RETRY_DELAYS_SECONDS = (3, 12, 45)
TRANSIENT_MESSAGE_MARKERS = (
    "servers are currently overloaded",
    "server is currently overloaded",
    "temporarily unavailable",
    "try again later",
)


def _exception_chain(exc):
    seen = set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def classify_retryable_failure(exc) -> str:
    """Return a narrow transient failure class, or an empty string."""
    for current in _exception_chain(exc):
        if isinstance(current, openai.RateLimitError):
            return "rate_limit"
        if isinstance(current, openai.APITimeoutError):
            return "provider_timeout"
        if isinstance(current, openai.APIConnectionError):
            return "provider_connection"
        if isinstance(current, openai.InternalServerError):
            return "provider_server"
        if isinstance(current, openai.APIStatusError):
            status_code = int(getattr(current, "status_code", 0) or 0)
            if status_code in {408, 409, 429} or status_code >= 500:
                return "provider_status"
            return ""
        if isinstance(current, httpx.TimeoutException):
            return "transport_timeout"
        if isinstance(current, httpx.TransportError):
            return "transport_error"
        if isinstance(current, openai.APIError):
            message = str(current).lower()
            if any(marker in message for marker in TRANSIENT_MESSAGE_MARKERS):
                return "provider_overload"
    return ""


def classify_terminal_failure(exc) -> str:
    """Separate failures needing user action from other permanent failures."""
    message = str(exc).lower()
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        message = f"{message} {body}".lower()
    if any(marker in message for marker in (
        "ai_setup_required", "no ai balance", "no credits remaining",
        "insufficient_quota", "billing",
    )):
        return "user_action"
    return "permanent"


def retry_delays_seconds() -> tuple[float, ...]:
    configured = getattr(settings, "UNICOM_REQUEST_RETRY_DELAYS_SECONDS", DEFAULT_RETRY_DELAYS_SECONDS)
    delays = tuple(max(0.0, float(value)) for value in configured)
    max_retries = max(0, int(getattr(settings, "UNICOM_REQUEST_MAX_RETRIES", len(delays))))
    return delays[:max_retries]


def schedule_retry(request, exc, *, now=None, jitter=None) -> bool:
    """Populate retry state after one failed attempt; caller persists it."""
    now = now or timezone.now()
    kind = classify_retryable_failure(exc)
    request.failure_kind = kind or classify_terminal_failure(exc)
    request.next_retry_at = None
    request.retry_exhausted_at = None
    if not kind:
        return False

    delays = retry_delays_seconds()
    if request.retry_count >= len(delays):
        request.retry_exhausted_at = now
        return False

    jitter_factor = jitter if jitter is not None else random.uniform(0.8, 1.2)
    request.next_retry_at = now + timedelta(seconds=delays[request.retry_count] * jitter_factor)
    return True

