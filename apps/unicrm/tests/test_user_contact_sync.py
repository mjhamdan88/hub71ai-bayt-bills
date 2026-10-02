from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from unicrm.models import Contact
from unicrm.services.user_contact_sync import ensure_contact_for_user


class UserContactSyncTests(TestCase):
    def setUp(self):
        self.User = get_user_model()

    def test_contact_created_for_new_user(self):
        user = self.User.objects.create_user(
            username='alice',
            email='alice@example.com',
            first_name='Alice',
            last_name='Anderson',
        )

        contact = Contact.objects.get(user=user)
        self.assertEqual(contact.email, 'alice@example.com')
        self.assertEqual(contact.first_name, 'Alice')
        self.assertEqual(contact.last_name, 'Anderson')
        self.assertIsNone(contact.owner)
        self.assertFalse(contact.attributes.get('auth_user_email_verified'))
        self.assertTrue(contact.attributes.get('auth_user_has_email'))
        self.assertEqual(contact.attributes.get('auth_user_id'), user.pk)

    def test_staff_user_sets_owner(self):
        user = self.User.objects.create_user(
            username='staffer',
            email='staffer@example.com',
            is_staff=True,
        )

        contact = Contact.objects.get(user=user)
        self.assertEqual(contact.owner, user)

    def test_email_updated_when_user_has_new_email(self):
        user = self.User.objects.create_user(
            username='no-email',
        )
        contact = Contact.objects.get(user=user)
        self.assertIsNone(contact.email)
        self.assertEqual(contact.first_name, 'no-email')
        self.assertEqual(str(contact), 'no-email')
        self.assertFalse(contact.attributes.get('auth_user_has_email'))

        user.email = 'updated@example.com'
        user.first_name = 'Updated'
        user.last_name = 'Person'
        user.save()

        contact.refresh_from_db()
        self.assertEqual(contact.email, 'updated@example.com')
        self.assertEqual(contact.first_name, 'Updated')
        self.assertEqual(contact.last_name, 'Person')
        self.assertFalse(contact.attributes.get('auth_user_email_verified'))
        self.assertTrue(contact.attributes.get('auth_user_has_email'))

    def test_verification_flag_updates_when_user_verified(self):
        user = self.User.objects.create_user(
            username='verifier',
            email='verify@example.com',
        )
        contact = Contact.objects.get(user=user)
        self.assertFalse(contact.attributes.get('auth_user_email_verified'))

        user = self.User.objects.get(pk=user.pk)
        setattr(user, 'email_verified', True)
        ensure_contact_for_user(user)

        contact.refresh_from_db()
        self.assertTrue(contact.attributes.get('auth_user_email_verified'))
        self.assertTrue(contact.attributes.get('auth_user_has_email'))

    def test_contact_email_cleared_when_user_email_removed(self):
        user = self.User.objects.create_user(
            username='remover',
            email='remove@example.com',
        )
        contact = Contact.objects.get(user=user)
        self.assertEqual(contact.email, 'remove@example.com')

        user.email = ''
        user.save()

        contact.refresh_from_db()
        self.assertIsNone(contact.email)
        self.assertEqual(str(contact), 'remover')
        self.assertFalse(contact.attributes.get('auth_user_has_email'))

    def test_contact_uses_username_when_names_missing(self):
        user = self.User.objects.create_user(username='mystery')
        contact = Contact.objects.get(user=user)
        self.assertEqual(contact.first_name, 'mystery')
        self.assertEqual(contact.last_name, '')
        self.assertEqual(str(contact), 'mystery')
        self.assertEqual(contact.attributes.get('auth_user_username'), 'mystery')
        self.assertFalse(contact.attributes.get('auth_user_has_email'))

    def test_superuser_considered_verified(self):
        user = self.User.objects.create_superuser(
            username='boss',
            email='boss@example.com',
            password='pass123',
        )
        contact = Contact.objects.get(user=user)
        self.assertTrue(contact.attributes.get('auth_user_email_verified'))
