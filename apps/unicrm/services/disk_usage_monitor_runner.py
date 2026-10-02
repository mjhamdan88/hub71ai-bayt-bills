from __future__ import annotations

import logging
import threading
from typing import Optional

from django.db import connections

from unicrm.services.disk_usage_monitor import check_disk_usage_and_alert

logger = logging.getLogger(__name__)


class DiskUsageMonitorRunner:
    """Background loop that checks disk usage and dispatches alerts when needed."""

    _instance: Optional["DiskUsageMonitorRunner"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "DiskUsageMonitorRunner":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._thread = None
                    cls._instance._stop_event = None
                    cls._instance._path = "/"
                    cls._instance._threshold = 70.0
                    cls._instance._interval_seconds = 60.0
                    cls._instance._cooldown_seconds = 3600.0
                    cls._instance._initiated_by = None
        return cls._instance

    def start(
        self,
        *,
        path: str = "/",
        threshold_percent: float = 70.0,
        interval_seconds: float = 60.0,
        cooldown_seconds: float = 3600.0,
        initiated_by=None,
    ) -> None:
        interval_seconds = max(1.0, float(interval_seconds or 60.0))
        cooldown_seconds = max(interval_seconds, float(cooldown_seconds or 3600.0))

        with self._lock:
            if self._thread and self._thread.is_alive():
                return

            self._path = path
            self._threshold = threshold_percent
            self._interval_seconds = interval_seconds
            self._cooldown_seconds = cooldown_seconds
            self._initiated_by = initiated_by

            self._stop_event = threading.Event()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            logger.info(
                "Disk usage monitor started (path=%s, threshold=%.1f%%, interval=%ss, cooldown=%ss)",
                self._path,
                self._threshold,
                self._interval_seconds,
                self._cooldown_seconds,
            )

    def stop(self) -> None:
        with self._lock:
            if self._stop_event:
                self._stop_event.set()
            if self._thread:
                self._thread.join(timeout=1.0)
            self._thread = None
            self._stop_event = None
            logger.info("Disk usage monitor stopped")

    def _run(self) -> None:
        assert self._stop_event is not None

        while not self._stop_event.is_set():
            alert_sent = self._perform_check()
            wait_seconds = self._cooldown_seconds if alert_sent else self._interval_seconds
            self._stop_event.wait(wait_seconds)

    def _perform_check(self) -> bool:
        try:
            return check_disk_usage_and_alert(
                path=self._path,
                threshold_percent=self._threshold,
                initiated_by=self._initiated_by,
            )
        except Exception:
            logger.exception("Disk usage monitor failed while checking usage")
            return False
        finally:
            connections.close_all()


disk_usage_monitor_runner = DiskUsageMonitorRunner()
