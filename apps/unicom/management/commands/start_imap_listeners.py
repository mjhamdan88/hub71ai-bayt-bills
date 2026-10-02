from django.core.management.base import BaseCommand
from unicom.services.email.IMAP_thread_manager import imap_manager
from unicom.services.email.backfill import process_next_backfill_job
from unicom.models import EmailBackfillJob
import time
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Start IMAP listeners for all active email channels and keep them running"

    def handle(self, *args, **options):
        # A worker may have exited mid-import. Jobs are UID-deduplicated, so
        # safely resume them from the queue on startup.
        EmailBackfillJob.objects.filter(status=EmailBackfillJob.Status.RUNNING).update(
            status=EmailBackfillJob.Status.PENDING
        )
        self.stdout.write("Starting IMAP listeners for all active email channels...")
        imap_manager.start_all()
        self.stdout.write(self.style.SUCCESS("IMAP listeners started successfully"))
        
        try:
            self.stdout.write("Press Ctrl+C to stop...")
            while True:
                if not process_next_backfill_job():
                    time.sleep(2)
        except KeyboardInterrupt:
            self.stdout.write("\nShutting down IMAP listeners...")
            self.stdout.write(self.style.SUCCESS("IMAP listeners stopped"))
