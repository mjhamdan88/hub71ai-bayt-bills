from datetime import timedelta

import pytz
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from unicom.models import Channel
from unicrm.models import Communication, Company, Contact, Segment
from unicrm.services.communication_scheduler import prepare_deliveries_for_communication


class CommunicationComposeViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='staff', password='pass', is_staff=True)
        self.client.force_login(self.user)

        self.company = Company.objects.create(name='ACME')
        self.contact = Contact.objects.create(
            first_name='Jane',
            last_name='Doe',
            email='jane@example.com',
            company=self.company,
        )
        self.channel = Channel.objects.create(
            name='Primary Email',
            platform='Email',
            config={},
            active=True,
        )
        Channel.objects.filter(pk=self.channel.pk).update(active=True)
        self.channel.refresh_from_db()
        self.segment = Segment.objects.create(
            name='Everyone',
            description='All contacts',
            code='''\nfrom unicrm.models import Contact\n\ndef apply(qs):\n    return qs\n''',
        )

    def test_single_channel_preselected(self):
        Channel.objects.filter(active=True, platform='Email').update(active=False)
        Channel.objects.filter(pk=self.channel.pk).update(active=True)
        only_channel = Channel.objects.filter(active=True, platform='Email').first()
        active_channels = list(Channel.objects.filter(active=True, platform='Email').values_list('pk', 'name'))
        self.assertEqual(active_channels, [(self.channel.pk, self.channel.name)])
        response = self.client.get(reverse('unicrm:communications-compose'))
        if only_channel:
            self.assertRegex(
                response.content.decode(),
                rf'<option value="{only_channel.pk}"[^>]*selected>'
            )

    def test_compose_send_now_defers_delivery_preparation(self):
        response = self.client.post(
            reverse('unicrm:communications-compose'),
            {
                'segment': self.segment.pk,
                'channel': self.channel.pk,
                'subject_template': 'Hi {{ contact.first_name }}',
                'content': '<p>Hello there</p>',
                'delivery_mode': 'now',
                'timezone': 'UTC',
            },
        )
        if response.status_code != 302:
            errors = response.context['form'].errors if response.context and 'form' in response.context else response.content.decode()
            self.fail(f"Unexpected response ({response.status_code}): {errors}")
        self.assertEqual(response.status_code, 302)
        communication = Communication.objects.latest('pk')
        self.assertEqual(communication.initiated_by, self.user)
        self.assertIn('Hello there', communication.content)
        self.assertEqual(communication.status, 'scheduled')
        self.assertIsNotNone(communication.scheduled_for)
        self.assertLess(
            abs(communication.scheduled_for - timezone.now()),
            timedelta(minutes=1),
        )
        self.assertEqual(communication.messages.count(), 0)

    def test_compose_schedule_for_future_defers_delivery_preparation(self):
        tz = pytz.timezone('America/New_York')
        future_local = timezone.now().astimezone(tz) + timedelta(hours=3)
        response = self.client.post(
            reverse('unicrm:communications-compose'),
            {
                'segment': self.segment.pk,
                'channel': self.channel.pk,
                'subject_template': '',
                'content': '<p>Scheduled</p>',
                'delivery_mode': 'schedule',
                'send_at': future_local.strftime('%Y-%m-%dT%H:%M'),
                'timezone': 'America/New_York',
            },
        )
        if response.status_code != 302:
            errors = response.context['form'].errors if response.context and 'form' in response.context else response.content.decode()
            self.fail(f"Unexpected response ({response.status_code}): {errors}")
        self.assertEqual(response.status_code, 302)
        communication = Communication.objects.latest('pk')
        self.assertEqual(communication.status, 'scheduled')
        self.assertIsNotNone(communication.scheduled_for)
        expected_utc = future_local.astimezone(pytz.UTC)
        self.assertLess(
            abs(communication.scheduled_for - expected_utc),
            timedelta(minutes=1),
        )
        self.assertEqual(communication.messages.count(), 0)

    def test_prepare_deliveries_prefers_custom_content(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            content='<p>Override</p>',
        )
        result = prepare_deliveries_for_communication(communication)
        self.assertGreaterEqual(result.created, 1)
        delivery = communication.messages.first()
        payload = delivery.metadata.get('payload')
        self.assertEqual(payload['html'].strip(), '<p>Override</p>')
        self.assertEqual(delivery.status, 'scheduled')

    def test_compose_can_enable_auto_enroll(self):
        response = self.client.post(
            reverse('unicrm:communications-compose'),
            {
                'segment': self.segment.pk,
                'channel': self.channel.pk,
                'subject_template': 'Hi {{ contact.first_name }}',
                'content': '<p>Hello there</p>',
                'delivery_mode': 'now',
                'timezone': 'UTC',
                'auto_enroll_new_contacts': 'on',
            },
        )
        if response.status_code != 302:
            errors = response.context['form'].errors if response.context and 'form' in response.context else response.content.decode()
            self.fail(f"Unexpected response ({response.status_code}): {errors}")
        communication = Communication.objects.latest('pk')
        self.assertTrue(communication.auto_enroll_new_contacts)
