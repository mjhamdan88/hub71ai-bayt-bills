from django.core.management.base import BaseCommand
from django.utils import timezone
from unicom.services.crossplatform.scheduler import process_scheduled_messages
import time
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Continuously process and send scheduled messages at a defined interval.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=10,  # Default interval in seconds
            help='Interval in seconds between checking for scheduled messages.'
        )

    def handle(self, *args, **options):
        interval = options['interval']
        self.stdout.write(self.style.SUCCESS(f'Starting scheduled message processor with a {interval}-second interval...'))
        self.stdout.write(self.style.NOTICE('Press Ctrl+C to stop.'))

        try:
            while True:
                # self.stdout.write(self.style.HTTP_INFO(f'Checking for scheduled messages at {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}'))
                try:
                    result = process_scheduled_messages()
                    if result["total_due"] > 0:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Processed {result["total_due"]} due messages. Sent: {result["sent"]}. Failed: {result["failed"]}.'
                            )
                        )
                    elif result["sent"] == 0 and result["failed"] == 0: # No messages were due
                        pass # Don't log anything if no messages were due, to keep output clean
                        
                except Exception as e:
                    # This catches unexpected errors in process_scheduled_messages or the loop itself
                    logger.error(f'Critical error in scheduler loop: {str(e)}', exc_info=True)
                    self.stdout.write(self.style.ERROR(f'Scheduler loop error: {str(e)}. Check logs for details.'))
                
                # Wait for the defined interval before checking again
                time.sleep(interval)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Scheduled message processor stopped by user.'))
        except Exception as e:
            logger.critical(f'Scheduler process terminated due to an unhandled exception: {str(e)}', exc_info=True)
            self.stdout.write(self.style.ERROR(f'Scheduler terminated unexpectedly: {str(e)}'))
        finally:
            self.stdout.write(self.style.SUCCESS('Scheduled message processor shut down.')) 