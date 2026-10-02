from django.core.management.base import BaseCommand

from unicrm.models import Contact
from unicrm.services.contact_interaction_cache import refresh_contact_cache


class Command(BaseCommand):
    help = "Rebuild the communication history cache for contacts."

    def add_arguments(self, parser):
        parser.add_argument(
            '--contact-id',
            type=int,
            help='Refresh a single contact by id',
        )

    def handle(self, *args, **options):
        contact_id = options.get('contact_id')
        if contact_id:
            contact = Contact.objects.filter(pk=contact_id).first()
            if not contact:
                self.stdout.write(self.style.ERROR(f'Contact {contact_id} not found'))
                return
            refresh_contact_cache(contact)
            self.stdout.write(self.style.SUCCESS(f'Refreshed cache for contact {contact_id}'))
            return

        qs = Contact.objects.order_by('pk').iterator()
        refreshed = 0
        for contact in qs:
            refresh_contact_cache(contact)
            refreshed += 1
            if refreshed % 50 == 0:
                self.stdout.write(f'Refreshed {refreshed} contacts...')
        self.stdout.write(self.style.SUCCESS(f'Finished. Refreshed {refreshed} contacts.'))
