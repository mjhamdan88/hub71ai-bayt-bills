import requests
from typing import Any, Dict, List, Optional, Tuple, Union
from django.db import transaction, IntegrityError
from django.db.models import Prefetch

from unibot.services.credentials import get_credentials
from unibot.services.tool_exceptions import ToolHandlerError, ToolHandlerWarning
from unicrm.models import Company, Contact, Subscription

API_ENDPOINT = "https://api.getprospect.com/api/v1/insights/search/contacts"
API_KEY_NAME = "GETPROSPECT_API_KEY"

# Allowed email status values seen in the web app
ALLOWED_EMAIL_STATUS = ["all", "valid"]
ALLOWED_SENIORITY = [
    "Owner",
    "Partner",
    "Chief Officer",
    "VP",
    "Director",
    "Senior",
    "Manager",
    "Intern",
    "Unpaid",
]

# Industry enums observed in GetProspect schemas (copied from prior tool)
ALLOWED_INDUSTRIES = [
    "Defense & Space", "Computer Networking", "Internet", "Computer Hardware", "Computer Software",
    "Law Practice", "Legal Services", "Management Consulting", "Biotechnology", "Medical Practice",
    "Hospital & Health Care", "Semiconductors", "Telecommunications", "Medical Devices", "Cosmetics",
    "Apparel & Fashion", "Sporting Goods", "Tobacco", "Supermarkets", "Food Production",
    "Consumer Electronics", "Consumer Goods", "Furniture", "Retail", "Entertainment",
    "Gambling & Casinos", "Pharmaceuticals", "Veterinary", "Restaurants", "Sports",
    "Food & Beverages", "Motion Pictures and Film", "Broadcast Media", "Museums and Institutions",
    "Fine Art", "Performing Arts", "Recreational Facilities and Services", "Banking", "Insurance",
    "Financial Services", "Real Estate", "Investment Banking", "Investment Management", "Accounting",
    "Construction", "Building Materials", "Architecture & Planning", "Leisure, Travel & Tourism",
    "Hospitality", "Automotive", "Chemicals", "Machinery", "Oil & Energy", "Shipbuilding",
    "Mining & Metals", "Utilities", "Textiles", "Paper & Forest Products", "Railroad Manufacture",
    "Farming", "Ranching", "Fishery", "Dairy", "Primary/Secondary Education", "Higher Education",
    "Education Management", "Research", "Military", "Legislative Office", "Judiciary",
    "Civil Engineering", "Aviation & Aerospace", "Law Enforcement", "Public Safety",
    "Executive Office", "Public Policy", "Marketing and Advertising", "Newspapers", "Publishing",
    "Printing", "Information Services", "Libraries", "Environmental Services",
    "Package/Freight Delivery", "Individual & Family Services", "Religious Institutions",
    "Civic & Social Organization", "Consumer Services", "Transportation/Trucking/Railroad",
    "Warehousing", "Airlines/Aviation", "Maritime", "Information Technology and Services",
    "Market Research", "Public Relations and Communications", "Design",
    "Nonprofit Organization Management", "Fund-Raising", "Writing and Editing", "Program Development",
    "Staffing and Recruiting", "Professional Training & Coaching", "International Affairs",
    "Government Administration", "Translation and Localization", "Computer Games", "Events Services",
    "Arts and Crafts", "Electrical/Electronic Manufacturing", "Nanotechnology", "Online Media",
    "Logistics and Supply Chain", "Music", "Plastics", "Computer & Network Security", "Wireless",
    "Alternative Dispute Resolution", "Security and Investigations", "Facilities Services",
    "Outsourcing/Offshoring", "Health, Wellness and Fitness", "Alternative Medicine", "Animation",
    "Media Production", "Commercial Real Estate", "Capital Markets", "Philanthropy", "Think Tanks",
    "E-Learning", "Wholesale", "Import and Export", "Mechanical or Industrial Engineering",
    "Photography", "Human Resources", "Business Supplies and Equipment", "Mental Health Care",
    "Graphic Design", "International Trade and Development", "Wine and Spirits",
    "Luxury Goods & Jewelry", "Renewables & Environment", "Political Organization",
    "Venture Capital & Private Equity", "Government Relations", "Industrial Automation",
    "Horticulture", "Mobile Games", "Packaging and Containers", "Glass, Ceramics & Concrete",
]


def _build_filters(
    company_name: Any,
    company_domain: Any,
    email_status: str,
    contact_location: Any = "",
    company_locations: Optional[List[str]] = None,
    position: Any = "",
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
) -> List[Dict[str, Any]]:
    filters: List[Dict[str, Any]] = []

    def _coerce_list(value: Any) -> List[str]:
        """
        Normalize strings/lists/tuples into a flat list of non-empty strings.
        Supports comma or newline separation for string inputs.
        """
        if value is None:
            return []
        if isinstance(value, str):
            items: List[str] = []
            for line in value.replace("\r", "").split("\n"):
                for part in line.split(","):
                    cleaned = part.strip()
                    if cleaned:
                        items.append(cleaned)
            return items
        if isinstance(value, (list, tuple, set)):
            items: List[str] = []
            for v in value:
                items.extend(_coerce_list(v))
            return items
        # Fallback to string conversion
        val = str(value).strip()
        return [val] if val else []

    def _split_includes_excludes(values: List[str]) -> tuple[List[str], List[str]]:
        includes: List[str] = []
        excludes: List[str] = []
        for v in values:
            if not v:
                continue
            v_clean = v.strip()
            lower = v_clean.lower()
            if lower.startswith("not "):
                excludes.append(v_clean[4:].strip())
            elif v_clean.startswith("!"):
                excludes.append(v_clean[1:].strip())
            else:
                includes.append(v_clean)
        return includes, excludes

    def _normalize_industry_values(values: List[str]) -> List[Dict[str, Any]]:
        """
        Map user-provided industry labels to GetProspect expected objects.
        - Supports NOT/! via caller's split.
        - Uses known enums; if not found, falls back to printedData/matching = user value.
        - Handles composite label "Transportation & Storage" explicitly with its sub-industries.
        """
        composite = {
            "transportation & storage": [
                "Airlines/Aviation",
                "Logistics and Supply Chain",
                "Package/Freight Delivery",
                "Transportation/Trucking/Railroad",
                "Warehousing",
            ]
        }

        def _match_one(value: str) -> Dict[str, Any]:
            norm = value.lower().replace("&", "and").strip()
            if norm in composite:
                return {"matching": composite[norm], "printedData": value}
            # exact/loose match against allowed enums
            for cand in ALLOWED_INDUSTRIES:
                cand_norm = cand.lower().replace("&", "and")
                if norm == cand_norm:
                    return {"matching": cand, "printedData": cand}
            for cand in ALLOWED_INDUSTRIES:
                cand_norm = cand.lower().replace("&", "and")
                if norm in cand_norm:
                    return {"matching": cand, "printedData": cand}
            return {"matching": value, "printedData": value}

        return [_match_one(v) for v in values if v]

    # Email status filter (safe default: all)
    status = email_status if email_status in ALLOWED_EMAIL_STATUS else "all"
    filters.append(
        {"property": "email", "included": {"operator": "EMAIL_STATUS", "value": [status]}}
    )

    # Company name (CONTAINS) with include/exclude support (use NOT or ! prefix to exclude)
    company_includes, company_excludes = _split_includes_excludes(
        _coerce_list(company_name)
    )
    if company_includes or company_excludes:
        filters.append(
            {
                "property": "company.name",
                "included": {"operator": "CONTAINS", "value": company_includes},
                "excluded": {"value": company_excludes, "operator": "NOT_CONTAINS"},
                "checkboxes": [],
            }
        )

    # Company domain can tighten the query if provided
    domain_includes, domain_excludes = _split_includes_excludes(
        _coerce_list(company_domain)
    )
    if domain_includes or domain_excludes:
        filters.append(
            {
                "property": "company.domain",
                "included": {"operator": "EQUALS", "value": domain_includes},
                "excluded": {"value": domain_excludes, "operator": "NOT_EQUALS"},
                "checkboxes": [],
            }
        )

    # Industries (EQ) accepts include/exclude; use NOT/! prefix to exclude
    industry_includes, industry_excludes = _split_includes_excludes(_coerce_list(industries))
    if industry_includes or industry_excludes:
        filters.append(
            {
                "property": "company.industry",
                "included": {"operator": "EQ", "value": _normalize_industry_values(industry_includes)},
                "excluded": {"value": _normalize_industry_values(industry_excludes), "operator": "NEQ"},
                "checkboxes": [],
            }
        )

    # Keywords include/exclude (company)
    kw_includes, kw_excludes = _split_includes_excludes(_coerce_list(company_keywords))
    if kw_includes or kw_excludes:
        filters.append(
            {
                "property": "company.keywords",
                "included": {"operator": "KEYWORDS_SEARCH", "value": kw_includes},
                "excluded": {"value": kw_excludes, "operator": "NOT_KEYWORDS_SEARCH"},
                "checkboxes": ["search_desc"],
            }
        )

    # Contact keywords (top-level keywords)
    ckw_includes, ckw_excludes = _split_includes_excludes(_coerce_list(contact_keywords))
    if ckw_includes or ckw_excludes:
        filters.append(
            {
                "property": "keywords",
                "included": {"operator": "KEYWORDS_SEARCH", "value": ckw_includes},
                "excluded": {"value": ckw_excludes, "operator": "NOT_KEYWORDS_SEARCH"},
                "checkboxes": ["search_desc"],
            }
        )

    contact_locations = _coerce_list(contact_location)
    if contact_locations:
        filters.append(
            {
                "property": "contact.location",
                "included": {"operator": "LOCATION", "value": [[loc, None] for loc in contact_locations]},
                "excluded": {"value": []},
                "checkboxes": [],
            }
        )

    if company_locations:
        filters.append(
            {
                "property": "company.location",
                "included": {"operator": "LOCATION", "value": [[loc, None] for loc in company_locations if loc]},
                "excluded": {"value": []},
                "checkboxes": [],
            }
        )

    position_values = _coerce_list(position)
    if position_values:
        filters.append(
            {
                "property": "company.position",
                "included": {"operator": "CONTAINS_POSITION", "value": position_values},
                "excluded": {"value": []},
                "checkboxes": [],
            }
        )

    seniority_values = _coerce_list(seniority)
    seniority_values = [_normalize_seniority(v) for v in seniority_values]
    seniority_values = [v for v in seniority_values if v]
    if seniority_values:
        filters.append(
            {
                "property": "company.seniority",
                "included": {"operator": "CONTAINS_SENIORITY", "value": seniority_values},
                "excluded": {"value": []},
                "checkboxes": [],
            }
        )

    # Contact names (CONTAINS_NAME)
    name_includes, name_excludes = _split_includes_excludes(_coerce_list(contact_names))
    if name_includes or name_excludes:
        filters.append(
            {
                "property": "contact.name",
                "included": {"operator": "CONTAINS_NAME", "value": name_includes},
                "excluded": {"value": name_excludes},
                "checkboxes": [],
            }
        )

    # Technologies (EQ) -> expect pairs [name, id]; map names only
    tech_includes, tech_excludes = _split_includes_excludes(_coerce_list(technologies))
    if tech_includes or tech_excludes:
        filters.append(
            {
                "property": "company.technologies",
                "included": {"operator": "EQ", "value": [[t, ""] for t in tech_includes]},
                "excluded": {"value": [[t, ""] for t in tech_excludes]},
                "checkboxes": [],
            }
        )

    # Departments (CONTAINS_POSITION)
    dept_includes, dept_excludes = _split_includes_excludes(_coerce_list(departments))
    if dept_includes or dept_excludes:
        filters.append(
            {
                "property": "company.departments",
                "included": {"operator": "CONTAINS_POSITION", "value": [{"matching": [d], "printedData": d} for d in dept_includes]},
                "excluded": {"value": [{"matching": [d], "printedData": d} for d in dept_excludes]},
                "checkboxes": [],
            }
        )

    # Company types (CONTAINS)
    ctype_includes, ctype_excludes = _split_includes_excludes(_coerce_list(company_types))
    if ctype_includes or ctype_excludes:
        filters.append(
            {
                "property": "company.companyType",
                "included": {"operator": "CONTAINS", "value": ctype_includes},
                "excluded": {"value": ctype_excludes},
                "checkboxes": [],
            }
        )

    # Company size ranges (checkboxes) with optional min/max mapping
    canonical_sizes = [
        ("1 - 10", 1, 10),
        ("11 - 20", 11, 20),
        ("21 - 50", 21, 50),
        ("51 - 100", 51, 100),
        ("101 - 200", 101, 200),
        ("201 - 500", 201, 500),
        ("501 - 1000", 501, 1000),
        ("1001 - 2000", 1001, 2000),
        ("2001 - 5000", 2001, 5000),
        ("5001 - 10000", 5001, 10000),
        ("10000", 10000, 999999),
    ]

    normalized_sizes = []
    if company_size_ranges:
        lookup = {label: label for label, _, _ in canonical_sizes}
        for rng in _coerce_list(company_size_ranges):
            if not rng:
                continue
            key = rng.replace("–", "-").strip()
            normalized = lookup.get(key)
            if normalized:
                normalized_sizes.append(normalized)

    if company_size_min is not None or company_size_max is not None:
        min_v = company_size_min if company_size_min is not None else 0
        max_v = company_size_max if company_size_max is not None else 999999
        for label, lo, hi in canonical_sizes:
            if hi < min_v or lo > max_v:
                continue
            if label not in normalized_sizes:
                normalized_sizes.append(label)

    if normalized_sizes:
        filters.append(
            {
                "property": "company.size",
                "included": {"operator": "RANGE", "value": normalized_sizes},
                "excluded": {"value": []},
                "checkboxes": [],
            }
        )

    # Founded year range
    if founded_from or founded_to:
        start = founded_from if founded_from is not None else None
        end = founded_to if founded_to is not None else None
        filters.append(
            {
                "property": "company.foundedAt",
                "included": {
                    "operator": "UNIVERSAL_RANGE",
                    "value": [[start, end, True]],
                },
                "excluded": {"value": []},
                "checkboxes": [],
            }
        )

    return filters


def _normalize_seniority(value: Union[str, List[str]]) -> Optional[Union[str, List[str]]]:
    """
    Normalize a single seniority or a list of seniorities to the allowed enums.
    Returns a single string when given a scalar and a list of strings when given a list.
    """
    if isinstance(value, (list, tuple, set)):
        normalized: List[str] = []
        for item in value:
            norm = _normalize_seniority(item)
            if norm and isinstance(norm, str) and norm not in normalized:
                normalized.append(norm)
        return normalized or None

    if not value:
        return None
    v = str(value).strip().lower()
    synonyms = {
        "c-level": "Chief Officer",
        "c level": "Chief Officer",
        "ceo": "Chief Officer",
        "cto": "Chief Officer",
        "coo": "Chief Officer",
        "chief": "Chief Officer",
        "vp": "VP",
        "vice president": "VP",
        "dir": "Director",
        "director": "Director",
        "sr": "Senior",
        "senior": "Senior",
        "mgr": "Manager",
        "manager": "Manager",
    }
    mapped = synonyms.get(v)
    candidate = mapped or str(value).strip()
    for allowed in ALLOWED_SENIORITY:
        if candidate.lower() == allowed.lower():
            return allowed
    return None


def _find_or_create_company(name: str, domain: str) -> Optional[Company]:
    """
    Find a company by domain (preferred) or name; create if not found.
    Avoids raising on unique constraints when another worker created it first.
    """
    if not name and not domain:
        return None
    normalized_domain = (domain or "").strip().lower()
    normalized_name = name.strip() if name else ""

    try:
        if normalized_domain:
            company = Company.objects.filter(domain__iexact=normalized_domain).first()
            if company:
                return company
        if normalized_name:
            company = Company.objects.filter(name__iexact=normalized_name).first()
            if company:
                return company
        with transaction.atomic():
            company = Company.objects.create(
                name=normalized_name or (normalized_domain or "Unknown Company"),
                domain=normalized_domain,
            )
            return company
    except IntegrityError:
        # Another process might have created it; retry fetch.
        if normalized_domain:
            company = Company.objects.filter(domain__iexact=normalized_domain).first()
            if company:
                return company
        if normalized_name:
            company = Company.objects.filter(name__iexact=normalized_name).first()
            if company:
                return company
    return None


def _fetch_existing_contacts(insight_ids: List[Any]) -> Dict[str, Dict[str, Any]]:
    """
    Fetch existing contacts in a single query and surface communication and subscription context.
    """
    valid_ids = [str(iid) for iid in insight_ids if iid]
    if not valid_ids:
        return {}

    subscriptions_qs = Subscription.objects.select_related("mailing_list")
    contacts = (
        Contact.objects.filter(insight_id__in=valid_ids)
        .prefetch_related(Prefetch("subscriptions", queryset=subscriptions_qs))
    )
    context: Dict[str, Dict[str, Any]] = {}
    for contact in contacts:
        mailing_lists = []
        for sub in contact.subscriptions.all():
            if not sub.mailing_list:
                continue
            mailing_lists.append(
                {
                    "id": sub.mailing_list.pk,
                    "name": sub.mailing_list.name,
                    "slug": sub.mailing_list.slug,
                    "is_active": sub.is_active,
                }
            )
        history = contact.communication_history or []
        contact_payload: Dict[str, Any] = {"contact_id": contact.pk, "email": contact.email}
        if mailing_lists:
            contact_payload["mailing_lists"] = mailing_lists
        if history:
            contact_payload["communication_history"] = history
            summary = contact.formatted_communication_history()
            if summary:
                contact_payload["communication_history_summary"] = summary
        context[str(contact.insight_id)] = contact_payload
    return context


def _persist_leads(leads: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
    """
    Upsert contacts into the CRM using insight_id as the unique key.
    Returns (persisted_count, errors)
    """
    persisted = 0
    errors: List[str] = []
    for lead in leads:
        insight_id = lead.get("insight_id") or lead.get("id")
        if not insight_id:
            continue

        first = lead.get("first_name") or ""
        last = lead.get("last_name") or ""
        job_title = lead.get("position") or ""
        company_name = lead.get("company_name") or ""
        company_domain = lead.get("company_domain") or ""
        raw_item = lead.get("raw") or {}
        email_val = lead.get("email")

        company = _find_or_create_company(company_name, company_domain)
        # Prepare raw company payload for attributes enrichment
        raw_company = None
        try:
            comps = (raw_item or {}).get("companies") or []
            if comps and isinstance(comps[0], dict):
                raw_company = comps[0].get("company")
        except Exception:
            raw_company = None

        if company:
            cattrs = company.attributes or {}
            cattrs.setdefault("getprospect", {})
            if raw_company:
                cattrs["getprospect"]["raw"] = raw_company
            company.attributes = cattrs
            try:
                company.save(update_fields=["attributes"])
            except Exception:
                pass

        try:
            with transaction.atomic():
                contact, created = Contact.objects.get_or_create(
                    insight_id=insight_id,
                    defaults={
                        "first_name": first,
                        "last_name": last,
                        "job_title": job_title,
                        "company": company,
                    },
                )
                fields_to_update = []
                if not created:
                    if not contact.first_name and first:
                        contact.first_name = first
                        fields_to_update.append("first_name")
                    if not contact.last_name and last:
                        contact.last_name = last
                        fields_to_update.append("last_name")
                    if not contact.job_title and job_title:
                        contact.job_title = job_title
                        fields_to_update.append("job_title")
                    if not contact.company and company:
                        contact.company = company
                        fields_to_update.append("company")
                # Store raw payload in attributes under a namespaced key
                attrs = contact.attributes or {}
                attrs.setdefault("getprospect", {})
                attrs["getprospect"]["raw"] = raw_item
                contact.attributes = attrs
                fields_to_update.append("attributes")
                if created:
                    contact.save()
                elif fields_to_update:
                    contact.save(update_fields=fields_to_update)
                persisted += 1
        except IntegrityError as exc:
            errors.append(f"Contact {insight_id}: {exc}")

    return persisted, errors


def lead_search_v2(
    company_name: str = "",
    company_domain: str = "",
    email_status: str = "all",
    contact_location: str = "",
    company_locations: Optional[List[str]] = None,
    position: str = "",
    seniority: str = "",
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
) -> Dict[str, Any]:
    """
    Search contacts (leads) using the GetProspect web-app search endpoint with company filters.

    This endpoint returns contacts plus attached company info. If a contact’s email was previously revealed,
    it appears under companies[].email; otherwise it is absent. Use the insight_id for follow-up email requests.
    """
    creds = get_credentials(
        [
            {
                "key": API_KEY_NAME,
                "label": "GetProspect API Key",
                "type": "password",
                "placeholder": "Enter your GetProspect API key",
                "required": True,
            }
        ]
    )
    if creds is None:
        raise ToolHandlerWarning("GetProspect API key is not set. A secure setup link has been sent.")

    # Keep page size small to limit credit burn; clamp to 50
    if page_size <= 0:
        page_size = 5
    page_size = min(page_size, 50)

    normalized_seniority = _normalize_seniority(seniority)
    filters = _build_filters(
        company_name.strip(),
        company_domain.strip(),
        email_status.strip().lower(),
        contact_location.strip(),
        company_locations or [],
        position.strip(),
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
    payload = {"filters": filters, "requestType": "all"}

    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "apiKey": creds[API_KEY_NAME],
    }
    params = {"pageSize": page_size, "pageNumber": page_number}

    def _call(payload: Dict[str, Any]):
        try:
            return requests.post(
                API_ENDPOINT,
                headers=headers,
                params=params,
                json=payload,
                timeout=15,
            )
        except requests.Timeout:
            return {"error": "timeout"}
        except requests.RequestException as exc:
            return {"error": str(exc)}

    def _extract(resp_json: Dict[str, Any]) -> Dict[str, Any]:
        leads_list = []
        for item in resp_json.get("data", []) or []:
            if not isinstance(item, dict):
                continue
            companies = item.get("companies") or []
            first_company = companies[0].get("company") if companies and isinstance(companies[0], dict) else {}
            position_val = companies[0].get("position") if companies and isinstance(companies[0], dict) else None
            email_val = None
            email_status = None
            email_checked = None
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
                    "company_industry": first_company.get("industry"),
                    "company_size": first_company.get("size"),
                    "company_country": first_company.get("countryCode"),
                    "company_hq": first_company.get("headquarters"),
                    "position": position_val,
                    "saved": bool(item.get("saved")),
                    "linkedin_url": item.get("linkedinUrl"),
                    "raw": item,
                }
            )
        meta_local = resp_json.get("meta") or {}
        return {
            "leads": leads_list,
            "meta": meta_local,
        }

    def _run_with_retry(filters_payload, allow_simplify=True):
        resp = _call(filters_payload)
        if isinstance(resp, dict) and "error" in resp:
            raise ToolHandlerError(f"Request error: {resp['error']}", payload={"leads": [], "meta": {}})
        if not resp.ok:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text[:300]
            raise ToolHandlerError(
                f"GetProspect returned HTTP {resp.status_code}",
                payload={"details": detail, "leads": [], "meta": {}},
            )
        try:
            data_local = resp.json()
        except ValueError:
            raise ToolHandlerError("GetProspect returned a non-JSON response.", payload={"leads": [], "meta": {}})
        extracted = _extract(data_local)
        leads_local = extracted["leads"]
        meta_local = extracted["meta"]
        # If empty and broad filters were used, retry once without position/seniority
        if allow_simplify and not leads_local and (position or seniority):
            simplified_filters = _build_filters(
                company_name.strip(),
                company_domain.strip(),
                email_status.strip().lower(),
                contact_location.strip(),
                position="",
                seniority="",
            )
            fb_payload = {"filters": simplified_filters, "requestType": "all"}
            resp_fb = _run_with_retry(fb_payload, allow_simplify=False)
            # If fallback returns leads, annotate; otherwise propagate handled errors
            if resp_fb and resp_fb.get("leads"):
                resp_fb["note"] = "Simplified filters used after empty result"
                return resp_fb
        return {"leads": leads_local, "meta": meta_local, "raw": data_local}

    result = _run_with_retry(payload, allow_simplify=True)

    leads = result.get("leads", [])
    meta = result.get("meta", {})
    note = result.get("note")

    crm_contacts = _fetch_existing_contacts([lead.get("insight_id") or lead.get("id") for lead in leads])

    persisted_count, persist_errors = _persist_leads(leads)

    total_found = meta.get("totalItems") or len(leads) or 0
    summary_lines = [f"Found {total_found} leads (showing up to {len(leads)})"]

    # Prepare a grouped, human-friendly view: companies -> contacts
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
            "position": lead.get("position"),
            "saved": lead.get("saved"),
            "linkedin": lead.get("linkedin_url"),
        }
        if crm_contact:
            lead_payload["crm_contact"] = crm_contact
        formatted_leads.append(lead_payload)

    if not leads:
        raise ToolHandlerWarning("No leads found for the given filters.", payload={"meta": meta})

    return {
        "total": meta.get("totalItems"),
        "page": meta.get("page"),
        "page_size": meta.get("pageSize"),
        "summary": summary_lines[0],
        "leads": formatted_leads,
        "note": note,
        "persisted": persisted_count,
        "persist_errors": persist_errors,
        "companies": list(companies.values()),
    }


tool_definition = {
    "name": "lead_search_v2",
    "description": (
        "Search contacts (leads) using the GetProspect web-app endpoint. "
        "Returns contact IDs (insight_id) for follow-up email lookup. "
        "You can query broadly (no company filters) or focus with company name/domain. "
        "To exclude, prefix any value with NOT/! (e.g., NOT ExampleCorp)."
    ),
    "parameters": {
        # Contact filters
        "contact_names": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional: contact name fragments to include/exclude (prefix with NOT/! to exclude).",
        },
        "contact_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional: contact keywords to include/exclude (prefix with NOT/! to exclude).",
        },
        "contact_location": {
            "type": "string",
            "description": "Contact location (country or region).",
        },
        "position": {
            "type": "string",
            "description": "Job title keyword (e.g., CEO, Director). Can be combined with or without company filters.",
        },
        "seniority": {
            "type": "string",
            "description": "Seniority level (one of: Owner, Partner, Chief Officer (C-level), VP, Director, Senior, Manager, Intern, Unpaid).",
        },
        # Company filters
        "company_name": {
            "type": "string",
            "description": "Optional: company name (partial match is fine, e.g., 'ADNOC'). Use to focus on a company; leave empty to get mixed companies.",
        },
        "company_domain": {
            "type": "string",
            "description": "Optional: exact company domain. Use when known to narrow results.",
        },
        "company_locations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional: company locations (LOCATION operator).",
        },
        "industries": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional: industries to include/exclude (prefix with NOT/! to exclude).",
        },
        "company_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional: company keywords to include/exclude (prefix with NOT/! to exclude).",
        },
        "technologies": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional: company technologies to include/exclude (prefix with NOT/! to exclude).",
        },
        "departments": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional: departments to include/exclude (prefix with NOT/! to exclude).",
        },
        "company_types": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional: company types to include/exclude (e.g., Private, Public, Nonprofit; prefix with NOT/! to exclude).",
        },
        "company_size_ranges": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional: company size ranges (e.g., '1 - 10', '201 - 500', '5001 - 10000', '10000').",
        },
        "company_size_min": {
            "type": "integer",
            "description": "Optional: company size minimum (maps to predefined ranges).",
        },
        "company_size_max": {
            "type": "integer",
            "description": "Optional: company size maximum (maps to predefined ranges).",
        },
        "founded_from": {
            "type": "integer",
            "description": "Optional: company founded year (from).",
        },
        "founded_to": {
            "type": "integer",
            "description": "Optional: company founded year (to).",
        },
        # Other
        # "email_status": {
        #     "type": "string",
        #     "description": "Email status filter ('all' or 'valid'). Defaults to 'all'.",
        #     "enum": ALLOWED_EMAIL_STATUS,
        #     "default": "all",
        # },
        "page_size": {
            "type": "integer",
            "description": "Results per page (max 50 to limit credits).",
            "default": 20,
        },
        "page_number": {
            "type": "integer",
            "description": "Page number (1-based).",
            "default": 1,
        },
    },
    "required": [],
    "run": lead_search_v2,
}
