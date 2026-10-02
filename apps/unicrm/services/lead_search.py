from __future__ import annotations

import time
import requests
from typing import Any, Dict, List, Optional, Tuple, Union

from django.conf import settings

from unicrm.templates.unicrm.unibot.lead_search_v2_tool import (
    API_ENDPOINT,
    _build_filters,
    _normalize_seniority,
    _fetch_existing_contacts,
    _persist_leads,
)


def run_lead_search(
    *,
    api_key: Optional[str] = None,
    company_name: Union[str, List[str]] = "",
    company_domain: Union[str, List[str]] = "",
    email_status: str = "all",
    contact_location: Union[str, List[str]] = "",
    company_locations: Optional[List[str]] = None,
    position: str = "",
    seniority: Union[str, List[str]] = "",
    industries: Optional[List[str]] = None,
    company_keywords: Optional[List[str]] = None,
    contact_keywords: Optional[List[str]] = None,
    contact_names: Optional[List[str]] = None,
    technologies: Optional[List[str]] = None,
    departments: Optional[List[str]] = None,
    company_types: Optional[List[str]] = None,
    company_size_ranges: Optional[List[str]] = None,
    company_size_min: Optional[int] = None,
    company_size_max: Optional[int] = None,
    founded_from: Optional[int] = None,
    founded_to: Optional[int] = None,
    page_size: int = 20,
    page_number: int = 1,
    request_type: str = "excluded",
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Unified GetProspect lead search runner.
    - Uses the env-configured GETPROSPECT_API_KEY unless explicitly provided.
    - Reuses the bot tool's filter builder and persistence helpers.
    Returns (result_dict, error_message_or_None).
    """
    REQUEST_TIMEOUT = 30

    def _normalize_scalar_or_list(value: Union[str, List[str]]) -> Union[str, List[str]]:
        return value.strip() if isinstance(value, str) else value

    key = api_key or getattr(settings, "GETPROSPECT_API_KEY", None)
    if not key:
        return {}, "GETPROSPECT_API_KEY is not configured."

    page_size = min(max(page_size, 1), 50)
    page_number = max(page_number, 1)

    normalized_seniority = _normalize_seniority(seniority or "")
    filters = _build_filters(
        _normalize_scalar_or_list(company_name),
        _normalize_scalar_or_list(company_domain),
        email_status.strip().lower(),
        _normalize_scalar_or_list(contact_location),
        company_locations or [],
        _normalize_scalar_or_list(position),
        normalized_seniority or "",
        industries or [],
        company_keywords or [],
        contact_keywords or [],
        contact_names or [],
        technologies or [],
        departments or [],
        company_types or [],
        company_size_ranges or [],
        company_size_min,
        company_size_max,
        founded_from,
        founded_to,
    )
    # Adjust domain filter to match observed GetProspect operators (EQ/NOT_EQ)
    for f in filters:
        if f.get("property") == "company.domain":
            if f.get("included"):
                f["included"]["operator"] = "EQ"
            if f.get("excluded"):
                f["excluded"]["operator"] = "NOT_EQ"
    if request_type not in {"all", "included", "excluded"}:
        request_type = "excluded"
    payload = {"filters": filters, "requestType": request_type}
    params = {"pageSize": page_size, "pageNumber": page_number}

    resp_json, error = _call_getprospect(key, payload, params, timeout=REQUEST_TIMEOUT)
    if error:
        return {}, error

    extracted = _extract(resp_json)
    if extracted["leads"]:
        return _finalize_result(extracted, filters), None

    # Fallback: drop position/seniority if they were used
    has_position = any(f.get("property") == "company.position" for f in filters)
    has_seniority = any(f.get("property") == "company.seniority" for f in filters)
    if not (has_position or has_seniority):
        extracted["note"] = "No results for given filters."
        return _finalize_result(extracted, filters), None

    simplified_filters = [f for f in filters if f.get("property") not in ("company.position", "company.seniority")]
    fallback_payload = {"filters": simplified_filters, "requestType": payload.get("requestType", "all")}
    fb_json, fb_error = _call_getprospect(key, fallback_payload, params)
    if fb_error:
        return {}, fb_error
    fb_extracted = _extract(fb_json)
    fb_extracted["note"] = "Simplified filters used after empty result." if fb_extracted["leads"] else "No results for given filters."
    return _finalize_result(fb_extracted, simplified_filters), None


def _call_getprospect(
    api_key: str,
    payload: Dict[str, Any],
    params: Dict[str, Any],
    timeout: int = 15,
) -> Tuple[Dict[str, Any], Optional[str]]:
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "apiKey": api_key,
    }
    started = time.perf_counter()
    try:
        resp = requests.post(
            API_ENDPOINT,
            headers=headers,
            params=params,
            json=payload,
            timeout=timeout,
        )
    except requests.Timeout:
        elapsed = time.perf_counter() - started
        return {}, f"GetProspect request timed out after {elapsed:.1f}s (limit {timeout}s). Try reducing filters or increasing page size later."
    except requests.RequestException as exc:
        elapsed = time.perf_counter() - started
        return {}, f"GetProspect request failed after {elapsed:.1f}s: {exc.__class__.__name__}: {exc}"

    if not resp.ok:
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text[:300]
        return {}, f"GetProspect returned HTTP {resp.status_code}: {detail}"

    try:
        return resp.json(), None
    except ValueError:
        return {}, "GetProspect returned a non-JSON response."


def _extract(resp_json: Dict[str, Any]) -> Dict[str, Any]:
    leads_list = []
    for item in resp_json.get("data", []) or []:
        if not isinstance(item, dict):
            continue
        companies = item.get("companies") or []
        first_company = companies[0].get("company") if companies and isinstance(companies[0], dict) else {}
        company_wrapper = companies[0] if companies and isinstance(companies[0], dict) else {}
        def _pick_company(field: str) -> Any:
            return (
                first_company.get(field)
                or company_wrapper.get(field)
                or (first_company.get("company", {}) if isinstance(first_company, dict) else {}).get(field)
            )
        position_val = companies[0].get("position") if companies and isinstance(companies[0], dict) else None
        leads_list.append(
            {
                "id": item.get("id"),
                "insight_id": item.get("id"),
                "first_name": item.get("firstName"),
                "last_name": item.get("lastName"),
                "full_name": " ".join(
                    [p for p in [item.get("firstName"), item.get("lastName")] if p]
                ).strip()
                or item.get("contactInfo"),
            "company_name": first_company.get("name"),
            "company_domain": first_company.get("domain"),
                "company_industry": _pick_company("industry"),
                "company_size": _pick_company("size"),
                "company_country": _pick_company("countryCode"),
                "company_hq": _pick_company("headquarters"),
                "position": position_val,
                "saved": bool(item.get("saved")),
                "linkedin_url": item.get("linkedinUrl"),
                "raw": item,
            }
    )
    meta_local = resp_json.get("meta") or {}
    return {"leads": leads_list, "meta": meta_local, "raw": resp_json}


def _finalize_result(extracted: Dict[str, Any], filters: List[Dict[str, Any]]) -> Dict[str, Any]:
    leads = extracted.get("leads", [])
    meta = extracted.get("meta") or {}
    note = extracted.get("note")

    crm_contacts = _fetch_existing_contacts([lead.get("insight_id") or lead.get("id") for lead in leads])
    persisted_count, persist_errors = _persist_leads(leads) if leads else (0, [])
    companies, formatted_leads = _format_results(leads, crm_contacts)

    return {
        "total": meta.get("totalItems") or len(leads) or 0,
        "page": meta.get("page"),
        "page_size": meta.get("pageSize"),
        "leads": formatted_leads,
        "companies": companies,
        "persisted": persisted_count,
        "persist_errors": persist_errors,
        "raw_meta": meta,
        "note": note,
        "filters": filters,
    }


def _format_results(
    leads: List[Dict[str, Any]],
    crm_contacts: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    companies: Dict[str, Dict[str, Any]] = {}
    for lead in leads:
        key = (lead.get("company_domain") or lead.get("company_name") or "").lower()
        comp_entry = companies.setdefault(
            key,
            {
                "company": {
                    "name": lead.get("company_name"),
                    "domain": lead.get("company_domain"),
                    "industry": lead.get("company_industry"),
                    "size": lead.get("company_size"),
                    "country": lead.get("company_country"),
                    "headquarters": lead.get("company_hq"),
                },
                "contacts": [],
            },
        )
        insight_key = str(lead.get("insight_id") or "")
        crm_contact = crm_contacts.get(insight_key)
        contact_entry = {
            "insight_id": lead.get("insight_id"),
            "name": lead.get("full_name"),
            "position": lead.get("position"),
            "saved": lead.get("saved"),
            "linkedin": lead.get("linkedin_url"),
        }
        if crm_contact:
            contact_entry["crm_contact"] = crm_contact
        comp_entry["contacts"].append(contact_entry)

    formatted_leads = []
    for lead in leads:
        insight_key = str(lead.get("insight_id") or "")
        crm_contact = crm_contacts.get(insight_key)
        lead_payload = {
            "insight_id": lead.get("insight_id"),
            "name": lead.get("full_name"),
            "company": lead.get("company_name"),
            "domain": lead.get("company_domain"),
            "company_industry": lead.get("company_industry"),
            "company_size": lead.get("company_size"),
            "company_location": lead.get("company_hq") or lead.get("company_country"),
            "position": lead.get("position"),
            "saved": lead.get("saved"),
            "linkedin": lead.get("linkedin_url"),
        }
        if crm_contact:
            lead_payload["crm_contact"] = crm_contact
        formatted_leads.append(lead_payload)

    return list(companies.values()), formatted_leads
