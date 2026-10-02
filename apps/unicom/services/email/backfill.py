import logging

from django.db import transaction
from django.utils import timezone
from imapclient import IMAPClient

from unicom.models import EmailBackfillJob, Message
from .auth_helpers import get_email_service_credentials
from .save_email_message import save_email_message

logger = logging.getLogger(__name__)


def create_backfill_job(channel):
    if channel.platform != "Email" or not channel.active:
        raise ValueError("Only active email channels can be imported.")
    active = channel.email_backfill_jobs.filter(
        status__in=[EmailBackfillJob.Status.PENDING, EmailBackfillJob.Status.RUNNING]
    ).first()
    return active or EmailBackfillJob.objects.create(channel=channel)


def run_backfill_job(job):
    channel = job.channel
    config = channel.config or {}
    imap = config["IMAP"]
    username, password = get_email_service_credentials(config, "IMAP")
    EmailBackfillJob.objects.filter(pk=job.pk).update(
        status=EmailBackfillJob.Status.RUNNING,
        started_at=job.started_at or timezone.now(),
        error="",
        total_messages=0,
        processed_messages=0,
        imported_messages=0,
        skipped_messages=0,
        failed_messages=0,
    )
    try:
        with IMAPClient(imap["host"], port=imap["port"], ssl=imap["use_ssl"]) as server:
            server.login(username, password)
            server.select_folder("INBOX", readonly=True)
            uids = list(server.search(["ALL"]))
            EmailBackfillJob.objects.filter(pk=job.pk).update(total_messages=len(uids))
            known_uids = set(
                Message.objects.filter(channel=channel, imap_uid__in=uids).values_list("imap_uid", flat=True)
            )
            for uid in uids:
                imported = skipped = failed = 0
                if uid in known_uids:
                    skipped = 1
                else:
                    try:
                        response = server.fetch(uid, ["BODY.PEEK[]"])
                        raw = response[uid][b"BODY[]"]
                        before = Message.objects.filter(channel=channel, imap_uid=uid).exists()
                        message = save_email_message(channel, raw, uid=uid, historical=True)
                        if message is None or before:
                            skipped = 1
                        else:
                            # A globally deduplicated Message-ID may already exist.
                            if message.channel_id == channel.id and message.imap_uid == uid:
                                imported = 1
                            else:
                                skipped = 1
                    except Exception:
                        failed = 1
                        logger.exception("Channel %s backfill failed for UID %s", channel.pk, uid)
                with transaction.atomic():
                    current = EmailBackfillJob.objects.select_for_update().get(pk=job.pk)
                    current.processed_messages += 1
                    current.imported_messages += imported
                    current.skipped_messages += skipped
                    current.failed_messages += failed
                    current.save(update_fields=[
                        "processed_messages", "imported_messages", "skipped_messages", "failed_messages"
                    ])
        final = EmailBackfillJob.objects.get(pk=job.pk)
        final.status = EmailBackfillJob.Status.COMPLETED
        final.finished_at = timezone.now()
        final.save(update_fields=["status", "finished_at"])
    except Exception as exc:
        EmailBackfillJob.objects.filter(pk=job.pk).update(
            status=EmailBackfillJob.Status.FAILED,
            error=str(exc)[:2000],
            finished_at=timezone.now(),
        )
        logger.exception("Channel %s historical inbox import failed", channel.pk)


def process_next_backfill_job():
    with transaction.atomic():
        job = (
            EmailBackfillJob.objects.select_for_update(skip_locked=True)
            .filter(status=EmailBackfillJob.Status.PENDING)
            .order_by("created_at")
            .first()
        )
        if not job:
            return False
        job.status = EmailBackfillJob.Status.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])
    run_backfill_job(job)
    return True
