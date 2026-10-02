from unicom.services.email.send_email_message import email_tracking_enabled
from django.test import SimpleTestCase


class EmailTrackingChannelConfigTests(SimpleTestCase):
    def test_sender_honors_channel_tracking_switch(self):
        self.assertTrue(email_tracking_enabled({}))
        self.assertTrue(email_tracking_enabled({"EMAIL_TRACKING_ENABLED": True}))
        self.assertFalse(email_tracking_enabled({"EMAIL_TRACKING_ENABLED": False}))
