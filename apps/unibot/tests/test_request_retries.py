from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import openai
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from unibot.management.commands.run_worker import claim_due_retry
from unibot.services.request_retries import (
    classify_retryable_failure,
    schedule_retry,
)


class RequestRetryPolicyTests(SimpleTestCase):
    def test_transport_protocol_failure_is_retryable(self):
        error = httpx.RemoteProtocolError("incomplete chunked read")
        self.assertEqual(classify_retryable_failure(error), "transport_error")

    def test_provider_overload_is_retryable(self):
        error = openai.APIError(
            "Our servers are currently overloaded. Please try again later.",
            httpx.Request("POST", "https://provider.invalid/v1/responses"),
            body=None,
        )
        self.assertEqual(classify_retryable_failure(error), "provider_overload")

    def test_provider_bad_request_is_not_retryable(self):
        response = httpx.Response(
            400,
            request=httpx.Request("POST", "https://provider.invalid/v1/responses"),
        )
        error = openai.BadRequestError("invalid schema", response=response, body=None)
        self.assertEqual(classify_retryable_failure(error), "")

    def test_permanent_failure_is_not_scheduled(self):
        request = SimpleNamespace(
            retry_count=0, failure_kind="", next_retry_at=None,
            retry_exhausted_at=None,
        )
        self.assertFalse(schedule_retry(request, ValueError("invalid schema")))
        self.assertEqual(request.failure_kind, "permanent")
        self.assertIsNone(request.next_retry_at)

    def test_funding_failure_requires_user_action(self):
        request = SimpleNamespace(
            retry_count=0, failure_kind="", next_retry_at=None,
            retry_exhausted_at=None,
        )
        self.assertFalse(schedule_retry(request, ValueError("No AI balance is available")))
        self.assertEqual(request.failure_kind, "user_action")

    @override_settings(
        UNICOM_REQUEST_MAX_RETRIES=3,
        UNICOM_REQUEST_RETRY_DELAYS_SECONDS=(3, 12, 45),
    )
    def test_backoff_is_bounded_and_stops_after_three_retries(self):
        now = timezone.now()
        request = SimpleNamespace(
            retry_count=0, failure_kind="", next_retry_at=None,
            retry_exhausted_at=None,
        )
        error = httpx.ReadTimeout("temporary timeout")
        for retry_count, delay in enumerate((3, 12, 45)):
            request.retry_count = retry_count
            self.assertTrue(schedule_retry(request, error, now=now, jitter=1.0))
            self.assertEqual(request.next_retry_at, now + timedelta(seconds=delay))
            self.assertIsNone(request.retry_exhausted_at)

        request.retry_count = 3
        self.assertFalse(schedule_retry(request, error, now=now, jitter=1.0))
        self.assertIsNone(request.next_retry_at)
        self.assertEqual(request.retry_exhausted_at, now)

    def test_claim_updates_retry_state_once(self):
        now = timezone.now()
        request = SimpleNamespace(
            status="FAILED", retry_count=1,
            last_retried_at=None, next_retry_at=now - timedelta(seconds=1),
            save=Mock(),
        )
        self.assertTrue(claim_due_retry(request, now=now))
        self.assertEqual(request.status, "QUEUED")
        self.assertEqual(request.retry_count, 2)
        self.assertEqual(request.last_retried_at, now)
        self.assertIsNone(request.next_retry_at)
        self.assertFalse(claim_due_retry(request, now=now))
        request.save.assert_called_once()
