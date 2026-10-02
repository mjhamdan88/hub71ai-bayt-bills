from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from .models import ActionRequest, Payment, PaymentMethod, Wallet
from .wallet import add


class PaymentMethodSaveTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='card_owner')
        Wallet.objects.create(owner=self.user)
        self.details = {'bank': 'My bank', 'cardholder': 'Alex Smith',
                        'network': 'Visa', 'last4': '9876', 'expiry': '2029-08'}

    def submit(self, details):
        request = RequestFactory().post('/wallet/add/', details)
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)
        return add(request)

    def test_saves_details_directly_without_action_or_payment(self):
        response = self.submit(self.details)
        self.assertEqual(response.status_code, 302)
        card = PaymentMethod.objects.get(owner=self.user)
        for field, value in self.details.items():
            self.assertEqual(getattr(card, field), value)
        self.assertFalse(ActionRequest.objects.exists())
        self.assertFalse(Payment.objects.exists())

    def test_invalid_details_preserve_input_without_saving(self):
        response = self.submit({**self.details, 'last4': '12345'})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Alex Smith', status_code=400)
        self.assertFalse(PaymentMethod.objects.exists())
