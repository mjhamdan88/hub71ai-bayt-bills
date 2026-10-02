import json
import re
from typing import Any, Dict, List, Sequence, Set, Tuple, Union, Optional
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.db import transaction

from unicrm.models import Company, Contact


def _normalize_domain(value: Optional[str]) -> str:
    if not value:
        return ""
    trimmed = value.strip().lower()
    trimmed = re.sub(r"^https?://", "", trimmed)
    trimmed = trimmed.split("/", 1)[0]
    if trimmed.startswith("www."):
        trimmed = trimmed[4:]
    return trimmed


def _load_staff_payload(payload: Union[str, Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, Sequence):
        raise ValueError("Staff payload must be a list of objects.")
    staff: List[Dict[str, Any]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        staff.append(entry)
    return staff


def _load_company_attributes(payload: Union[str, Dict[str, Any], None]) -> Dict[str, Any]:
    if payload in (None, ""):
        return {}
    if isinstance(payload, str):
        payload = payload.strip()
        if not payload:
            return {}
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("Company attributes must be a JSON object.")
    return payload


def _reacher_endpoint() -> str:
    base_url = (
        getattr(settings, "REACHER_HOSTNAME", None)
        or getattr(settings, "REACHER_HOST", None)
        or getattr(settings, "REACHER_BASE_URL", None)
    )
    if not base_url:
        raise RuntimeError("Reacher API host is not configured.")
    base_url = base_url.strip()
    if not base_url.startswith(("http://", "https://")):
        base_url = f"http://{base_url}"
    return urljoin(f"{base_url.rstrip('/')}/", "v0/check_email")


_STRICTNESS_TO_ALLOWED_STATUS: Dict[str, Set[str]] = {
    "strict": {"safe"},
    "moderate": {"safe", "risky"},
    "lenient": {"safe", "risky", "unknown"},
}


def _allowed_reacher_statuses() -> Tuple[Set[str], str]:
    strictness = (getattr(settings, "REACHER_STRICTNESS", "") or "moderate").strip().lower()
    allowed = _STRICTNESS_TO_ALLOWED_STATUS.get(strictness)
    if not allowed:
        strictness = "moderate"
        allowed = _STRICTNESS_TO_ALLOWED_STATUS[strictness]
    return allowed, strictness


def _validate_emails(
    emails: List[str], include_raw_payload: bool = False
) -> tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    endpoint = _reacher_endpoint()
    results: Dict[str, Dict[str, Any]] = {}
    for email in emails:
        try:
            response = requests.post(endpoint, json={"to_email": email}, timeout=120)
        except requests.Timeout:
            return {}, "Timed out while contacting Reacher (emails not validated)."
        except requests.RequestException as exc:
            return {}, f"Unable to reach Reacher for validation: {exc}"

        try:
            response.raise_for_status()
        except requests.HTTPError:
            status_code = response.status_code
            base_msg = "Reacher rejected the validation request"
            if status_code == 429:
                base_msg = "Reacher throttled validation (HTTP 429). Please retry shortly."
            elif status_code >= 500:
                base_msg = f"Reacher service error (HTTP {status_code})."
            else:
                base_msg = f"Reacher returned HTTP {status_code}."
            detail = ""
            try:
                detail_json = response.json()
                detail = f" Details: {detail_json.get('error') or detail_json.get('message') or ''}"
            except ValueError:
                if response.text:
                    detail = f" Details: {response.text[:200]}"
            return {}, base_msg + detail

        try:
            data = response.json()
        except ValueError:
            return {}, "Reacher returned a non-JSON response."

        status = str(data.get("is_reachable", "") or "").lower() or "unknown"
        reason = data.get("result") or data.get("reason") or data.get("error")
        entry: Dict[str, Any] = {"status": status}
        if reason:
            entry["reason"] = str(reason)
        if include_raw_payload:
            entry["payload"] = data
        results[email] = entry

    return results, None


def add_company_with_staff(
    company_name: str,
    staff: Union[str, Sequence[Dict[str, Any]]],
    company_domain: str = "",
    company_website: str = "",
    company_industry: str = "",
    company_attributes: Union[str, Dict[str, Any], None] = None,
    notes: str = "",
    include_reacher_payload: bool = False,
) -> str:
    if not company_name or not company_name.strip():
        return "Company name is required."

    try:
        staff_payload = _load_staff_payload(staff)
    except json.JSONDecodeError as exc:
        return f"Staff payload must be valid JSON: {exc}"
    except ValueError as exc:
        return str(exc)

    try:
        company_attribute_values = _load_company_attributes(company_attributes)
    except json.JSONDecodeError as exc:
        return f"company_attributes must be valid JSON: {exc}"
    except ValueError as exc:
        return str(exc)

    if not staff_payload:
        return "At least one staff member with a valid email address is required."

    normalized_domain = _normalize_domain(company_domain)
    if not normalized_domain:
        return "company_domain is required so duplicates can be prevented."
    if Company.objects.filter(name__iexact=company_name.strip()).exists():
        return f"A company named '{company_name.strip()}' already exists."
    if Company.objects.filter(domain__iexact=normalized_domain).exists():
        return f"A company with domain '{normalized_domain}' already exists."

    emails: List[str] = []
    seen_emails: Set[str] = set()
    for member in staff_payload:
        email = (member.get("email") or "").strip()
        if not email:
            return "Each staff record must include an email address."
        lowered = email.lower()
        if lowered in seen_emails:
            return f"Duplicate email '{email}' detected in the payload."
        if Contact.objects.filter(email__iexact=email).exists():
            return f"A contact with email '{email}' already exists."
        seen_emails.add(lowered)
        emails.append(email)

    validation_results, validation_error = _validate_emails(
        emails, include_raw_payload=include_reacher_payload
    )
    if validation_error:
        payload_hint = ""
        if include_reacher_payload and validation_results:
            payload_hint = f" Raw payload: {json.dumps(validation_results, separators=(',', ':'))}"
        return (
            "Aborting company and staff creation because email validation was unavailable: "
            + validation_error
            + " Emails were not checked for deliverability."
            + payload_hint
        )

    allowed_statuses, strictness = _allowed_reacher_statuses()

    invalid = [
        f"{email} ({details.get('status', 'unknown')})"
        + (f": {details.get('reason')}" if details.get('reason') else "")
        for email, details in validation_results.items()
        if (details.get("status") or "unknown") not in allowed_statuses
    ]
    if invalid:
        payload_hint = ""
        if include_reacher_payload:
            payload_hint = (
                " Raw payload: "
                + json.dumps(validation_results, separators=(",", ":"))
            )
        return (
            "Aborting company and staff creation because Reacher reported emails outside the allowed "
            f"statuses for strictness '{strictness}' ({', '.join(sorted(allowed_statuses))} permitted): "
            + ", ".join(invalid)
            + payload_hint
        )

    created_contacts: list[str] = []
    with transaction.atomic():
        company = Company.objects.create(
            name=company_name.strip(),
            domain=normalized_domain,
            website=(company_website or "").strip(),
            industry=(company_industry or "").strip(),
            notes=(notes or "").strip(),
            attributes=company_attribute_values,
        )
        for member in staff_payload:
            attributes = member.get("attributes")
            if not isinstance(attributes, dict):
                attributes = {}
            contact = Contact.objects.create(
                first_name=(member.get("first_name") or "").strip(),
                last_name=(member.get("last_name") or "").strip(),
                email=(member.get("email") or "").strip(),
                job_title=(member.get("job_title") or "").strip(),
                phone_number=(member.get("phone_number") or "").strip(),
                company=company,
                attributes=attributes,
            )
            created_contacts.append(contact.email or str(contact.pk))

    return (
        f"Created company '{company.name}' with {len(created_contacts)} contacts: "
        + ", ".join(created_contacts)
    )


tool_definition = {
    "name": "add_company_with_staff",
    "description": "Atomically creates a new company and its staff contacts after verifying they are new and validated via Reacher.",
    "parameters": {
        "company_name": {
            "type": "string",
            "description": "Name of the company to create.",
        },
        "company_domain": {
            "type": "string",
            "description": "Primary domain for the company (required).",
        },
        "company_website": {
            "type": "string",
            "description": "Company website URL (optional).",
            "default": "",
        },
        "company_industry": {
            "type": "string",
            "description": "Industry or vertical focus for the company (optional).",
            "default": "",
        },
        "company_attributes": {
            "type": "string",
            "description": "JSON object containing custom fields to store on the company record (optional). Example: {\"employee_count\": 42}.",
            "default": "{}",
        },
        "notes": {
            "type": "string",
            "description": "Internal notes to store on the company record (optional).",
            "default": "",
        },
        "staff": {
            "type": "string",
            "description": (
                "JSON array describing staff entries; each object may include first_name, last_name, email, job_title, "
                "phone_number, and an attributes JSON object for per-contact custom data."
            ),
        },
        "include_reacher_payload": {
            "type": "boolean",
            "description": (
                "When true, include the full per-email Reacher payload in the response for debugging."
            ),
            "default": False,
        },
    },
    "run": add_company_with_staff,
}
