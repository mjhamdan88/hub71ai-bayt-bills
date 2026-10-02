from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from unicrm.models import Communication, CommunicationMessage, Company, Contact, Segment
from unicom.models import Channel


class RetryDeliveryApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='staff', password='pass', is_staff=True)
        self.client.force_login(self.user)
        self.company = Company.objects.create(name='ACME')
        self.contact = Contact.objects.create(
            first_name='Retry',
            last_name='Candidate',
            email='retry@example.com',
            company=self.company,
        )
        self.channel = Channel.objects.create(
            name='Email',
            platform='Email',
            config={},
            active=True,
        )
        self.segment = Segment.objects.create(
            name='All',
            description='All ACME contacts',
            code=f"""
def apply(qs):
    return qs.filter(company_id={self.company.pk})
""",
        )
        self.communication = Communication.objects.create(
            segment=self.segment,
            channel=self.channel,
            initiated_by=self.user,
            scheduled_for=timezone.now(),
            subject_template='Hello',
            content='<p>Content</p>',
        )
        self.delivery = CommunicationMessage.objects.create(
            communication=self.communication,
            contact=self.contact,
            status='failed',
            metadata={'status': 'failed', 'errors': ['Network issue']},
            scheduled_at=timezone.now(),
        )

    def test_staff_can_retry_failed_delivery(self):
        url = reverse('unicrm:delivery-retry', args=[self.delivery.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, 'scheduled')
        self.assertEqual(self.delivery.metadata.get('status'), 'scheduled')
        self.assertIsNotNone(self.delivery.scheduled_at)

    def test_retry_requires_failed_status(self):
        self.delivery.status = 'sent'
        self.delivery.save(update_fields=['status'])
        url = reverse('unicrm:delivery-retry', args=[self.delivery.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload['ok'])

    def test_staff_can_retry_bounced_delivery_and_clear_contact(self):
        self.delivery.status = 'bounced'
        self.delivery.metadata = {'status': 'bounced', 'errors': ['Blocked by Reacher pre-send validation']}
        self.delivery.save(update_fields=['status', 'metadata'])

        self.contact.email_bounced = True
        self.contact.email_bounced_at = timezone.now()
        self.contact.email_bounce_type = 'hard'
        self.contact.save(update_fields=['email_bounced', 'email_bounced_at', 'email_bounce_type'])

        url = reverse('unicrm:delivery-retry', args=[self.delivery.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])

        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, 'scheduled')
        self.assertEqual(self.delivery.metadata.get('status'), 'scheduled')
        self.assertIsNotNone(self.delivery.scheduled_at)

        self.contact.refresh_from_db()
        self.assertFalse(self.contact.email_bounced)
        self.assertIsNone(self.contact.email_bounced_at)
        self.assertEqual(self.contact.email_bounce_type, '')

    def test_non_staff_users_blocked(self):
        self.client.logout()
        url = reverse('unicrm:delivery-retry', args=[self.delivery.pk])
        response = self.client.post(url)
        # staff_member_required redirects unauthenticated/unauthorized users
        self.assertEqual(response.status_code, 302)
