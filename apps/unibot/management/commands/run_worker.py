from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from unicom.models.request import Request
from unibot.models import Bot
import importlib.util
import os
import time
from django.conf import settings
from openai import OpenAI
import traceback


def claim_due_retry(request, *, now=None):
    """Transition one already-locked failed request back to the work queue."""
    if request.status != 'FAILED':
        return False
    claimed_at = now or timezone.now()
    request.status = 'QUEUED'
    request.retry_count += 1
    request.last_retried_at = claimed_at
    request.next_retry_at = None
    request.save(update_fields=[
        'status', 'retry_count', 'last_retried_at', 'next_retry_at',
    ])
    return True


class Command(BaseCommand):
    help = 'Run the bot worker to process requests.'

    def add_arguments(self, parser):
        parser.add_argument('--bot-id', type=int, help='ID of the bot to use (optional)')
        parser.add_argument('--status', type=str, help='Status of requests to process (default: QUEUED)', default='QUEUED')
        parser.add_argument('--limit', type=int, help='Limit number of requests to process per loop')
        parser.add_argument('--sleep', type=int, help='Seconds to sleep between loops', default=2)

    def handle(self, *args, **options):
        bot_id = options.get('bot_id')
        status = options.get('status', 'QUEUED')
        limit = options.get('limit')
        sleep_time = options.get('sleep', 2)

        self.stdout.write(self.style.SUCCESS('Starting worker. Press Ctrl+C to stop.'))
        try:
            while True:
                if bot_id:
                    bots = Bot.objects.filter(id=bot_id)
                else:
                    bots = Bot.objects.all()
                bot_map = {bot.request_category_id: bot for bot in bots if bot.request_category_id}
                if not bot_map:
                    self.stdout.write(self.style.WARNING('No bots with request categories found.'))
                    time.sleep(sleep_time)
                    continue
                categories = list(bot_map.keys())
                # Get requests for these categories
                qs = Request.objects.select_for_update(skip_locked=True).filter(category_id__in=categories)
                if status == 'QUEUED':
                    qs = qs.filter(
                        Q(status='QUEUED')
                        | Q(status='FAILED', next_retry_at__lte=timezone.now())
                    )
                else:
                    qs = qs.filter(status=status)
                qs = qs.order_by('created_at')
                if limit:
                    qs = qs[:limit]
                processed = 0
                with transaction.atomic():
                    for req in qs:
                        claim_due_retry(req)
                        bot = bot_map.get(req.category_id)
                        if not bot:
                            self.stderr.write(self.style.ERROR(f'No bot found for category {req.category_id}'))
                            continue
                        result = bot.process_request(req)
                        if result:
                            processed += 1
                            self.stdout.write(self.style.SUCCESS(f'Processed request {req.id}'))
                        else:
                            self.stderr.write(self.style.ERROR(f'Failed to process request {req.id}: {getattr(req, "error", "Unknown error")}'))
                if processed == 0:
                    time.sleep(sleep_time)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Worker stopped by user.'))
