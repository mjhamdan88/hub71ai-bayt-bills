from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from unicrm.services import check_disk_usage_and_alert


class DiskUsageMonitorTests(SimpleTestCase):
    def setUp(self):
        self.path = "/data"

    def test_below_threshold_does_not_send_alert(self):
        with mock.patch("unicrm.services.disk_usage_monitor.shutil.disk_usage") as disk_usage:
            disk_usage.return_value = (1000, 100, 900)
            with mock.patch("unicrm.services.disk_usage_monitor.send_red_alert") as send_alert:
                buffer = StringIO()
                with redirect_stdout(buffer):
                    result = check_disk_usage_and_alert(self.path, threshold_percent=50.0)

        self.assertFalse(result)
        send_alert.assert_not_called()
        self.assertIn("Disk usage for /data", buffer.getvalue())

    def test_above_threshold_sends_alert_and_returns_success_status(self):
        usages = (1000, 950, 50)
        fake_deliveries = [
            SimpleNamespace(status="sent"),
            SimpleNamespace(status="failed"),
        ]

        with mock.patch("unicrm.services.disk_usage_monitor.shutil.disk_usage", return_value=usages):
            with mock.patch(
                "unicrm.services.disk_usage_monitor._host_identity",
                return_value=("testhost", "testhost.example.com", "10.0.0.5"),
            ):
                with mock.patch(
                    "unicrm.services.disk_usage_monitor.send_red_alert", return_value=fake_deliveries
                ) as send_alert:
                    result = check_disk_usage_and_alert(self.path, threshold_percent=90.0)

        self.assertTrue(result)
        send_alert.assert_called_once()
        subject = send_alert.call_args.kwargs["subject"]
        body = send_alert.call_args.kwargs["body"]
        self.assertIn("Disk usage alert", subject)
        self.assertIn("testhost", subject)
        self.assertIn("Host: testhost", body)
        self.assertIn("FQDN: testhost.example.com", body)
        self.assertIn("IP: 10.0.0.5", body)
