from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from unicom.models import Channel
from unicrm.models import Communication, Company, Contact, Segment
from unicrm.services.communication_dispatcher import process_scheduled_communications


class CommunicationDispatcherTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create(username='scheduler')
        self.company = Company.objects.create(name='Acme Inc.')
        self.contact = Contact.objects.create(
            first_name='Jane',
            last_name='Doe',
            email='jane@example.com',
            company=self.company,
        )
        self.channel = Channel.objects.create(
            name='Email Channel',
            platform='Email',
            config={},
            active=True,
        )
        self.segment = Segment.objects.create(
            name='All contacts',
            description='All contacts',
            code="""
from unicrm.models import Contact

def apply(qs):
    return qs
""",
        )

    def _create_communication(self, scheduled_for):
        return Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=scheduled_for,
            subject_template='Hello <!--mce:protected %7B%7B%20contact.first_name%20%7D%7D-->',
            content='<p>Hello <!--mce:protected %7B%7B%20contact.first_name%20%7D%7D--></p>',
            status='scheduled',
        )

    def test_processes_due_communications(self):
        scheduled_at = timezone.now() - timedelta(minutes=1)
        communication = self._create_communication(scheduled_at)

        with mock.patch('unicom.models.channel.Channel.send_message', return_value=None) as send_message:
            summary = process_scheduled_communications(now=timezone.now())

        send_message.assert_called()
        communication.refresh_from_db()
        status = communication.messages.values_list('metadata__status', flat=True).first()
        details = summary.get('details', [])
        self.assertTrue(details)

        self.assertEqual(summary['communications_processed'], 1)
        self.assertEqual(summary['messages_sent'], 1)
        self.assertEqual(summary['messages_failed'], 0)
        self.assertEqual(status, 'sent')
        self.assertEqual(communication.status, 'completed')
        self.assertEqual(details[0]['subject'], 'Hello Jane')
        self.assertIn('Hello Jane', details[0]['html'])

    def test_skips_future_communications(self):
        scheduled_at = timezone.now() + timedelta(hours=1)
        communication = self._create_communication(scheduled_at)

        with mock.patch('unicom.models.channel.Channel.send_message') as send_message:
            summary = process_scheduled_communications(now=timezone.now())

        communication.refresh_from_db()
        self.assertEqual(summary['communications_processed'], 0)
        self.assertEqual(summary['messages_sent'], 0)
        self.assertEqual(summary['messages_failed'], 0)
        self.assertEqual(communication.status, 'scheduled')
        send_message.assert_not_called()

    def test_records_failures(self):
        scheduled_at = timezone.now() - timedelta(minutes=5)
        communication = self._create_communication(scheduled_at)

        with mock.patch('unicom.models.channel.Channel.send_message', side_effect=RuntimeError('boom')):
            summary = process_scheduled_communications(now=timezone.now())

        communication.refresh_from_db()
        status = communication.messages.values_list('metadata__status', flat=True).first()
        details = summary.get('details', [])
        self.assertTrue(details)

        self.assertEqual(summary['communications_processed'], 1)
        self.assertEqual(summary['messages_sent'], 0)
        self.assertEqual(summary['messages_failed'], 1)
        self.assertEqual(status, 'failed')
        self.assertEqual(communication.status, 'completed')
        self.assertEqual(details[0]['status'], 'failed')
        self.assertTrue(details[0]['errors'])

    def test_does_not_send_twice(self):
        scheduled_at = timezone.now() - timedelta(minutes=1)
        communication = self._create_communication(scheduled_at)

        with mock.patch('unicom.models.channel.Channel.send_message', return_value=None) as send_message:
            summary1 = process_scheduled_communications(now=timezone.now())
            self.assertEqual(send_message.call_count, 1)
            summary2 = process_scheduled_communications(now=timezone.now())
            self.assertEqual(send_message.call_count, 1)

        self.assertEqual(summary1['messages_sent'], 1)
        self.assertEqual(summary2['communications_processed'], 0)
