import requests
from typing import Any, Dict, List, Optional, Sequence, Union

from unibot.services.credentials import get_credentials

API_ENDPOINT = "https://api.getprospect.com/public/v1/insights/contacts"
API_KEY_NAME = "GETPROSPECT_API_KEY"
ALLOWED_SENIORITY = [
    "Owner", "Partner", "Chief Officer", "VP", "Director",
    "Senior", "Manager", "Intern", "Unpaid",
]
ALLOWED_EMPLOYEE_RANGES = [
    "1 - 10", "11 - 20", "21 - 50", "51 - 100", "101 - 200",
    "201 - 500", "501 - 1000", "1001 - 2000", "2001 - 5000",
    "5001 - 10000", "10000",
]
# Long industry list from the GetProspect schema
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

# Helpers for building the GetProspect request payloads
def _build_text_filter(value: Union[str, Sequence[str], None]) -> Optional[Dict[str, List[str]]]:
    if value is None:
        return None
    if isinstance(value, str):
        values = _as_list(value)
    else:
        values = [v.strip() for v in value if isinstance(v, str) and v.strip()]
    return {"included": values} if values else None


def _as_list(value: Optional[Union[str, Sequence[str]]]) -> List[str]:
    """
    Normalize a string or sequence into a clean list of non-empty strings.
    Accepts comma-separated strings too.
    """
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",")]
        return [p for p in parts if p]
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def _build_include_exclude_filter(
    included: Optional[Union[str, Sequence[str]]] = None,
    excluded: Optional[Union[str, Sequence[str]]] = None,
) -> Optional[Dict[str, List[str]]]:
    inc = _as_list(included)
    exc = _as_list(excluded)
    if not inc and not exc:
        return None
    payload: Dict[str, List[str]] = {}
    if inc:
        payload["included"] = inc
    if exc:
        payload["excluded"] = exc
    return payload


def _build_seniority_filter(
    included: Optional[Union[str, Sequence[str]]] = None,
    excluded: Optional[Union[str, Sequence[str]]] = None,
) -> Optional[Dict[str, Union[str, List[str]]]]:
    # API schema shows single-string enums, but some clients send arrays.
    # We accept arrays and pass them through if multiple are provided.
    inc = _as_list(included)
    exc = _as_list(excluded)
    if not inc and not exc:
        return None
    payload: Dict[str, Union[str, List[str]]] = {}
    if inc:
        payload["included"] = inc if len(inc) > 1 else inc[0]
    if exc:
        payload["excluded"] = exc if len(exc) > 1 else exc[0]
    return payload


def _normalize_industries(
    included: Optional[Union[str, Sequence[str]]] = None,
    excluded: Optional[Union[str, Sequence[str]]] = None,
) -> tuple[Optional[Dict[str, List[str]]], List[str]]:
    """
    Normalize industry values to the exact enums GetProspect expects.
    Returns (filter_payload_or_None, errors)
    """
    errors: List[str] = []
    inc_raw = _as_list(included)
    exc_raw = _as_list(excluded)

    if not inc_raw and not exc_raw:
        return None, errors

    def _match_one(value: str) -> Optional[str]:
        normalized = value.lower().replace("&", "and")
        for candidate in ALLOWED_INDUSTRIES:
            if normalized == candidate.lower().replace("&", "and"):
                return candidate
        # loose contains match fallback
        for candidate in ALLOWED_INDUSTRIES:
            c_norm = candidate.lower().replace("&", "and")
            if normalized in c_norm:
                return candidate
        return None

    inc: List[str] = []
    for v in inc_raw:
        matched = _match_one(v)
        if matched:
            inc.append(matched)
        else:
            errors.append(f"Invalid industry '{v}'. Use one of the standard names (e.g., 'Information Technology and Services').")

    exc: List[str] = []
    for v in exc_raw:
        matched = _match_one(v)
        if matched:
            exc.append(matched)
        else:
            errors.append(f"Invalid industry '{v}'. Use one of the standard names (e.g., 'Information Technology and Services').")

    if errors:
        return None, errors

    payload: Dict[str, List[str]] = {}
    if inc:
        payload["included"] = inc
    if exc:
        payload["excluded"] = exc
    return payload or None, errors


def search_leads(
    contact_name: str = "",
    company_name: str = "",
    job_title: str = "",
    domain: str = "",
    keywords: Optional[Union[str, Sequence[str]]] = None,
    location: str = "",
    headquarters: str = "",
    industry_include: Optional[Union[str, Sequence[str]]] = None,
    industry_exclude: Optional[Union[str, Sequence[str]]] = None,
    seniority_include: Optional[Union[str, Sequence[str]]] = None,
    seniority_exclude: Optional[Union[str, Sequence[str]]] = None,
    employees_size: str = "",
    page_size: int = 10,
    page_number: int = 1,
    sort: str = "",
    order: str = "ASC",
) -> Dict[str, Any]:
    """
    Search GetProspect contacts with rich filters.

    Args mirror the GetProspect Search leads endpoint. Most are optional; empty values are skipped.
    """
    creds = get_credentials([
        {
            "key": API_KEY_NAME,
            "label": "GetProspect API Key",
            "type": "password",
            "placeholder": "Enter your GetProspect API key",
            "required": True,
        }
    ])
    if creds is None:
        return {
            "success": False,
            "error": "GetProspect API key is not set. A secure setup link has been sent.",
        }

    api_key = creds[API_KEY_NAME]

    # Validate enums to avoid API 400/500s
    errors: List[str] = []
    sort_allowed = [
        "id", "firstName", "lastName", "contactInfo", "summary",
        "geolocation.region", "geolocation.timezone", "geolocation.location", "geolocation.countryCode",
    ]
    if sort and sort not in sort_allowed:
        errors.append(f"Invalid sort '{sort}'. Choose one of: {', '.join(sort_allowed)}.")
    if order and order not in ["ASC", "DESC"]:
        errors.append("Invalid order. Use ASC or DESC.")

    if employees_size:
        if employees_size not in ALLOWED_EMPLOYEE_RANGES:
            errors.append("employees_size must be one of the documented ranges like '51 - 100' or '201 - 500'.")

    if seniority_include and isinstance(seniority_include, str):
        seniority_include = _as_list(seniority_include)
    if seniority_exclude and isinstance(seniority_exclude, str):
        seniority_exclude = _as_list(seniority_exclude)

    def _validate_seniority(values: Optional[Union[str, Sequence[str]]]) -> Optional[Union[str, List[str]]]:
        vals = _as_list(values)
        invalid = [v for v in vals if v not in ALLOWED_SENIORITY]
        if invalid:
            errors.append(f"Invalid seniority value(s): {', '.join(invalid)}. Allowed: {', '.join(ALLOWED_SENIORITY)}.")
            return None
        return vals if len(vals) > 1 else (vals[0] if vals else None)

    seniority_filter = _validate_seniority(seniority_include)
    seniority_excluded_values = _validate_seniority(seniority_exclude)

    industry_filter, industry_errors = _normalize_industries(industry_include, industry_exclude)
    errors.extend(industry_errors)

    if errors:
        return {"success": False, "error": "Validation failed", "details": errors}

    query_params = {}
    if page_size:
        query_params["pageSize"] = page_size
    if page_number:
        query_params["pageNumber"] = page_number
    if sort:
        query_params["sort"] = sort
    if order:
        query_params["order"] = order

    payload: Dict[str, Any] = {"email": "all_contacts"}
    # Prefer job_title/location/keywords/company_name; discourage empty strings
    for field, value in [
        ("contactName", contact_name),
        ("companyName", company_name),
        ("jobTitle", job_title),
        ("domain", domain),
        ("location", location),
        ("headquarters", headquarters),
    ]:
        flt = _build_text_filter(value)
        if flt:
            payload[field] = flt

    if keywords:
        kw_filter = _build_text_filter(keywords)
        if kw_filter:
            payload["keywords"] = kw_filter

    if industry_filter:
        payload["industry"] = industry_filter

    if seniority_filter or seniority_excluded_values:
        combined = {}
        if seniority_filter:
            combined["included"] = seniority_filter
        if seniority_excluded_values:
            combined["excluded"] = seniority_excluded_values
        payload["seniority"] = combined

    if employees_size:
        employees_size = employees_size.strip()
        if employees_size in ALLOWED_EMPLOYEE_RANGES:
            payload["employees"] = {"included": employees_size}

    # Require at least one substantive filter so the LLM doesn't fire empty queries
    if len(payload.keys() - {"email"}) == 0:
        return {
            "success": False,
            "error": (
                "Please provide at least one useful filter: job_title, keywords, location, "
                "company_name, industry_include, domain, or last_updated."
            ),
        }

    headers = {"apiKey": api_key}

    try:
        response = requests.post(
            API_ENDPOINT,
            params=query_params,
            json=payload if payload else None,
            headers=headers,
            timeout=20,
        )
    except requests.Timeout:
        return {"success": False, "error": "Request to GetProspect timed out."}
    except requests.RequestException as exc:
        return {"success": False, "error": f"Request error: {exc}"}

    if not response.ok:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:300]
        return {
            "success": False,
            "error": f"GetProspect returned HTTP {response.status_code}",
            "details": detail,
        }

    try:
        data = response.json()
    except ValueError:
        return {"success": False, "error": "GetProspect returned a non-JSON response."}

    leads = []
    for item in data.get("data", []) or []:
        if not isinstance(item, dict):
            continue
        companies = [
            c.get("name") for c in (item.get("companies") or []) if isinstance(c, dict) and c.get("name")
        ]
        linkedin_urls = [
            ln.get("url") for ln in (item.get("linkedin") or []) if isinstance(ln, dict) and ln.get("url")
        ]
        full_name = " ".join(
            part for part in [item.get("firstName"), item.get("lastName")] if part
        ).strip()
        geolocation = item.get("geolocation") if isinstance(item.get("geolocation"), dict) else {}
        leads.append({
            "id": item.get("getProspectId"),
            "name": full_name or item.get("summary") or item.get("contactInfo"),
            "job_title": item.get("summary") or item.get("contactInfo"),
            "companies": companies,
            "country": geolocation.get("countryCode"),
            "linkedin": linkedin_urls[0] if linkedin_urls else None,
            "raw": item,
        })

    return {
        "success": True,
        "total": (data.get("meta") or {}).get("totalItems"),
        "page": (data.get("meta") or {}).get("page"),
        "page_size": (data.get("meta") or {}).get("pageSize"),
        "leads": leads,
        "raw": data,
    }


tool_definition = {
    "name": "search_leads",
    "description": "Search B2B contacts using GetProspect with filters like name, company, title, industry, location, and pagination.",
    "parameters": {
        "contact_name": {"type": "string", "description": "Contact name to include (optional)."},
        "company_name": {"type": "string", "description": "Company name to include (optional)."},
        "job_title": {"type": "string", "description": "Job title to include (optional)."},
        "domain": {"type": "string", "description": "Company domain to include (optional)."},
    "keywords": {"type": "string", "description": "Keywords to include (comma-separated or single)."},
    "location": {"type": "string", "description": "Location text to include (city/region/country)."},
        "headquarters": {"type": "string", "description": "Headquarters location to include."},
        "industry_include": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Industries to include (use GetProspect names, e.g., 'Information Technology and Services').",
        },
    "industry_exclude": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Industries to exclude.",
        },
        "seniority_include": {
            "type": "array",
        "items": {"type": "string"},
        "description": "Seniority levels to include (Owner, Partner, Chief Officer, VP, Director, Senior, Manager, Intern, Unpaid).",
        "enum": ALLOWED_SENIORITY,
    },
    "seniority_exclude": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Seniority levels to exclude.",
        "enum": ALLOWED_SENIORITY,
    },
        "employees_size": {
            "type": "string",
            "description": "Company size range (e.g., '51 - 100', '201 - 500', '10000').",
            "enum": ALLOWED_EMPLOYEE_RANGES,
        },
        "page_size": {
            "type": "integer",
            "description": "Results per page (default 10, max per API docs).",
            "default": 10,
        },
        "page_number": {
            "type": "integer",
            "description": "Page number (default 1).",
            "default": 1,
    },
    "sort": {
        "type": "string",
        "description": "Property to sort by (id, firstName, lastName, contactInfo, summary, geolocation.region, geolocation.timezone, geolocation.location, geolocation.countryCode).",
        "enum": [
            "id", "firstName", "lastName", "contactInfo", "summary",
            "geolocation.region", "geolocation.timezone", "geolocation.location", "geolocation.countryCode",
        ],
    },
    "order": {
        "type": "string",
        "description": "Sort order (ASC or DESC).",
        "default": "ASC",
        "enum": ["ASC", "DESC"],
    },
    },
    "run": search_leads,
}
