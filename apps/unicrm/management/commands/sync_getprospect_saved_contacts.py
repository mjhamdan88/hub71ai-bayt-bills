import json
from typing import Optional

import requests
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from unicrm.models import Contact, Company


API_ENDPOINT = "https://api.getprospect.com/api/v1/insights/search/contacts"


class Command(BaseCommand):
    help = "Sync saved GetProspect contacts (requestType=included) and update Contact emails by insight_id."

    def add_arguments(self, parser):
        parser.add_argument(
            "--api-key",
            dest="api_key",
            default=None,
            help="GetProspect API key (or set GETPROSPECT_API_KEY env var).",
        )
        parser.add_argument(
            "--page-size",
            dest="page_size",
            type=int,
            default=50,
            help="Page size for GetProspect search (default: 50, max: 100).",
        )
        parser.add_argument(
            "--max-pages",
            dest="max_pages",
            type=int,
            default=None,
            help="Optional cap on number of pages to process.",
        )

    def handle(self, *args, **options):
        api_key = options["api_key"] or None
        if not api_key:
            raise CommandError("API key is required. Pass --api-key or set GETPROSPECT_API_KEY.")

        page_size = max(1, min(options["page_size"], 100))
        max_pages = options["max_pages"]

        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json;charset=UTF-8",
            "apiKey": api_key,
        }
        payload = {
            "filters": [
                {"property": "email", "included": {"operator": "EMAIL_STATUS", "value": ["all"]}}
            ],
            "requestType": "included",
        }

        page = 1
        total_processed = 0
        total_emails_set = 0
        total_new_emails = 0
        errors = 0

        while True:
            params = {"pageSize": page_size, "pageNumber": page}
            try:
                resp = requests.post(API_ENDPOINT, headers=headers, params=params, json=payload, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                errors += 1
                self.stderr.write(f"[page {page}] request failed: {exc}")
                break

            items = data.get("data") or []
            if not items:
                break

            for item in items:
                try:
                    insight_id = item.get("id") or item.get("insightId")
                    if not insight_id:
                        continue
                    email_val, email_status, email_checked = self._extract_email(item)
                    first_name = item.get("firstName") or ""
                    last_name = item.get("lastName") or ""
                    companies = item.get("companies") or []
                    company_obj = self._resolve_company(companies)
                    job_title = None
                    if companies and isinstance(companies[0], dict):
                        job_title = companies[0].get("position") or ""

                    contact, created = Contact.objects.get_or_create(
                        insight_id=insight_id,
                        defaults={
                            "first_name": first_name,
                            "last_name": last_name,
                            "company": company_obj,
                            "job_title": job_title or "",
                        },
                    )

                    fields_to_update = []
                    if not contact.first_name and first_name:
                        contact.first_name = first_name
                        fields_to_update.append("first_name")
                    if not contact.last_name and last_name:
                        contact.last_name = last_name
                        fields_to_update.append("last_name")
                    if not contact.job_title and job_title:
                        contact.job_title = job_title
                        fields_to_update.append("job_title")
                    if not contact.company and company_obj:
                        contact.company = company_obj
                        fields_to_update.append("company")
                    if email_val:
                        total_emails_set += 1
                        if not contact.email:
                            contact.email = email_val
                            fields_to_update.append("email")
                            total_new_emails += 1
                    if email_status:
                        contact.gp_email_status = email_status
                        fields_to_update.append("gp_email_status")
                    if email_checked:
                        contact.gp_email_checked_at = timezone.now()
                        fields_to_update.append("gp_email_checked_at")
                    if fields_to_update:
                        contact.save(update_fields=fields_to_update)
                    total_processed += 1
                except Exception as exc:
                    errors += 1
                    self.stderr.write(f"[page {page}] failed to process contact: {exc}")

            meta = data.get("meta") or {}
            total_pages = meta.get("totalPages") or 0
            if max_pages and page >= max_pages:
                break
            if total_pages and page >= total_pages:
                break
            page += 1

        self.stdout.write(
            f"Done. Processed {total_processed} contacts, emails present in GP: {total_emails_set}, new emails saved: {total_new_emails}, errors: {errors}."
        )

    def _extract_email(self, item: dict) -> tuple[Optional[str], Optional[str], Optional[str]]:
        companies = item.get("companies") or []
        for comp in companies:
            if not isinstance(comp, dict):
                continue
            eobj = comp.get("email")
            if isinstance(eobj, dict):
                return (
                    eobj.get("value"),
                    eobj.get("status"),
                    eobj.get("lastCheckedAt"),
                )
        return None, None, None

    def _resolve_company(self, companies) -> Optional[Company]:
        if not companies:
            return None
        comp = companies[0]
        if not isinstance(comp, dict):
            return None
        cdata = comp.get("company") or {}
        name = cdata.get("name") or ""
        domain = (cdata.get("domain") or "").lower()
        if not name and not domain:
            return None
        company = None
        if domain:
            company = Company.objects.filter(domain__iexact=domain).first()
        if not company and name:
            company = Company.objects.filter(name__iexact=name).first()
        if not company:
            company = Company.objects.create(name=name or domain or "Unknown Company", domain=domain)
        # store raw company data for reference
        attrs = company.attributes or {}
        attrs.setdefault("getprospect", {})
        attrs["getprospect"]["raw"] = cdata
        company.attributes = attrs
        company.save(update_fields=["attributes"])
        return company
