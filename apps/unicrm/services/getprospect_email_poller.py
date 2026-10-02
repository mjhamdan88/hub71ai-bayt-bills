import logging
import random
import threading
import time
from typing import Optional

from django.conf import settings
from django.db import connections
from django.utils import timezone
import requests
from django.db import models
from django.db.models import Q

from unicrm.models import Contact

logger = logging.getLogger(__name__)


class GetProspectEmailPoller:
    """
    Background poller for recently requested GetProspect emails.
    - Runs only in webserver contexts (gated in apps.py).
    - Every minute: find contacts with pending requests, no email, requested 5s–5m ago.
    - Make a single search call (requestType=included) with contact.name filters for those pending leads.
    - Update emails/status when found; mark not_found after ~3 minutes without email.
    """

    _instance: Optional["GetProspectEmailPoller"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "GetProspectEmailPoller":
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._thread = None
                    cls._instance._stop_event = None
                    cls._instance._interval = 60
        return cls._instance

    def start(self, interval: int = 60) -> None:
        if interval <= 0:
            interval = 60
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._interval = interval
            self._stop_event = threading.Event()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            logger.info("GetProspect email poller started (interval=%s)", self._interval)

    def stop(self) -> None:
        with self._lock:
            if self._stop_event:
                self._stop_event.set()
            if self._thread:
                self._thread.join(timeout=1.0)
            self._thread = None
            self._stop_event = None
            logger.info("GetProspect email poller stopped")

    def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception:  # pragma: no cover
                logger.exception("GetProspect email poller error")
            finally:
                connections.close_all()
            self._stop_event.wait(self._interval)

    def _tick(self) -> None:
        api_key = getattr(settings, "GETPROSPECT_API_KEY", None)
        if not api_key:
            return

        now = timezone.now()
        # Pending: requested, no email, not recently checked
        cooldown = timezone.timedelta(seconds=60)
        pending = (
            Contact.objects.filter(email__isnull=True, gp_requested_at__isnull=False)
            .exclude(gp_email_status="duplicate_email")
            .filter(Q(gp_email_checked_at__isnull=True) | Q(gp_email_checked_at__lt=now - cooldown))
            .order_by("-gp_requested_at")[:50]
        )
        if not pending:
            return

        # Build name filters; if missing names, fall back to company name
        name_filters = []
        for c in pending:
            name = f"{(c.first_name or '').strip()} {(c.last_name or '').strip()}".strip()
            if name:
                name_filters.append(name)
            elif c.company and c.company.name:
                name_filters.append(c.company.name)
        if not name_filters:
            return
        # avoid repeating identical name filters when multiple contacts share the same name
        seen_names: set[str] = set()
        unique_filters: list[str] = []
        for value in name_filters:
            if value not in seen_names:
                seen_names.add(value)
                unique_filters.append(value)
        name_filters = unique_filters

        search_filters = {
            "filters": [
                {"property": "email", "included": {"operator": "EMAIL_STATUS", "value": ["all"]}},
                {
                    "property": "contact.name",
                    "included": {"operator": "CONTAINS_NAME", "value": name_filters},
                    "excluded": {"value": []},
                    "checkboxes": [],
                },
            ],
            "requestType": "included",
        }

        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json;charset=UTF-8",
            "apiKey": api_key,
        }

        try:
            resp = requests.post(
                "https://api.getprospect.com/api/v1/insights/search/contacts",
                headers=headers,
                json=search_filters,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("GetProspect poll request failed: %s", exc)
            return

        items = data.get("data") or []
        by_id = {c.insight_id: c for c in pending if c.insight_id}

        for item in items:
            iid = item.get("id") or item.get("insightId")
            if not iid or iid not in by_id:
                continue
            c = by_id[iid]
            email_obj = None
            for comp in item.get("companies") or []:
                if isinstance(comp, dict) and isinstance(comp.get("email"), dict):
                    email_obj = comp["email"]
                    break
            email_val = email_obj.get("value") if email_obj else None
            if email_val:
                # Skip saving if another contact already has this email; mark as duplicate for follow-up.
                duplicate = (
                    Contact.objects.filter(email=email_val)
                    .exclude(pk=c.pk)
                    .only("id")
                    .first()
                )
                if duplicate:
                    # logger.warning(
                    #     "GetProspect poller found duplicate email %s for contacts %s and %s",
                    #     email_val,
                    #     c.pk,
                    #     duplicate.pk,
                    # )
                    c.gp_email_status = "duplicate_email"
                    c.gp_email_checked_at = timezone.now()
                    c.save(update_fields=["gp_email_status", "gp_email_checked_at"])
                    continue

                normalized_email = email_val.strip()
                c.email = normalized_email
                attrs = c.attributes or {}
                gp_attrs = attrs.get("getprospect") or {}
                prev_verified_email = (
                    (gp_attrs.get("email_verification") or {}).get("email") or ""
                ).strip().lower()
                should_verify = normalized_email.lower() != prev_verified_email
                verified = False
                if should_verify:
                    try:
                        result = c.refresh_getprospect_verification(api_key=api_key)
                        verified = bool(result.get("success"))
                    except Exception:
                        logger.exception("Failed to refresh GetProspect verification for contact %s", c.pk)
                        verified = False
                c.save(update_fields=["email"])
                if verified:
                    continue
                c.gp_email_status = email_obj.get("status") or "valid"
                c.gp_email_checked_at = timezone.now()
                c.save(update_fields=["gp_email_status", "gp_email_checked_at"])
            else:
                # If older than 3 minutes since request and still no email, mark not_found
                if c.gp_requested_at and (timezone.now() - c.gp_requested_at).total_seconds() > 180:
                    c.gp_email_status = "not_found"
                    c.gp_email_checked_at = timezone.now()
                    c.save(update_fields=["gp_email_status", "gp_email_checked_at"])

        # polite delay between cycles inside the tick to avoid tight loops if interval is small
        time.sleep(random.uniform(0.5, 1.0))


getprospect_email_poller = GetProspectEmailPoller()
