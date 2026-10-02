from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from textwrap import dedent

from unicom.models import Account, Channel, Chat, Message
from unicrm.models import (
    Communication,
    CommunicationMessage,
    Company,
    Contact,
    Segment,
)
from unicrm.services.communication_dispatcher import process_scheduled_communications
from unicrm.services.communication_scheduler import prepare_deliveries_for_communication
from unicom.services.email.save_email_message import save_email_message


class CommunicationSchedulerTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create(username='marketing')
        self.company = Company.objects.create(name='Acme Inc.')
        self.contact = Contact.objects.create(
            first_name='John',
            last_name='Doe',
            email='john@example.com',
            company=self.company,
        )
        self.channel = Channel.objects.create(
            name='Email Channel',
            platform='Email',
            config={
                'EMAIL_ADDRESS': 'noreply@example.com',
                'EMAIL_PASSWORD': 'password',
            },
            active=True,
        )
        self.html_content = '<p>Hello <!--mce:protected %7B%7B%20contact.first_name%20%7D%7D-->!</p>'
        self.segment = Segment.objects.create(
            name='Test Contacts',
            description='Contacts for the Acme Inc. company (allows blank emails).',
            code=f"""
def apply(qs):
    return qs.filter(company_id={self.company.pk})
""",
        )

    def test_preparation_creates_payloads(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now() + timedelta(hours=1),
            subject_template="Hello <!--mce:protected %7B%7B%20contact.first_name%20%7D%7D-->",
            content=self.html_content,
        )

        result = prepare_deliveries_for_communication(communication)

        communication.refresh_from_db()
        self.assertEqual(result.created, 1)
        self.assertEqual(communication.status, 'scheduled')
        self.assertEqual(communication.messages.count(), 1)
        delivery = communication.messages.first()
        self.assertEqual(delivery.status, 'scheduled')
        self.assertIsNotNone(delivery.scheduled_at)
        payload = delivery.metadata.get('payload')
        self.assertEqual(payload['to'], [self.contact.email])
        self.assertEqual(payload['subject'], 'Hello John')
        self.assertIn('Hello John', payload['html'])
        self.assertEqual(communication.status_summary.get('total'), 1)
        self.assertEqual(communication.status_summary.get('clicked'), 0)

    def test_gp_validation_skips_reacher(self):
        self.contact.gp_email_status = 'valid'
        self.contact.gp_email_checked_at = timezone.now() - timedelta(days=10)
        self.contact.save(update_fields=['gp_email_status', 'gp_email_checked_at'])

        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            subject_template="Hello",
            content=self.html_content,
        )

        prepare_deliveries_for_communication(communication)
        delivery = communication.messages.first()
        metadata = delivery.metadata or {}
        payload = metadata.get('payload') or {}
        self.assertTrue(metadata.get('skip_reacher'))
        self.assertEqual(metadata.get('gp_validation_status'), 'valid')
        self.assertTrue(payload.get('skip_reacher'))

    def test_gp_invalid_blocks_and_marks_bounced(self):
        self.contact.gp_email_status = 'invalid'
        self.contact.gp_email_checked_at = timezone.now() - timedelta(days=5)
        self.contact.save(update_fields=['gp_email_status', 'gp_email_checked_at'])

        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            subject_template="Hello",
            content=self.html_content,
        )

        result = prepare_deliveries_for_communication(communication)
        delivery = communication.messages.first()
        metadata = delivery.metadata or {}
        self.assertEqual(delivery.status, 'bounced')
        self.assertEqual(metadata.get('status'), 'bounced')
        self.assertEqual(metadata.get('gp_validation_status'), 'invalid')
        errors = metadata.get('errors', [])
        self.assertTrue(any('GetProspect' in err for err in errors))
        # Should be counted as skipped/bounced in preparation outcome
        self.assertEqual(result.skipped, 1)

    def test_refresh_summary_updates_when_sent(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content=self.html_content,
        )
        prepare_deliveries_for_communication(communication)

        delivery = communication.messages.first()
        metadata = delivery.metadata or {}
        metadata['status'] = 'sent'
        delivery.metadata = metadata
        delivery.status = 'sent'
        delivery.save(update_fields=['metadata', 'status'])

        communication.refresh_from_db()
        communication.refresh_status_summary()
        self.assertEqual(communication.status_summary.get('sent'), 1)
        self.assertEqual(communication.status, 'completed')

    def test_contacts_without_email_are_skipped(self):
        contact = Contact.objects.create(
            first_name='NoEmail',
            email='',
            company=self.company,
        )
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content=self.html_content,
        )

        result = prepare_deliveries_for_communication(communication)

        self.assertEqual(result.skipped, 1)  # the blank email contact
        self.assertEqual(CommunicationMessage.objects.filter(communication=communication).count(), 2)
        statuses = set(communication.messages.values_list('status', flat=True))
        self.assertIn('skipped', statuses)
        self.assertIn('scheduled', statuses)

    def test_bounce_updates_contact_and_metadata(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content=self.html_content,
        )
        prepare_deliveries_for_communication(communication)

        delivery = communication.messages.first()
        account = Account.objects.create(
            id=self.channel.config['EMAIL_ADDRESS'],
            channel=self.channel,
            platform='Email',
            name='Sender',
        )
        chat = Chat.objects.create(
            id='chat-1',
            channel=self.channel,
            platform='Email',
        )
        send_time = timezone.now()
        message = Message.objects.create(
            id='<msg-1@example.com>',
            channel=self.channel,
            platform='Email',
            sender=account,
            chat=chat,
            is_outgoing=True,
            sender_name='Marketing',
            subject='Subject',
            text='Body',
            html='<p>Body</p>',
            to=[self.contact.email],
            timestamp=send_time,
            time_sent=send_time,
            sent=True,
            raw={},
        )

        metadata = delivery.metadata or {}
        metadata['status'] = 'sent'
        delivery.metadata = metadata
        delivery.message = message
        delivery.status = 'sent'
        delivery.save(update_fields=['metadata', 'message', 'status', 'updated_at'])

        bounce_email = dedent(f"""\
            From: Mail Delivery Subsystem <mailer-daemon@yandex.ru>
            To: {self.channel.config['EMAIL_ADDRESS']}
            Subject: Undelivered Mail Returned to Sender
            Message-ID: <bounce-1@example.com>
            Date: Mon, 03 Nov 2025 16:57:00 +0300
            Content-Type: multipart/report; boundary="b1"

            --b1
            Content-Type: text/plain; charset="utf-8"

            This is the mail system at host yandex.ru.

            <{self.contact.email}>: host mx.example.com said: 554 5.1.1 Unknown user; user not found
            Message-ID: {message.id}

            --b1--
        """).encode('utf-8')

        save_email_message(self.channel, bounce_email)

        message.refresh_from_db()
        self.assertTrue(message.bounced)
        self.assertEqual(message.bounce_type, 'hard')
        self.assertIn(self.contact.email, message.bounce_details.get('recipients', []))
        bounce_time = message.time_bounced
        self.assertIsNotNone(bounce_time)

        delivery.refresh_from_db()
        self.assertEqual(delivery.metadata.get('status'), 'bounced')

        communication.refresh_from_db()
        communication.refresh_status_summary()
        self.assertEqual(communication.status_summary.get('bounced'), 1)
        self.assertEqual(communication.status_summary.get('failed'), 0)

        self.contact.refresh_from_db()
        self.assertTrue(self.contact.email_bounced)
        self.assertEqual(self.contact.email_bounce_type, 'hard')
        self.assertIsNotNone(self.contact.email_bounced_at)
        self.assertLess(
            abs(self.contact.email_bounced_at - bounce_time),
            timedelta(seconds=1),
        )

        followup = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content=self.html_content,
        )
        result = prepare_deliveries_for_communication(followup)

        followup_delivery = followup.messages.first()
        self.assertIsNone(followup_delivery)
        self.assertEqual(result.skipped, 0)

        followup.refresh_status_summary()
        self.assertEqual(followup.status_summary.get('bounced'), 0)
        self.assertEqual(followup.status_summary.get('failed'), 0)
        self.assertEqual(followup.status, 'scheduled')

    def test_evergreen_status_goes_ongoing(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content=self.html_content,
            auto_enroll_new_contacts=True,
        )
        prepare_deliveries_for_communication(communication)
        delivery = communication.messages.first()
        metadata = delivery.metadata or {}
        metadata['status'] = 'sent'
        delivery.metadata = metadata
        delivery.status = 'sent'
        delivery.save(update_fields=['metadata', 'status'])

        communication.refresh_status_summary()
        self.assertEqual(communication.status, 'ongoing')

    def test_auto_enroll_creates_message_for_new_contact(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content=self.html_content,
            auto_enroll_new_contacts=True,
        )
        prepare_deliveries_for_communication(communication)
        self.assertEqual(communication.messages.count(), 1)

        new_contact = Contact.objects.create(
            first_name='Late',
            last_name='Joiner',
            email='late@example.com',
            company=self.company,
        )

        communication.refresh_from_db()
        deliveries = communication.messages.filter(contact=new_contact)
        self.assertEqual(deliveries.count(), 1)
        delivery = deliveries.first()
        self.assertEqual(delivery.status, 'scheduled')
        self.assertEqual(delivery.metadata.get('status'), 'scheduled')

    def test_evergreen_refresh_handles_time_based_segments(self):
        rolling_segment = Segment.objects.create(
            name='Older than a day',
            description='Contacts whose account age exceeds 24h.',
            code=dedent(
                """
def apply(qs):
    cutoff = timezone.now() - timezone.timedelta(days=1)
    return qs.filter(created_at__lte=cutoff)
"""
            ),
        )
        late_contact = Contact.objects.create(
            first_name='Timer',
            last_name='Based',
            email='timer@example.com',
            company=self.company,
        )
        Contact.objects.filter(pk=self.contact.pk).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        self.contact.refresh_from_db()

        future_scheduled_for = timezone.now() + timedelta(days=5)
        communication = Communication.objects.create(
            segment=rolling_segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=future_scheduled_for,
            content=self.html_content,
            auto_enroll_new_contacts=True,
        )
        prepare_deliveries_for_communication(communication)
        initial_refresh = communication.evergreen_refreshed_at

        initial_delivery = communication.messages.get(contact=self.contact)
        metadata = initial_delivery.metadata or {}
        metadata['status'] = 'sent'
        initial_delivery.metadata = metadata
        initial_delivery.status = 'sent'
        initial_delivery.save(update_fields=['metadata', 'status'])

        communication.refresh_from_db()
        communication.refresh_status_summary()
        self.assertEqual(communication.status, 'ongoing')
        self.assertFalse(
            communication.messages.filter(contact=late_contact).exists()
        )
        initial_contact_ids = set(
            communication.messages.values_list('contact_id', flat=True)
        )
        self.assertIsNotNone(initial_refresh)

        future_time = timezone.now() + timedelta(days=2)
        with self.settings(
            UNICRM_EVERGREEN_REFRESH_INTERVAL_SECONDS=0,
            ENABLE_IMAP_AUTOSTART=False,
        ):
            with patch('django.utils.timezone.now', return_value=future_time):
                process_scheduled_communications(now=future_time)

        communication.refresh_from_db()
        new_delivery = communication.messages.filter(contact=late_contact).first()
        self.assertIsNotNone(new_delivery)
        self.assertEqual(new_delivery.status, 'scheduled')
        self.assertEqual(new_delivery.scheduled_at, future_scheduled_for)
        all_contact_ids = set(
            communication.messages.values_list('contact_id', flat=True)
        )
        self.assertGreaterEqual(len(all_contact_ids), len(initial_contact_ids) + 1)
        self.assertIn(late_contact.id, all_contact_ids)
        self.assertIsNotNone(communication.evergreen_refreshed_at)
        self.assertGreater(communication.evergreen_refreshed_at, initial_refresh)

    def test_prepare_deliveries_throttles_large_audiences(self):
        base_time = timezone.now()
        # create additional contacts to exceed threshold
        for idx in range(20):
            Contact.objects.create(
                first_name=f'Contact{idx}',
                email=f'user{idx}@example.com',
                company=self.company,
            )
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=base_time,
            content=self.html_content,
        )
        communication.scheduled_for = base_time
        communication.save(update_fields=['scheduled_for'])

        burst_limit = 4
        with self.settings(
            UNICRM_DELIVERY_BURST_LIMIT=burst_limit,
            UNICRM_DELIVERY_DRIP_MIN_MINUTES=1,
            UNICRM_DELIVERY_DRIP_MAX_MINUTES=2,
        ):
            prepare_deliveries_for_communication(communication)

        deliveries = list(communication.messages.order_by('pk'))
        self.assertEqual(len(deliveries), Contact.objects.filter(company=self.company).count())

        first_batch_time = deliveries[0].scheduled_at
        for idx, delivery in enumerate(deliveries):
            if idx < burst_limit:
                self.assertEqual(delivery.scheduled_at, first_batch_time)
            else:
                delta = (delivery.scheduled_at - first_batch_time).total_seconds()
                self.assertGreaterEqual(delta, 60)
                prev_delta = (delivery.scheduled_at - deliveries[idx - 1].scheduled_at).total_seconds()
                self.assertGreaterEqual(prev_delta, 60)
                self.assertLessEqual(prev_delta, 120)

    def test_prepare_does_not_automatically_reschedule_failed_deliveries(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content=self.html_content,
        )
        prepare_deliveries_for_communication(communication)
        delivery = communication.messages.first()
        delivery.status = 'failed'
        metadata = delivery.metadata or {}
        metadata['status'] = 'failed'
        metadata['errors'] = ['Bounce']
        delivery.metadata = metadata
        delivery.save(update_fields=['status', 'metadata'])

        prepare_deliveries_for_communication(communication)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, 'failed')
        self.assertEqual(delivery.metadata.get('status'), 'failed')

    def test_reply_updates_status_summary(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content=self.html_content,
        )
        prepare_deliveries_for_communication(communication)

        delivery = communication.messages.first()

        account = Account.objects.create(
            id=self.channel.config['EMAIL_ADDRESS'],
            channel=self.channel,
            platform='Email',
            name='Sender',
        )
        chat = Chat.objects.create(
            id='chat-reply',
            channel=self.channel,
            platform='Email',
        )

        sent_time = timezone.now()
        outgoing_message = Message.objects.create(
            id='<outgoing@example.com>',
            channel=self.channel,
            platform='Email',
            sender=account,
            chat=chat,
            is_outgoing=True,
            sender_name='Marketing',
            subject='Subject',
            text='Body',
            html='<p>Body</p>',
            to=[self.contact.email],
            timestamp=sent_time,
            time_sent=sent_time,
            sent=True,
            raw={},
        )

        metadata = delivery.metadata or {}
        metadata['status'] = 'sent'
        metadata['chat_id'] = chat.id
        delivery.metadata = metadata
        delivery.message = outgoing_message
        delivery.status = 'sent'
        delivery.save(update_fields=['metadata', 'message', 'status', 'updated_at'])

        reply_time = sent_time + timedelta(minutes=5)
        contact_account = Account.objects.create(
            id=self.contact.email,
            channel=self.channel,
            platform='Email',
            name=self.contact.email,
        )
        reply_message = Message.objects.create(
            id='<reply@example.com>',
            channel=self.channel,
            platform='Email',
            sender=contact_account,
            chat=chat,
            is_outgoing=False,
            sender_name='Contact',
            subject='Re: Subject',
            text='Reply body',
            html='<p>Reply body</p>',
            to=[self.channel.config['EMAIL_ADDRESS']],
            timestamp=reply_time,
            time_sent=reply_time,
            sent=True,
            reply_to_message=outgoing_message,
            raw={},
        )

        delivery.refresh_from_db()
        self.assertTrue(delivery.has_received_reply)
        self.assertEqual(delivery.status, 'sent')
        self.assertIsNotNone(delivery.replied_at)
        self.assertIn(reply_message.id, delivery.metadata.get('replies', []))
        self.assertEqual(delivery.metadata.get('chat_id'), chat.id)

        communication.refresh_from_db()
        communication.refresh_status_summary()
        summary = communication.status_summary
        self.assertEqual(summary.get('replied'), 1)
