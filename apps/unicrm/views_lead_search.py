from __future__ import annotations

from typing import Any, Dict

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View

from unicrm.forms import LeadSearchAdminForm
from unicrm.services.lead_search import run_lead_search
from unicrm.templates.unicrm.unibot.lead_search_v2_tool import (
    ALLOWED_INDUSTRIES,
    ALLOWED_SENIORITY,
)


@method_decorator(staff_member_required, name="dispatch")
class LeadSearchAdminView(View):
    """
    Staff-facing wrapper around the GetProspect lead search.
    Uses the env-configured GETPROSPECT_API_KEY and reuses the bot tool's filter builder/persistence.
    """

    template_name = "unicrm/leads/lead_search_admin.html"

    def get(self, request, *args, **kwargs):
        form = LeadSearchAdminForm()
        context = {
            "form": form,
            "industries": sorted(ALLOWED_INDUSTRIES),
            "seniority_levels": ALLOWED_SENIORITY,
            "company_types": ["Private", "Public", "Education", "Government", "Nonprofit"],
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        form = LeadSearchAdminForm(request.POST)
        context: Dict[str, Any] = {
            "form": form,
            "results": None,
            "error": None,
            "note": None,
            "industries": sorted(ALLOWED_INDUSTRIES),
            "seniority_levels": ALLOWED_SENIORITY,
            "company_types": ["Private", "Public", "Education", "Government", "Nonprofit"],
        }

        if not form.is_valid():
            return render(request, self.template_name, context)

        industries_combined = form.cleaned_data.get("industries") or []
        result, error = run_lead_search(
            api_key=getattr(settings, "GETPROSPECT_API_KEY", None),
            company_name=form.cleaned_data.get("company_name") or [],
            company_domain=form.cleaned_data.get("company_domain") or [],
            email_status=form.cleaned_data.get("email_status", "all").strip().lower(),
            contact_location=form.cleaned_data.get("contact_location") or [],
            company_locations=form.cleaned_data.get("company_locations") or [],
            position=form.cleaned_data.get("position") or [],
            seniority=form.cleaned_data.get("seniority") or [],
            industries=industries_combined,
            company_keywords=form.cleaned_data.get("company_keywords") or [],
            contact_keywords=form.cleaned_data.get("contact_keywords") or [],
            contact_names=form.cleaned_data.get("contact_names") or [],
            technologies=form.cleaned_data.get("technologies") or [],
            departments=form.cleaned_data.get("departments") or [],
            company_types=form.cleaned_data.get("company_types") or [],
            company_size_ranges=form.cleaned_data.get("company_size_ranges") or [],
            company_size_min=form.cleaned_data.get("company_size_min"),
            company_size_max=form.cleaned_data.get("company_size_max"),
            founded_from=form.cleaned_data.get("founded_from"),
            founded_to=form.cleaned_data.get("founded_to"),
            page_size=form.cleaned_data.get("page_size"),
            page_number=form.cleaned_data.get("page_number"),
            request_type=form.cleaned_data.get("request_type") or "excluded",
        )
        if error:
            context["error"] = error
            return render(request, self.template_name, context)

        total = result.get("total") or 0
        page_size = result.get("page_size") or 1
        total_pages = (total + page_size - 1) // page_size if page_size else 1
        context.update(
            {
                "results": result,
                "note": result.get("note"),
                "total_pages": total_pages,
            }
        )
        return render(request, self.template_name, context)


@method_decorator(staff_member_required, name="dispatch")
class LeadSearchUiDemoView(View):
    """
    Static UI demo for include/exclude tag-based filters.
    """

    template_name = "unicrm/leads/lead_search_ui_demo.html"

    def get(self, request, *args, **kwargs):
        employee_ranges = [
            "1 - 10",
            "11 - 20",
            "21 - 50",
            "51 - 100",
            "101 - 200",
            "201 - 500",
            "501 - 1000",
            "1001 - 2000",
            "2001 - 5000",
            "5001 - 10000",
            "10000",
        ]
        company_types = ["Private", "Public", "Education", "Government", "Nonprofit"]
        context = {
            "industries": sorted(ALLOWED_INDUSTRIES),
            "seniority_levels": ALLOWED_SENIORITY,
            "company_types": company_types,
            "employee_ranges": employee_ranges,
        }
        return render(request, self.template_name, context)
