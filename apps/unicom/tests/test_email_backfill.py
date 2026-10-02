from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from unicom.models import Channel, EmailBackfillJob, Request
from unicom.services.email.backfill import create_backfill_job, run_backfill_job
from unicom.services.email.save_email_message import save_email_message


def email_channel(**config):
    base = {
        "EMAIL_ADDRESS": "privacy@portacode.com",
        "EMAIL_PASSWORD": "secret",
        "IMAP": {"host": "imap.example.com", "port": 993, "use_ssl": True},
        "SMTP": {"host": "smtp.example.com", "port": 465, "use_ssl": True},
    }
    base.update(config)
    return Channel.objects.create(name="Privacy", platform="Email", config=base, active=True)


class EmailBackfillTests(TestCase):
    def test_create_backfill_job_reuses_active_job(self):
        channel = email_channel()
        first = create_backfill_job(channel)
        self.assertEqual(create_backfill_job(channel).pk, first.pk)

    def test_backfill_updates_durable_progress_without_marking_mail_seen(self):
        channel = email_channel()
        job = create_backfill_job(channel)

        class FakeIMAP:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def login(self, *args): pass
            def select_folder(self, folder, readonly=False):
                assert folder == "INBOX"
                assert readonly is True
            def search(self, criteria):
                assert criteria == ["ALL"]
                return [10, 11]
            def fetch(self, uid, fields):
                assert fields == ["BODY.PEEK[]"]
                return {uid: {b"BODY[]": b"mail"}}

        def fake_save(channel, raw, uid=None, historical=False):
            self.assertTrue(historical)
            return SimpleNamespace(channel_id=channel.id, imap_uid=uid)

        with patch("unicom.services.email.backfill.IMAPClient", FakeIMAP), patch(
            "unicom.services.email.backfill.save_email_message", side_effect=fake_save
        ):
            run_backfill_job(job)

        job.refresh_from_db()
        self.assertEqual(job.status, EmailBackfillJob.Status.COMPLETED)
        self.assertEqual((job.total_messages, job.processed_messages, job.imported_messages), (2, 2, 2))
        self.assertEqual(job.progress_percent, 100)

    def test_historical_message_does_not_create_request(self):
        channel = email_channel()
        raw = b"\r\n".join([
            b"From: Person <person@example.com>", b"To: privacy@portacode.com",
            b"Subject: Old privacy request", b"Message-ID: <old-privacy@example.com>",
            b"Date: Tue, 01 Jul 2025 12:00:00 +0000",
            b"Authentication-Results: mx.portacode.com; dmarc=pass header.from=example.com",
            b"Content-Type: text/plain; charset=utf-8", b"", b"Please help with an old request.",
        ])
        message = save_email_message(channel, raw, uid=7, historical=True)
        self.assertTrue(message.raw["historical_import"])
        self.assertTrue(message.raw["skip_request_creation"])
        self.assertFalse(Request.objects.filter(message=message).exists())

    def test_admin_can_start_and_poll_backfill(self):
        admin_user = User.objects.create_superuser("admin", "admin@example.com", "password")
        self.client.force_login(admin_user)
        channel = email_channel()
        change = reverse("admin:unicom_channel_change", args=[channel.pk])
        start = reverse("admin:unicom_channel_backfill_start", args=[channel.pk])
        status = reverse("admin:unicom_channel_backfill_status", args=[channel.pk])
        page = self.client.get(change)
        self.assertContains(page, "Import inbox history")
        self.assertContains(page, "email-backfill-bar")
        self.assertEqual(self.client.post(start).status_code, 202)
        payload = self.client.get(status).json()
        self.assertEqual(payload["status"], EmailBackfillJob.Status.PENDING)
        self.assertEqual(payload["progress"], 0)
