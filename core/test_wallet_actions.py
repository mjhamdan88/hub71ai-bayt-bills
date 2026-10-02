from django.test import TestCase, Client
from django.contrib.auth.models import User
from .views import seed
from .wallet import seed_wallet, prepare
from .models import Budget, PaymentMethod, Bill, Payment, ActionRequest

class WalletActionsTest(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='wallet_test')
        self.other=User.objects.create_user(username='other_test')
        seed(self.user);seed_wallet(self.user)
        self.client.force_login(self.user)
    def test_confirmation_and_idempotence(self):
        result=prepare(self.user,{'kind':'pay_bill','category':'Gas','amount':None})
        action=ActionRequest.objects.get(pk=result['action_id'])
        bill=Bill.objects.get(pk=action.arguments['bill_id'])
        self.assertFalse(bill.paid)
        url=result['review_url']
        self.client.get(url);bill.refresh_from_db();self.assertFalse(bill.paid)
        self.client.post(url,{'decision':'confirm'});self.client.post(url,{'decision':'confirm'})
        bill.refresh_from_db();self.assertTrue(bill.paid)
        self.assertEqual(Payment.objects.filter(bill=bill).count(),1)
        self.assertIsNotNone(Payment.objects.get(bill=bill).payment_method_id)
    def test_scope_cancel_and_removed_card(self):
        result=prepare(self.user,{'kind':'adjust_budget','category':'Gas','amount':120})
        other=Client();other.force_login(self.other)
        self.assertEqual(other.post(result['review_url'],{'decision':'confirm'}).status_code,404)
        self.client.post(result['review_url'],{'decision':'cancel'})
        self.assertEqual(Budget.objects.get(owner=self.user,category='Gas').limit,100)
        card=PaymentMethod.objects.filter(owner=self.user).first()
        self.assertEqual(other.post(f'/wallet/{card.pk}/remove/').status_code,404)
        self.client.post(f'/wallet/{card.pk}/remove/')
        self.assertFalse(Budget.objects.filter(owner=self.user,payment_method=card).exists())
        seed_wallet(self.user);card.refresh_from_db();self.assertFalse(card.active)
        with self.assertRaises(ValueError):prepare(self.user,{'kind':'pay_bill','category':'Gas','amount':None})
    def test_inline_review_and_cancel(self):
        from .models import Message, Conversation
        from .views import chat_message
        result=prepare(self.user,{'kind':'adjust_budget','category':'Gas','amount':120})
        conversation=Conversation.objects.create(owner=self.user)
        review=Message.objects.create(owner=self.user,conversation=conversation,role='assistant',text=result['summary'],metadata={'action_id':result['action_id']})
        self.assertFalse(chat_message(review)['interactive_buttons'][0][0]['disabled'])
        response=self.client.post(result['review_url'],{'decision':'cancel'},HTTP_ACCEPT='application/json')
        self.assertEqual(response.json()['status'],'cancelled')
        self.assertTrue(response.json()['messages'][0]['interactive_buttons'][0][0]['disabled'])
        self.assertEqual(Budget.objects.get(owner=self.user,category='Gas').limit,100)
        self.assertEqual(self.client.post('/finance-chat/stream/',{'text':'Continue','chat_id':conversation.pk,'action_id':999999}).status_code,404)
    def test_inline_confirm_updates_budget_and_expires_stale_review(self):
        from .models import Message, Conversation
        result=prepare(self.user,{'kind':'adjust_budget','category':'Gas','amount':120})
        conversation=Conversation.objects.create(owner=self.user)
        Message.objects.create(owner=self.user,conversation=conversation,role='assistant',text=result['summary'],metadata={'action_id':result['action_id']})
        pending=self.client.post('/finance-chat/stream/',{'text':'Continue','chat_id':conversation.pk,'action_id':result['action_id']})
        self.assertEqual(pending.status_code,400)
        response=self.client.post(result['review_url'],{'decision':'confirm'},HTTP_ACCEPT='application/json')
        self.assertEqual(response.json()['status'],'completed')
        self.assertTrue(response.json()['messages'][0]['interactive_buttons'][0][0]['disabled'])
        self.assertEqual(Budget.objects.get(owner=self.user,category='Gas').limit,120)
        stale=prepare(self.user,{'kind':'adjust_budget','category':'Gas','amount':140})
        Budget.objects.filter(owner=self.user,category='Gas').update(limit=150)
        response=self.client.post(stale['review_url'],{'decision':'confirm'},HTTP_ACCEPT='application/json')
        self.assertEqual(response.json()['status'],'expired')
        self.assertEqual(Budget.objects.get(owner=self.user,category='Gas').limit,150)
