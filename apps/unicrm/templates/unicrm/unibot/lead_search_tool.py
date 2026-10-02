from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from unibot.services.tool_exceptions import ToolHandlerError, ToolHandlerWarning
from unicrm.services.lead_search import run_lead_search
from unicrm.templates.unicrm.unibot.lead_search_v2_tool import (
    ALLOWED_INDUSTRIES,
    ALLOWED_SENIORITY,
    _normalize_seniority,
)

ALLOWED_COMPANY_TYPES = ["Private", "Public", "Education", "Government", "Nonprofit"]


def _as_list(value: Optional[Union[str, Sequence[str]]]) -> List[str]:
    """
    Normalize string/sequence into a flat list of non-empty strings.
    Supports comma/newline-delimited strings.
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
            items.extend(_as_list(v))
        return items
    cleaned = str(value).strip()
    return [cleaned] if cleaned else []


def _clean_domain(domain: str) -> str:
    """
    Strip protocol, trailing slash, and leading www from a domain-like string.
    """
    cleaned = domain.strip()
    for prefix in ("http://", "https://"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    if "/" in cleaned:
        cleaned = cleaned.split("/", 1)[0]
    if cleaned.lower().startswith("www."):
        cleaned = cleaned[4:]
    return cleaned.strip()


def _combine_includes_excludes(
    includes: Optional[Union[str, Sequence[str]]] = None,
    excludes: Optional[Union[str, Sequence[str]]] = None,
    value_transform=None,
) -> List[str]:
    """
    Merge include/exclude lists into the legacy NOT/! prefix format expected by _build_filters.
    """
    merged: List[str] = []
    for val in _as_list(includes):
        transformed = value_transform(val) if value_transform else val
        if transformed:
            merged.append(transformed)
    for val in _as_list(excludes):
        transformed = value_transform(val) if value_transform else val
        if not transformed:
            continue
        merged.append(f"NOT {transformed}")
    # Preserve order but drop obvious duplicates
    seen = set()
    deduped: List[str] = []
    for v in merged:
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(v)
    return deduped


def _normalize_domains(
    includes: Optional[Union[str, Sequence[str]]] = None,
    excludes: Optional[Union[str, Sequence[str]]] = None,
) -> List[str]:
    return _combine_includes_excludes(includes, excludes, value_transform=_clean_domain)


def _normalize_industries(
    includes: Optional[Union[str, Sequence[str]]] = None,
    excludes: Optional[Union[str, Sequence[str]]] = None,
) -> Tuple[List[str], List[str]]:
    """
    Enforce exact industry enums so the API receives valid filters.
    Returns (values_with_not_prefix, errors).
    """
    allowed_lookup = {cand.lower().replace("&", "and").strip(): cand for cand in ALLOWED_INDUSTRIES}
    # Allow the composite alias from the legacy tool
    aliases = {"transportation & storage": "Transportation & Storage"}

    def _match(value: str) -> Optional[str]:
        norm = value.lower().replace("&", "and").strip()
        if norm in allowed_lookup:
            return allowed_lookup[norm]
        if norm in aliases:
            return aliases[norm]
        return None

    errors: List[str] = []
    normalized_includes: List[str] = []
    for val in _as_list(includes):
        match = _match(val)
        if match:
            normalized_includes.append(match)
        else:
            errors.append(
                f"Invalid industry '{val}'. Use one of the predefined options from ALLOWED_INDUSTRIES."
            )

    normalized_excludes: List[str] = []
    for val in _as_list(excludes):
        match = _match(val)
        if match:
            normalized_excludes.append(match)
        else:
            errors.append(
                f"Invalid industry '{val}'. Use one of the predefined options from ALLOWED_INDUSTRIES."
            )

    combined = _combine_includes_excludes(normalized_includes, normalized_excludes)
    return combined, errors


def _normalize_seniority_list(
    values: Optional[Union[str, Sequence[str]]]
) -> Tuple[List[str], List[str]]:
    normalized: List[str] = []
    errors: List[str] = []
    for val in _as_list(values):
        mapped = _normalize_seniority(val)
        if mapped:
            if mapped not in normalized:
                normalized.append(mapped)
        else:
            errors.append(
                f"Ignored seniority '{val}'. Allowed values: {', '.join(ALLOWED_SENIORITY)}"
            )
    return normalized, errors


def _normalize_company_types(
    includes: Optional[Union[str, Sequence[str]]] = None,
    excludes: Optional[Union[str, Sequence[str]]] = None,
) -> Tuple[List[str], List[str]]:
    allowed_lookup = {v.lower(): v for v in ALLOWED_COMPANY_TYPES}
    errors: List[str] = []
    inc_norm: List[str] = []
    exc_norm: List[str] = []

    def _match(val: str) -> Optional[str]:
        return allowed_lookup.get(val.strip().lower())

    for val in _as_list(includes):
        match = _match(val)
        if match:
            inc_norm.append(match)
        else:
            errors.append(f"Invalid company type '{val}'. Allowed: {', '.join(ALLOWED_COMPANY_TYPES)}")
    for val in _as_list(excludes):
        match = _match(val)
        if match:
            exc_norm.append(match)
        else:
            errors.append(f"Invalid company type '{val}'. Allowed: {', '.join(ALLOWED_COMPANY_TYPES)}")

    return _combine_includes_excludes(inc_norm, exc_norm), errors


def _derive_size_ranges(min_size: Optional[int], max_size: Optional[int]) -> List[str]:
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
    if min_size is None and max_size is None:
        return []
    min_v = min_size if min_size is not None else 0
    max_v = max_size if max_size is not None else 999999
    ranges: List[str] = []
    for label, lo, hi in canonical_sizes:
        if hi < min_v or lo > max_v:
            continue
        ranges.append(label)
    return ranges


def lead_search(
    *,
    company_names_include: Optional[Union[str, Sequence[str]]] = None,
    company_names_exclude: Optional[Union[str, Sequence[str]]] = None,
    company_domains_include: Optional[Union[str, Sequence[str]]] = None,
    company_domains_exclude: Optional[Union[str, Sequence[str]]] = None,
    industries_include: Optional[Union[str, Sequence[str]]] = None,
    industries_exclude: Optional[Union[str, Sequence[str]]] = None,
    contact_names_include: Optional[Union[str, Sequence[str]]] = None,
    contact_names_exclude: Optional[Union[str, Sequence[str]]] = None,
    contact_keywords_include: Optional[Union[str, Sequence[str]]] = None,
    contact_keywords_exclude: Optional[Union[str, Sequence[str]]] = None,
    company_keywords_include: Optional[Union[str, Sequence[str]]] = None,
    company_keywords_exclude: Optional[Union[str, Sequence[str]]] = None,
    technologies_include: Optional[Union[str, Sequence[str]]] = None,
    technologies_exclude: Optional[Union[str, Sequence[str]]] = None,
    departments_include: Optional[Union[str, Sequence[str]]] = None,
    departments_exclude: Optional[Union[str, Sequence[str]]] = None,
    company_types_include: Optional[Union[str, Sequence[str]]] = None,
    company_types_exclude: Optional[Union[str, Sequence[str]]] = None,
    contact_location: Union[str, Sequence[str]] = "",
    company_locations: Optional[List[str]] = None,
    position: Union[str, Sequence[str]] = "",
    seniority: Optional[Union[str, Sequence[str]]] = None,
    company_size_min: Optional[int] = None,
    company_size_max: Optional[int] = None,
    founded_from: Optional[int] = None,
    founded_to: Optional[int] = None,
    page_size: int = 20,
    page_number: int = 1,
) -> Dict[str, Any]:
    """
    Unified lead search wrapper for GetProspect.

    This is the preferred tool for the LLM: it wraps unicrm.services.lead_search.run_lead_search,
    applies strict enums for constrained fields (industries, seniority, company type),
    and normalizes domains/filters before passing them to the service.
    """
    industries, industry_errors = _normalize_industries(industries_include, industries_exclude)
    seniorities, seniority_errors = _normalize_seniority_list(seniority)
    company_types, company_type_errors = _normalize_company_types(
        company_types_include, company_types_exclude
    )
    errors = industry_errors + seniority_errors + company_type_errors
    if errors:
        raise ToolHandlerError("Invalid filter values", payload={"errors": errors})

    company_names = _combine_includes_excludes(company_names_include, company_names_exclude)
    company_domains = _normalize_domains(company_domains_include, company_domains_exclude)
    contact_names = _combine_includes_excludes(contact_names_include, contact_names_exclude)
    contact_keywords = _combine_includes_excludes(contact_keywords_include, contact_keywords_exclude)
    company_keywords = _combine_includes_excludes(company_keywords_include, company_keywords_exclude)
    technologies = _combine_includes_excludes(technologies_include, technologies_exclude)
    departments = _combine_includes_excludes(departments_include, departments_exclude)
    size_ranges = _derive_size_ranges(company_size_min, company_size_max)

    normalized_contact_location: Union[str, List[str]] = (
        contact_location if isinstance(contact_location, str) else _as_list(contact_location)
    )
    normalized_position: Union[str, List[str]] = (
        position if isinstance(position, str) else _as_list(position)
    )

    result, error = run_lead_search(
        company_name=company_names,
        company_domain=company_domains,
        email_status="all",
        contact_location=normalized_contact_location,
        company_locations=company_locations or [],
        position=normalized_position,
        seniority=seniorities,
        industries=industries,
        company_keywords=company_keywords,
        contact_keywords=contact_keywords,
        contact_names=contact_names,
        technologies=technologies,
        departments=departments,
        company_types=company_types,
        company_size_ranges=size_ranges,
        company_size_min=None,
        company_size_max=None,
        founded_from=founded_from,
        founded_to=founded_to,
        page_size=page_size,
        page_number=page_number,
        request_type="all",
    )

    if error:
        raise ToolHandlerWarning(error, payload={"leads": [], "meta": {}, "filters": result.get("filters")})

    if not result.get("leads"):
        raise ToolHandlerWarning("No leads found for the given filters.", payload=result)

    return result


tool_definition = {
    "name": "lead_search",
    "description": (
        "Search contacts (leads) via GetProspect using the unified service. "
        "Supports include/exclude for company names/domains/keywords, industries (enum), "
        "titles, seniority (enum), locations, technologies, company types (enum), company size via min/max mapping, and founded year. "
        "Returns full lead details including insight_id, company metadata, grouping, raw meta, and applied filters. "
        "Use this instead of lead_search_v2."
    ),
    "parameters": {
        # Company filters
        "company_names_include": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Company names to include (partial match).",
        },
        "company_names_exclude": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Company names to exclude.",
        },
        "company_domains_include": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Company domains to include (plain domain only; no protocol).",
        },
        "company_domains_exclude": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Company domains to exclude (plain domain only; no protocol).",
        },
        "industries_include": {
            "type": "array",
            "items": {"type": "string", "enum": ALLOWED_INDUSTRIES},
            "description": "Industries to include (exactly one of the predefined values).",
        },
        "industries_exclude": {
            "type": "array",
            "items": {"type": "string", "enum": ALLOWED_INDUSTRIES},
            "description": "Industries to exclude (exactly one of the predefined values).",
        },
        "company_keywords_include": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Company keywords to include.",
        },
        "company_keywords_exclude": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Company keywords to exclude.",
        },
        "company_types_include": {
            "type": "array",
            "items": {"type": "string", "enum": ALLOWED_COMPANY_TYPES},
            "description": "Company types to include (enum: Private, Public, Education, Government, Nonprofit).",
        },
        "company_types_exclude": {
            "type": "array",
            "items": {"type": "string", "enum": ALLOWED_COMPANY_TYPES},
            "description": "Company types to exclude (enum: Private, Public, Education, Government, Nonprofit).",
        },
        "company_locations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Company locations (country/region/city).",
        },
        "company_size_min": {
            "type": "integer",
            "description": "Minimum company size (maps to predefined ranges).",
        },
        "company_size_max": {
            "type": "integer",
            "description": "Maximum company size (maps to predefined ranges).",
        },
        "founded_from": {
            "type": "integer",
            "description": "Founded year (from).",
        },
        "founded_to": {
            "type": "integer",
            "description": "Founded year (to).",
        },
        # Contact filters
        "contact_names_include": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Contact name fragments to include.",
        },
        "contact_names_exclude": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Contact name fragments to exclude.",
        },
        "contact_keywords_include": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Contact keywords to include.",
        },
        "contact_keywords_exclude": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Contact keywords to exclude.",
        },
        "contact_location": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Contact location(s) (country/region/city).",
        },
        "position": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Job title keywords.",
        },
        "seniority": {
            "type": "array",
            "items": {"type": "string", "enum": ALLOWED_SENIORITY},
            "description": "Seniority levels (choose from the enum list).",
        },
        "departments_include": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Departments to include (e.g., Marketing, Sales).",
        },
        "departments_exclude": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Departments to exclude.",
        },
        "technologies_include": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Technologies to include.",
        },
        "technologies_exclude": {
            "type": ["array", "string"],
            "items": {"type": "string"},
            "description": "Technologies to exclude.",
        },
        # Other toggles/pagination
        "page_size": {
            "type": "integer",
            "description": "Results per page (1-50).",
            "default": 20,
        },
        "page_number": {
            "type": "integer",
            "description": "Page number (1-based).",
            "default": 1,
        },
    },
    "required": [],
    "run": lead_search,
}
