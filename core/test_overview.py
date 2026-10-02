from django.contrib.auth.models import User
from django.test import TestCase
from .models import Budget
from .views import seed


class OverviewRefreshTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='overview-refresh')
        seed(self.user)
        self.client.force_login(self.user)

    def test_fragment_reflects_current_budget_without_chat(self):
        budget = Budget.objects.get(owner=self.user, category='Gas')
        budget.limit = 1234.50
        budget.save()
        response = self.client.get('/?fragment=overview')
        self.assertContains(response, '1,234.50')
        self.assertContains(response, 'value="1234.50"')
        self.assertContains(response, 'data-live="summary"')
        self.assertNotContains(response, 'chat-mount')
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')

    def test_fragment_requires_login_and_scopes_data(self):
        other = User.objects.create_user(username='other-overview')
        seed(other)
        Budget.objects.filter(owner=other).update(limit=987654.32)
        self.assertNotContains(self.client.get('/?fragment=overview'), '987,654.32')
        self.client.logout()
        self.assertEqual(self.client.get('/?fragment=overview').status_code, 302)
