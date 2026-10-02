from __future__ import annotations

import logging
import threading
from typing import Optional

from django.db import connections

from unicrm.services.communication_dispatcher import process_scheduled_communications

logger = logging.getLogger(__name__)


class CommunicationSchedulerRunner:
    """Background runner that dispatches scheduled unicrm communications."""

    _instance: Optional['CommunicationSchedulerRunner'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'CommunicationSchedulerRunner':
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._thread = None
                    cls._instance._stop_event = None
                    cls._instance._interval = 10
        return cls._instance

    def start(self, interval: int = 10) -> None:
        if interval <= 0:
            interval = 10

        with self._lock:
            if self._thread and self._thread.is_alive():
                return

            self._interval = interval
            self._stop_event = threading.Event()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            logger.info('unicrm communication scheduler started (interval=%s)', self._interval)

    def stop(self) -> None:
        with self._lock:
            if self._stop_event:
                self._stop_event.set()
            if self._thread:
                self._thread.join(timeout=1.0)
            self._thread = None
            self._stop_event = None
            logger.info('unicrm communication scheduler stopped')

    def _run(self) -> None:
        assert self._stop_event is not None

        while not self._stop_event.is_set():
            try:
                summary = process_scheduled_communications()
                if summary.get('communications_processed'):
                    logger.info(
                        'unicrm scheduler processed %(communications_processed)s communications '
                        '(sent=%(messages_sent)s, failed=%(messages_failed)s)',
                        summary,
                    )
            except Exception:  # pragma: no cover
                logger.exception('unicrm scheduler encountered an error while dispatching communications')
            finally:
                connections.close_all()

            self._stop_event.wait(self._interval)


communication_scheduler_runner = CommunicationSchedulerRunner()
