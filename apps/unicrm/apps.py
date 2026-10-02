import os
import sys

from django.apps import AppConfig
from django.conf import settings


def _should_start_scheduler() -> bool:
    if not getattr(settings, 'UNICRM_AUTO_START_SCHEDULER', True):
        return False

    # Explicit opt-out
    if getattr(settings, 'UNICRM_DISABLE_GP_POLLER', False):
        return False

    # Explicit opt-in override (e.g., unusual server launchers)
    force_on = str(getattr(settings, 'UNICRM_FORCE_SCHEDULER', '')).lower()
    if force_on in {'1', 'true', 'yes', 'on'}:
        return True

    argv = sys.argv or []
    entrypoint = (argv[0] or '').lower()
    args = [a.lower() for a in argv[1:]]

    # Whitelist: only start under recognizable web servers
    server_names = ('daphne', 'gunicorn', 'uvicorn', 'hypercorn', 'asgiref', 'asgi', 'runserver')
    if any(name in entrypoint for name in server_names):
        return True
    if any(arg for arg in args if any(name in arg for name in server_names)):
        return True

    # If we got here, we did not positively identify a web server; do not start.
    return False


class UnicrmConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'unicrm'

    def ready(self):
        from . import signals  # noqa: F401
        # Register save_new_leads callback handlers (cross-platform buttons)
        from unicrm.services import save_new_leads_callbacks  # noqa: F401

        if _should_start_scheduler():
            from unicrm.services.communication_runner import communication_scheduler_runner
            from unicrm.services.getprospect_email_poller import getprospect_email_poller
            from unicrm.services.email_request_runner import email_request_runner

            interval = getattr(settings, 'UNICRM_SCHEDULER_INTERVAL', 10)
            communication_scheduler_runner.start(interval=interval)
            # Start the GetProspect email poller (separate interval)
            gp_interval = getattr(settings, 'UNICRM_GP_POLL_INTERVAL', 60)
            getprospect_email_poller.start(interval=gp_interval)
            # Start the email request runner
            email_request_runner.start(interval=5)
            if getattr(settings, 'UNICRM_DISK_MONITOR_ENABLED', False):
                from unicrm.services.disk_usage_monitor_runner import disk_usage_monitor_runner

                disk_monitor_cfg = {
                    'path': getattr(settings, 'UNICRM_DISK_MONITOR_PATH', '/'),
                    'threshold_percent': float(getattr(settings, 'UNICRM_DISK_MONITOR_THRESHOLD', 70.0)),
                    'interval_seconds': float(getattr(settings, 'UNICRM_DISK_MONITOR_INTERVAL_SECONDS', 60.0)),
                    'cooldown_seconds': float(getattr(settings, 'UNICRM_DISK_MONITOR_COOLDOWN_SECONDS', 3600.0)),
                }
                disk_usage_monitor_runner.start(**disk_monitor_cfg)
            print("unicrm scheduler/poller/email_requester started (web server context detected)")
