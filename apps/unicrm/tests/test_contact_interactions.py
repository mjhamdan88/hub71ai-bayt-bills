from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase
from django.utils import timezone

from unicom.models import Account, Channel, Chat, Message
from unicrm.models import (
    Communication,
    CommunicationMessage,
    Company,
    Contact,
    MailingList,
    Segment,
    Subscription,
    UnsubscribeAll,
)
from unicrm.services.communication_scheduler import prepare_deliveries_for_communication
from unicrm.services.contact_interaction_cache import refresh_contact_cache
from unicrm.services.unsubscribe_links import UNSUBSCRIBE_SALT
from unicrm.services.template_renderer import render_template_for_contact


class ContactInteractionCacheTests(TestCase):
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
        self.mailing_list = MailingList.objects.create(name='Newsletter', public_name='Newsletter', slug='newsletter')
        Subscription.objects.create(contact=self.contact, mailing_list=self.mailing_list)
        self.channel = Channel.objects.create(
            name='Email Channel',
            platform='Email',
            config={
                'EMAIL_ADDRESS': 'noreply@example.com',
                'EMAIL_PASSWORD': 'password',
            },
            active=True,
        )
        self.segment = Segment.objects.create(
            name='Test Contacts',
            description='Contacts for the Acme Inc. company.',
            code=f"""
def apply(qs):
    return qs.filter(company_id={self.company.pk})
""",
        )

    def test_history_cache_captures_multiple_entries(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            subject_template="Hello {{ contact.first_name }}",
            content="<p>Hi</p>",
        )
        prepare_deliveries_for_communication(communication)
        delivery = communication.messages.first()

        account = Account.objects.create(id='acct1', channel=self.channel, platform='Email')
        chat = Chat.objects.create(id='chat1', channel=self.channel, platform='Email')
        msg = Message.objects.create(
            id='msg1',
            provider_message_id='p1',
            channel=self.channel,
            platform='Email',
            sender=account,
            chat=chat,
            is_outgoing=True,
            sender_name='Sender',
            subject='Hello John',
            text='Body',
            timestamp=timezone.now(),
            raw={},
        )
        msg.time_sent = timezone.now()
        msg.time_opened = timezone.now()
        msg.opened = True
        msg.save()

        delivery.message = msg
        delivery.status = 'sent'
        delivery.save(update_fields=['message', 'status'])

        refresh_contact_cache(self.contact)
        self.contact.refresh_from_db()
        history = self.contact.communication_history
        self.assertEqual(len(history), 1)
        entry = history[0]
        self.assertEqual(entry.get('subject'), 'Hello John')
        self.assertEqual(entry.get('direction'), 'outbound')
        self.assertEqual(entry.get('status'), 'sent')
        self.assertIsNotNone(entry.get('opened_at'))

    def test_prepare_skips_contact_with_unsubscribe_all(self):
        UnsubscribeAll.objects.create(contact=self.contact)
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content="<p>Hi</p>",
        )

        result = prepare_deliveries_for_communication(communication)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(communication.messages.count(), 0)

    def test_unsubscribe_link_variable_available(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content="<p>Hi</p>",
        )
        result = render_template_for_contact(
            "<p>Hi</p>",
            contact=self.contact,
            communication=communication,
        )
        html_link = result.variables.get('unsubscribe_link')
        self.assertTrue(html_link)
        self.assertIn('<a href=', str(html_link))
        href_part = str(html_link).split('href="')[1]
        url = href_part.split('"')[0]
        token = url.split('token=')[1]
        payload = signing.loads(token, salt=UNSUBSCRIBE_SALT)
        self.assertEqual(payload.get('contact_id'), self.contact.pk)
        self.assertEqual(payload.get('mailing_list_slug'), self.mailing_list.slug)

    def test_unsubscribe_click_not_counted_as_engagement(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            subject_template="Hello {{ contact.first_name }}",
            content="<p>Hi</p>",
        )
        prepare_deliveries_for_communication(communication)
        delivery = communication.messages.first()

        account = Account.objects.create(id='acct3', channel=self.channel, platform='Email')
        chat = Chat.objects.create(id='chat3', channel=self.channel, platform='Email')
        unsubscribe_url = "https://example.com/unicrm/unsubscribe/?token=abc"
        msg = Message.objects.create(
            id='msg3',
            provider_message_id='p3',
            channel=self.channel,
            platform='Email',
            sender=account,
            chat=chat,
            is_outgoing=True,
            sender_name='Sender',
            subject='Hello John',
            text='Body',
            timestamp=timezone.now(),
            raw={},
        )
        msg.clicked_links = [unsubscribe_url]
        msg.link_clicked = True
        msg.save(update_fields=['clicked_links', 'link_clicked'])
        delivery.message = msg
        delivery.status = 'sent'
        delivery.metadata = {'clicked_links': [unsubscribe_url]}
        delivery.save(update_fields=['message', 'status', 'metadata'])

        communication.refresh_status_summary()
        self.assertEqual(communication.status_summary.get('unsubscribed'), 1)
        self.assertEqual(communication.status_summary.get('clicked'), 0)

    def test_failed_deliveries_not_cached(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content="<p>Hi</p>",
        )
        prepare_deliveries_for_communication(communication)
        delivery = communication.messages.first()
        delivery.status = 'failed'
        delivery.save(update_fields=['status'])

        refresh_contact_cache(self.contact)
        self.contact.refresh_from_db()
        self.assertEqual(len(self.contact.communication_history), 0)

    def test_bounced_deliveries_not_cached(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content="<p>Hi</p>",
        )
        prepare_deliveries_for_communication(communication)
        delivery = communication.messages.first()
        delivery.status = 'bounced'
        delivery.save(update_fields=['status'])

        refresh_contact_cache(self.contact)
        self.contact.refresh_from_db()
        self.assertEqual(len(self.contact.communication_history), 0)

    def test_opened_without_timestamp_counts_as_engaged(self):
        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            subject_template="Hello {{ contact.first_name }}",
            content="<p>Hi</p>",
        )
        prepare_deliveries_for_communication(communication)
        delivery = communication.messages.first()

        account = Account.objects.create(id='acct2', channel=self.channel, platform='Email')
        chat = Chat.objects.create(id='chat2', channel=self.channel, platform='Email')
        msg = Message.objects.create(
            id='msg2',
            provider_message_id='p2',
            channel=self.channel,
            platform='Email',
            sender=account,
            chat=chat,
            is_outgoing=True,
            sender_name='Sender',
            subject='Hello John',
            text='Body',
            timestamp=timezone.now(),
            raw={},
        )
        msg.opened = True
        msg.save(update_fields=['opened'])
        delivery.message = msg
        delivery.status = 'sent'
        delivery.save(update_fields=['message', 'status'])

        refresh_contact_cache(self.contact)
        self.contact.refresh_from_db()
        history = self.contact.communication_history
        self.assertEqual(len(history), 1)
        self.assertIsNotNone(history[0].get('opened_at'))

    def test_prepare_skips_recently_contacted(self):
        recent_time = (timezone.now() - timedelta(hours=1)).isoformat()
        self.contact.communication_history = [{
            'direction': 'outbound',
            'status': 'sent',
            'sent_at': recent_time,
            'subject': 'Earlier',
            'message_id': 'm-recent',
        }]
        self.contact.save(update_fields=['communication_history'])

        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content="<p>Hi</p>",
        )

        result = prepare_deliveries_for_communication(communication)
        self.assertEqual(result.skipped, 1)
        delivery = communication.messages.first()
        self.assertEqual(delivery.status, 'failed')

    def test_prepare_skips_unengaged_threshold(self):
        self.contact.communication_history = [
            {'direction': 'outbound', 'status': 'sent', 'sent_at': (timezone.now() - timedelta(days=3)).isoformat(), 'message_id': 'm1'},
            {'direction': 'outbound', 'status': 'sent', 'sent_at': (timezone.now() - timedelta(days=2)).isoformat(), 'message_id': 'm2'},
            {'direction': 'outbound', 'status': 'sent', 'sent_at': (timezone.now() - timedelta(days=1)).isoformat(), 'message_id': 'm3'},
        ]
        self.contact.save(update_fields=['communication_history'])

        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content="<p>Hi</p>",
        )

        result = prepare_deliveries_for_communication(communication)
        self.assertEqual(result.skipped, 1)
        delivery = communication.messages.first()
        self.assertEqual(delivery.status, 'failed')

    def test_reply_counts_as_engagement(self):
        self.contact.communication_history = [
            {'direction': 'outbound', 'status': 'sent', 'sent_at': (timezone.now() - timedelta(days=3)).isoformat(), 'has_received_reply': True},
            {'direction': 'outbound', 'status': 'sent', 'sent_at': (timezone.now() - timedelta(days=2)).isoformat()},
            {'direction': 'outbound', 'status': 'sent', 'sent_at': (timezone.now() - timedelta(days=1)).isoformat()},
        ]
        self.contact.save(update_fields=['communication_history'])

        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content="<p>Hi</p>",
        )

        result = prepare_deliveries_for_communication(communication)
        self.assertEqual(result.skipped, 0)

    def test_scheduled_only_entries_not_counted_for_cooldown(self):
        now = timezone.now()
        self.contact.communication_history = [
            {'direction': 'outbound', 'status': 'scheduled', 'sent_at': now.isoformat()},
            {'direction': 'outbound', 'status': 'sent', 'sent_at': (now - timedelta(days=10)).isoformat(), 'opened_at': (now - timedelta(days=9)).isoformat(), 'message_id': 'm1'},
            {'direction': 'outbound', 'status': 'sent', 'sent_at': (now - timedelta(days=20)).isoformat(), 'opened_at': (now - timedelta(days=19)).isoformat(), 'message_id': 'm2'},
        ]
        self.contact.save(update_fields=['communication_history'])

        communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            content="<p>Hi</p>",
        )

        result = prepare_deliveries_for_communication(communication)
        self.assertEqual(result.skipped, 0)
