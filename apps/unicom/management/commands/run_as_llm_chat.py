from django.core.management.base import BaseCommand
from unicom.models import Message
import json

class Command(BaseCommand):
    help = 'Retrieves a message by ID, runs as_llm_chat, and prints the result.'

    def add_arguments(self, parser):
        parser.add_argument('message_id', type=int, help='The ID of the message to retrieve.')

    def handle(self, *args, **options):
        message_id = options['message_id']
        message = Message.objects.get(id=message_id)
        message.reply_using_llm(model="o4-mini-2025-04-16", mode="thread")
        self.stdout.write(self.style.SUCCESS(f"Message with ID {message_id} replied using LLM."))