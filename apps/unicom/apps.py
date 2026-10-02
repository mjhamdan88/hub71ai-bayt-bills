from django.apps import AppConfig
import sys


class UnicomConfig(AppConfig):
    name = 'unicom'

    def ready(self):
        if len(sys.argv) > 1 and sys.argv[1] == "runserver":
            from unicom.services.email.IMAP_thread_manager import imap_manager
            imap_manager.start_all()
        import unicom.signals
