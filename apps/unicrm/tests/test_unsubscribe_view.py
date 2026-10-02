from django.test import Client, TestCase
from django.utils import timezone

from unicrm.models import Communication, CommunicationMessage, Contact, MailingList, Segment, Subscription, UnsubscribeAll
from unicrm.services.unsubscribe_links import build_unsubscribe_token


class UnsubscribeViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.contact = Contact.objects.create(email='john@example.com')
        self.mailing_list = MailingList.objects.create(name='Newsletter', public_name='Newsletter', slug='newsletter')
        self.subscription = Subscription.objects.create(contact=self.contact, mailing_list=self.mailing_list)
        self.segment = Segment.objects.create(
            name='All',
            description='All contacts',
            code='''\n\ndef apply(qs):\n    return qs\n''',
        )
        self.communication = Communication.objects.create(segment=self.segment)
        self.delivery = CommunicationMessage.objects.create(
            communication=self.communication,
            contact=self.contact,
            status='sent',
            metadata={},
        )

    def test_get_renders_page(self):
        token = build_unsubscribe_token(self.contact, mailing_list=self.mailing_list)
        response = self.client.get('/unicrm/unsubscribe/', {'token': token})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'john@example.com')
        self.assertContains(response, 'Newsletter')

    def test_unsubscribe_list(self):
        token = build_unsubscribe_token(self.contact, mailing_list=self.mailing_list)
        response = self.client.post('/unicrm/unsubscribe/', {'token': token, 'action': 'unsubscribe_list'})
        self.assertEqual(response.status_code, 200)
        self.subscription.refresh_from_db()
        self.assertIsNotNone(self.subscription.unsubscribed_at)
        self.assertFalse(UnsubscribeAll.objects.filter(contact=self.contact).exists())
        self.assertNotContains(response, '<form', html=False)

    def test_unsubscribe_all(self):
        token = build_unsubscribe_token(self.contact, communication=self.communication)
        response = self.client.post('/unicrm/unsubscribe/', {'token': token, 'action': 'unsubscribe_all'})
        self.assertEqual(response.status_code, 200)
        unsub = UnsubscribeAll.objects.filter(contact=self.contact).first()
        self.assertIsNotNone(unsub)
        self.assertEqual(unsub.communication, self.communication)
        self.subscription.refresh_from_db()
        self.assertIsNotNone(self.subscription.unsubscribed_at)
        self.assertNotContains(response, '<form', html=False)
        self.delivery.refresh_from_db()
        self.assertEqual((self.delivery.metadata or {}).get('status'), 'unsubscribed')
        self.communication.refresh_from_db()
        self.assertEqual(self.communication.status_summary.get('unsubscribed'), 1)
        self.assertEqual(self.communication.status_summary.get('failed'), 0)
        self.assertEqual(self.communication.status_summary.get('bounced'), 0)
