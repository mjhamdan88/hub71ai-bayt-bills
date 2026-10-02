from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from unicom.models import Account, AccountChat, Channel, Chat, Member
from unicrm.services.red_alerts import send_red_alert


class SendRedAlertTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            username="staffer",
            password="pass1234",
            email="staffer@example.com",
            is_staff=True,
        )
        self.member = Member.objects.create(name="Staff Member", user=self.staff_user)
        self.email_channel = Channel.objects.create(
            name="Alert Email",
            platform="Email",
            config=self._email_channel_config(),
            active=True,
        )
        self.telegram_channel = Channel.objects.create(
            name="Alert Bot",
            platform="Telegram",
            config={"TELEGRAM_API_TOKEN": "token"},
            active=True,
        )

    def _email_channel_config(self):
        return {
            "EMAIL_ADDRESS": "alerts@example.com",
            "EMAIL_PASSWORD": "secret",
            "SMTP": {"host": "smtp.example.com", "port": 587, "use_ssl": False},
            "IMAP": {"host": "imap.example.com", "port": 993, "use_ssl": True},
        }

    def test_sends_to_email_and_telegram_accounts(self):
        email_account = Account.objects.create(
            id="staffer@example.com",
            name="Staff Email",
            platform="Email",
            channel=self.email_channel,
            member=self.member,
        )
        telegram_account = Account.objects.create(
            id="telegram-account",
            name="Staff Telegram",
            platform="Telegram",
            channel=self.telegram_channel,
            member=self.member,
        )
        chat = Chat.objects.create(
            id="chat-1",
            channel=self.telegram_channel,
            platform="Telegram",
            is_private=True,
            name="Staff DM",
        )
        AccountChat.objects.create(account=telegram_account, chat=chat)

        with mock.patch(
            "unicrm.services.red_alerts.unicom_send_message"
        ) as send_message:
            send_message.side_effect = [
                SimpleNamespace(id="email-msg"),
                SimpleNamespace(id="telegram-msg"),
            ]
            deliveries = send_red_alert(
                subject="Disk almost full",
                body="Root filesystem usage is above 95%",
                initiated_by=self.staff_user,
            )

        self.assertEqual(len(deliveries), 2)
        statuses = {delivery.platform: delivery.status for delivery in deliveries}
        self.assertEqual(statuses, {"Email": "sent", "Telegram": "sent"})

        # Ensure email payload contains correct metadata
        email_call = next(
            call for call in send_message.call_args_list if call.args[0] == self.email_channel
        )
        self.assertEqual(email_call.args[1]["to"], [email_account.id])
        self.assertEqual(email_call.args[1]["subject"], "Disk almost full")
        self.assertIn("Root filesystem", email_call.args[1]["text"])
        self.assertIs(email_call.args[2], self.staff_user)

        telegram_call = next(
            call for call in send_message.call_args_list if call.args[0] == self.telegram_channel
        )
        self.assertEqual(telegram_call.args[1]["chat_id"], chat.id)
        self.assertIn("Disk almost full", telegram_call.args[1]["text"])
        self.assertIn("Root filesystem", telegram_call.args[1]["text"])

    def test_skips_telegram_account_without_chat(self):
        Account.objects.create(
            id="telegram-account",
            name="Staff Telegram",
            platform="Telegram",
            channel=self.telegram_channel,
            member=self.member,
        )

        with mock.patch(
            "unicrm.services.red_alerts.unicom_send_message"
        ) as send_message:
            deliveries = send_red_alert(
                subject="Process stalled",
                body="Daemon xyz has not reported in 10 minutes",
                initiated_by=self.staff_user,
            )

        send_message.assert_not_called()
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].platform, "Telegram")
        self.assertEqual(deliveries[0].status, "skipped")
        self.assertIn("No chat", deliveries[0].error or "")

