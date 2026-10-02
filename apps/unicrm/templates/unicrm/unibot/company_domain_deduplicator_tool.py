import re
from typing import Dict, Iterable, List, Sequence, Union

from django.db.models import Q

from unicrm.models import Company


def _normalize_domain(value: str) -> str:
    if not value:
        return ""
    trimmed = value.strip().lower()
    trimmed = re.sub(r"^https?://", "", trimmed)
    trimmed = trimmed.split("/", 1)[0]
    if trimmed.startswith("www."):
        trimmed = trimmed[4:]
    return trimmed


def _prepare_domains(domains: Union[str, Sequence[str]]) -> List[str]:
    if isinstance(domains, str):
        parts: Iterable[str] = re.split(r"[\s,;]+", domains)
    else:
        parts = domains
    normalized = [_normalize_domain(part) for part in parts if part]
    return sorted({domain for domain in normalized if domain})


def check_company_domains(domains: Union[str, Sequence[str]]) -> str:
    domain_list = _prepare_domains(domains)
    if not domain_list:
        return "No valid domain names were provided."

    query = Q()
    for domain in domain_list:
        query |= Q(domain__iexact=domain)

    existing: Dict[str, str] = {}
    if query:
        for company in Company.objects.filter(query):
            normalized = _normalize_domain(company.domain or "")
            if normalized:
                existing[normalized] = company.name

    available = [domain for domain in domain_list if domain not in existing]

    lines: list[str] = []
    if existing:
        lines.append("Existing domains already in the database:")
        for domain, name in existing.items():
            lines.append(f"- {domain} -> {name}")
    if available:
        lines.append("Available domains that can safely be added:")
        for domain in available:
            lines.append(f"- {domain}")

    return "\n".join(lines) if lines else "No matching domains were found."


tool_definition = {
    "name": "check_company_domains",
    "description": "Checks provided domains against unicrm.Company records and reports which ones already exist versus which are new.",
    "parameters": {
        "domains": {
            "type": "string",
            "description": "Domains to check, provided as a comma-separated string or JSON array encoded as a string.",
        }
    },
    "run": check_company_domains,
}
