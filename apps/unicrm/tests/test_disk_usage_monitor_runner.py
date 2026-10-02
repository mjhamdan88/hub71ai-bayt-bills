from unittest import mock

from django.test import SimpleTestCase

from unicrm.services.disk_usage_monitor_runner import disk_usage_monitor_runner


class DiskUsageMonitorRunnerTests(SimpleTestCase):
    def setUp(self):
        self.runner = disk_usage_monitor_runner
        self.runner._path = "/data"
        self.runner._threshold = 75.0
        self.runner._initiated_by = None

    def test_perform_check_returns_result(self):
        with mock.patch(
            "unicrm.services.disk_usage_monitor_runner.check_disk_usage_and_alert",
            return_value=True,
        ) as check, mock.patch(
            "unicrm.services.disk_usage_monitor_runner.connections"
        ) as connections:
            result = self.runner._perform_check()

        self.assertTrue(result)
        check.assert_called_once_with(
            path="/data",
            threshold_percent=75.0,
            initiated_by=None,
        )
        connections.close_all.assert_called_once()

    def test_perform_check_handles_exception_and_returns_false(self):
        with mock.patch(
            "unicrm.services.disk_usage_monitor_runner.check_disk_usage_and_alert",
            side_effect=RuntimeError("boom"),
        ), mock.patch("unicrm.services.disk_usage_monitor_runner.connections") as connections:
            result = self.runner._perform_check()

        self.assertFalse(result)
        connections.close_all.assert_called_once()
