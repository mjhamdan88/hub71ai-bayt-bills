from __future__ import annotations

import logging
import time

from django.core.management.base import BaseCommand

from unicrm.services.communication_dispatcher import process_scheduled_communications

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Continuously process scheduled unicrm Communications and dispatch their deliveries.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=10,
            help='Interval in seconds between scheduler cycles (default: 10).'
        )
        parser.add_argument(
            '--run-once',
            action='store_true',
            help='Process a single cycle and exit.'
        )

    def handle(self, *args, **options):
        interval = max(options['interval'], 1)
        run_once = options['run_once']
        verbosity = int(options.get('verbosity', 1))

        if run_once:
            summary = process_scheduled_communications(verbosity=verbosity)
            self._log_summary(summary, verbosity)
            return

        self.stdout.write(self.style.SUCCESS(
            f'Starting unicrm communication scheduler with a {interval}-second interval...'
        ))

        try:
            while True:
                summary = process_scheduled_communications(verbosity=verbosity)
                self._log_summary(summary, verbosity)
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Scheduler interrupted; shutting down.'))
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception('Unicrm scheduler encountered a fatal error: %s', exc)
            raise

    def _log_summary(self, summary, verbosity):
        processed = summary.get('communications_processed', 0)
        sent = summary.get('messages_sent', 0)
        failed = summary.get('messages_failed', 0)
        if verbosity >= 1 or processed or sent or failed:
            self.stdout.write(
                f'Processed {processed} communications (sent={sent}, failed={failed}).'
            )
        if verbosity >= 2:
            for detail in summary.get('details', []):
                email = detail.get('contact_email') or detail.get('contact_id')
                status = detail.get('status')
                subject = detail.get('subject') or ''
                body = detail.get('html') or ''
                note = detail.get('note')
                line = f" - Communication {detail.get('communication_id')} -> {email}: status={status}"
                if note:
                    line += f" ({note})"
                self.stdout.write(line)
                self.stdout.write(f"   Subject: {subject}")
                self.stdout.write(f"   Body: {body}")
                for err in detail.get('errors', []) or []:
                    self.stdout.write(f"   Error: {err}")
