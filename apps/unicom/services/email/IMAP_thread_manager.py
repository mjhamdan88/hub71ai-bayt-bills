import time
import logging
from threading import Lock, Thread
from imapclient import IMAPClient, SEEN
from django.db import transaction, connections

from unicom.services.email.save_email_message import save_email_message
from django.db.utils import ProgrammingError, OperationalError
from django.apps import apps
import psycopg2.errors

logger = logging.getLogger(__name__)

class IMAPThreadManager:
    """
    Singleton manager to supervise IMAP listener threads for all Channels.
    """
    _instance = None
    lock = Lock()

    def __new__(cls):
        if not cls._instance:
            with cls.lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance.threads = {}
        return cls._instance

    def start_all(self):
        """Start listener threads for all active channels."""
        try:
            Channel = apps.get_model('unicom', 'Channel')
            for channel in Channel.objects.filter(active=True, platform='Email'):
                self.start(channel)
        except (psycopg2.errors.UndefinedTable, ProgrammingError, OperationalError):
            # Database not ready (e.g., during initial migrations)
            logger.info("IMAPThreadManager: Database not ready, skipping start_all.")

    def start(self, channel):
        """Start a thread for a channel if not already running."""
        if not channel.active or channel.platform != 'Email':
            return
        if channel.pk in self.threads and self.threads[channel.pk].is_alive():
            return
        thread = Thread(target=self._run_listener, args=(channel,), daemon=True)
        self.threads[channel.pk] = thread
        thread.start()
        logger.info(f"Started IMAP listener for Channel {channel.pk}")

    def stop(self, channel):
        """Stop listener by marking channel inactive."""
        # relies on thread to exit when channel.deactivated or config changed
        if channel.pk in self.threads:
            del self.threads[channel.pk]
            logger.info(f"Stopped IMAP listener for Channel {channel.pk}")

    def restart(self, channel):
        """Restart listener for updated channel."""
        self.stop(channel)
        self.start(channel)

    def _run_listener(self, channel):
        """Internal: calls channel.listen_to_IMAP until unregistered."""
        while channel.pk in self.threads:
            try:
                channel.listen_to_IMAP()
            except Exception as e:
                logger.exception(f"Listener for Channel {channel.pk} crashed: {e}")
                time.sleep(10)
            finally:
                # ensure no DB connections are leaked by this thread
                connections.close_all()

# module-level singleton
imap_manager = IMAPThreadManager()
