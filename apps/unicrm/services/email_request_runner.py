import logging
import random
import threading
import time
from typing import Optional

from django.db import connections
from unicrm.models import Contact

logger = logging.getLogger(__name__)


class EmailRequestRunner:
    """Background runner for GetProspect email requests."""
    
    _instance: Optional["EmailRequestRunner"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "EmailRequestRunner":
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._thread = None
                    cls._instance._stop_event = None
                    cls._instance._interval = 5
        return cls._instance

    def start(self, interval: int = 5) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._interval = interval
            self._stop_event = threading.Event()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._process_pending_requests()
            except Exception as e:
                logger.error(f"EmailRequestRunner error: {e}")
            self._stop_event.wait(self._interval)

    def _process_pending_requests(self) -> None:
        from django.db import transaction
        
        with transaction.atomic():
            # Find contacts that need email requests (flagged by button click)
            contacts = list(Contact.objects.select_for_update(skip_locked=True).filter(
                insight_id__isnull=False,
                email__isnull=True,
                attributes__email_request_queued=True
            )[:10])  # Process 10 at a time
        
        if not contacts:
            return
            
        # Get API key from settings
        from django.conf import settings
        api_key = getattr(settings, "GETPROSPECT_API_KEY", None)
        
        if not api_key:
            return
            
        for contact in contacts:
            try:
                contact.request_getprospect_email(api_key=api_key)
                # Clear the queue flag
                attrs = contact.attributes or {}
                attrs.pop('email_request_queued', None)
                contact.attributes = attrs
                contact.save(update_fields=['attributes'])
                time.sleep(random.uniform(0.8, 1.2))  # Rate limiting
            except Exception as e:
                logger.error(f"Failed to request email for {contact.insight_id}: {e}")
        
        # Close DB connections to prevent leaks
        connections.close_all()


email_request_runner = EmailRequestRunner()
