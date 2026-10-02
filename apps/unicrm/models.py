from __future__ import annotations

from pathlib import Path
import types
from typing import Callable, Sequence

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.validators import validate_slug
from django.db import models
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


SNIPPETS_DIR = Path(__file__).resolve().parent / 'templates' / 'unicrm' / 'snippets'

SAFE_BUILTINS = {
    'str': str,
    'int': int,
    'float': float,
    'len': len,
    'min': min,
    'max': max,
    'sum': sum,
    'sorted': sorted,
    'round': round,
    'any': any,
    'all': all,
}


def _read_snippet(filename: str) -> str:
    path = SNIPPETS_DIR / filename
    try:
        return path.read_text(encoding='utf-8').strip() + '\n'
    except FileNotFoundError:
        return ''


def _default_template_variable_code() -> str:
    return _read_snippet('template_variable.py')


def _default_segment_code() -> str:
    return _read_snippet('segment_filter.py')


def compile_callable(code: str, func_name: str, extra_globals: dict[str, object] | None = None) -> Callable:
    """
    Compiles the provided code and returns the function with name ``func_name``.
    Allows full Python execution for staff users.
    """
    namespace: dict[str, object] = {}
    globals_dict: dict[str, object] = {'__builtins__': __builtins__}
    if extra_globals:
        globals_dict.update(extra_globals)
    exec(code, globals_dict, namespace)
    if namespace:
        globals_dict.update(namespace)
    func = namespace.get(func_name) or globals_dict.get(func_name)
    if not callable(func):
        raise ValueError(f"Callable `{func_name}` not found in provided code.")
    return func  # type: ignore[return-value]


class TimeStamped(models.Model):
    created_at = models.DateTimeField(_('Created at'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated at'), auto_now=True)

    class Meta:
        abstract = True


class Company(TimeStamped):
    """Represents an organisation that owns one or more contacts."""

    name = models.CharField(_('Name'), max_length=255, unique=True)
    domain = models.CharField(
        _('Email domain'),
        max_length=255,
        blank=True,
        unique=True,
        help_text=_('Primary email domain for this company (optional)')
    )
    website = models.URLField(_('Website'), blank=True)
    industry = models.CharField(
        _('Industry'),
        max_length=255,
        blank=True,
        help_text=_('Primary industry or vertical focus for this company (optional).')
    )
    notes = models.TextField(_('Internal notes'), blank=True)
    attributes = models.JSONField(
        _('Custom attributes'),
        default=dict,
        blank=True,
        help_text=_('Arbitrary data map available to template variables.')
    )

    class Meta:
        ordering = ('name',)
        verbose_name_plural = _('Companies')

    def __str__(self) -> str:
        return self.name


class Contact(TimeStamped):
    """
    Stores CRM contact information and custom attributes for template variables.
    """

    first_name = models.CharField(_('First name'), max_length=150, blank=True)
    last_name = models.CharField(_('Last name'), max_length=150, blank=True)
    email = models.EmailField(_('Email'), unique=True, blank=True, null=True)
    insight_id = models.CharField(
        _('GetProspect insight id'),
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        help_text=_('External lead identifier from GetProspect; used for email retrieval.'),
    )
    phone_number = models.CharField(_('Phone number'), max_length=50, blank=True)
    job_title = models.CharField(_('Job title'), max_length=150, blank=True)
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contacts',
    )
    user = models.OneToOneField(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='crm_contact',
        help_text=_('Linked Django auth user for this contact, when applicable.'),
    )
    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_contacts',
        help_text=_('Optional staff owner responsible for this contact.')
    )
    attributes = models.JSONField(
        _('Custom attributes'),
        default=dict,
        blank=True,
        help_text=_('Arbitrary data map available to template variables.')
    )
    communication_history = models.JSONField(
        _('Communication history'),
        default=list,
        blank=True,
        help_text=_('Cached list of communications involving this contact.')
    )
    email_bounced = models.BooleanField(
        _('Email bounced'),
        default=False,
        help_text=_('True when a recent outbound email to this contact bounced.')
    )
    email_bounced_at = models.DateTimeField(
        _('Email bounced at'),
        null=True,
        blank=True,
        help_text=_('Most recent bounce timestamp cached for this contact.')
    )
    email_bounce_type = models.CharField(
        _('Email bounce type'),
        max_length=20,
        blank=True,
        help_text=_('Classification of the most recent bounce (e.g. hard or soft).')
    )
    gp_requested_at = models.DateTimeField(
        _('GetProspect requested at'),
        null=True,
        blank=True,
        help_text=_('Timestamp when a GetProspect email request was initiated for this contact.'),
        db_index=True,
    )
    gp_email_checked_at = models.DateTimeField(
        _('GetProspect email checked at'),
        null=True,
        blank=True,
        help_text=_('Last time we polled GetProspect for this contact’s email.'),
        db_index=True,
    )
    gp_email_status = models.CharField(
        _('GetProspect email status'),
        max_length=20,
        blank=True,
        help_text=_('Status of GetProspect email lookup (e.g. pending, valid, invalid, not_found).'),
        db_index=True,
    )

    class Meta:
        ordering = ('last_name', 'first_name')

    def __str__(self) -> str:
        full_name = f"{self.first_name} {self.last_name}".strip()
        if full_name:
            if self.email:
                return f"{full_name} <{self.email}>"
            return full_name

        if self.email:
            return self.email

        username = (self.attributes or {}).get('auth_user_username')
        if username:
            return username

        if self.pk:
            return f'Contact #{self.pk}'
        return 'Contact'

    def formatted_communication_history(self) -> str:
        """
        Returns a human-readable rendering of the cached communication history.
        """
        entries = self.communication_history or []
        if not entries:
            return 'No communications recorded.'

        lines: list[str] = []
        for item in entries:
            status = (item.get('status') or '').lower()
            if status in {'failed', 'bounced'}:
                continue
            subject = item.get('subject') or 'No subject'
            direction = item.get('direction') or 'unknown'
            status_label = item.get('status') or 'unknown'
            sent_at = item.get('sent_at') or item.get('timestamp')
            channel = item.get('channel') or item.get('platform') or ''
            reaction = ''
            if item.get('opened_at') or item.get('clicked_at') or item.get('replied_at'):
                reactions = []
                if item.get('opened_at'):
                    reactions.append('opened')
                if item.get('clicked_at'):
                    reactions.append('clicked')
                if item.get('replied_at') or item.get('has_received_reply'):
                    reactions.append('replied')
                reaction = f" | {'/'.join(reactions)}"
            sent_label = f" @ {sent_at}" if sent_at else ''
            channel_label = f" via {channel}" if channel else ''
            lines.append(f"[{direction}{channel_label}] {subject}{sent_label} ({status_label}{reaction})")

        return '\n'.join(lines)

    def request_getprospect_email(
        self,
        api_key: str,
        company_id: str | None = None,
        filters: dict | None = None,
        timeout: int = 15,
    ) -> dict:
        """
        Trigger the GetProspect "Show Email" flow for this contact.

        This will:
        - POST /api/v1/insights/search (user_search) with provided filters to get a userSearchId
        - POST /api/v1/contacts/contact/save/insight/{insight_id} to start enrichment

        Args:
            api_key: GetProspect API key.
            company_id: Optional company id to link; if not provided, attempts to read from attributes['getprospect']['raw'].
            filters: Optional filters payload to send to /insights/search; if not provided, tries attributes['getprospect']['raw'].
            timeout: request timeout in seconds.

        Returns:
            dict with keys: success (bool), error (str|None), userSearchId (str|None), response (dict|None)
        """
        import requests

        if not self.insight_id:
            return {"success": False, "error": "insight_id is required for GetProspect email request.", "response": None}
        if not api_key:
            return {"success": False, "error": "API key is required.", "response": None}

        # mark request initiation
        self.gp_requested_at = timezone.now()
        self.gp_email_status = "pending"
        self.save(update_fields=["gp_requested_at", "gp_email_status"])

        attrs = self.attributes or {}
        gp_raw = (attrs.get("getprospect") or {}).get("raw") or {}
        inferred_company_id = None
        try:
            companies = gp_raw.get("companies") or []
            if companies and isinstance(companies[0], dict):
                inferred_company_id = companies[0].get("company", {}).get("id") or companies[0].get("company", {}).get("_id")
        except Exception:
            inferred_company_id = None

        effective_company_id = company_id or inferred_company_id
        if not effective_company_id:
            return {"success": False, "error": "company_id is required (not found in attributes).", "response": None}

        # Build filters payload
        search_filters = filters or (attrs.get("getprospect") or {}).get("filters") or {}
        if not search_filters:
            # minimal fallback: email status all + optional company/domain hints
            fltrs = [
                {"property": "email", "included": {"operator": "EMAIL_STATUS", "value": ["all"]}}
            ]
            if self.company and self.company.domain:
                fltrs.append(
                    {"property": "company.domain", "included": {"operator": "EQUALS", "value": [self.company.domain]}}
                )
            elif self.company and self.company.name:
                fltrs.append(
                    {"property": "company.name", "included": {"operator": "CONTAINS", "value": [self.company.name]}, "excluded": {"value": [], "operator": "NOT_CONTAINS"}, "checkboxes": []}
                )
            search_filters = {
                "filters": fltrs,
                "kind": "user_search",
                "source": "contact",
            }
        else:
            # ensure required fields for insights/search
            search_filters.setdefault("kind", "user_search")
            search_filters.setdefault("source", "contact")

        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json;charset=UTF-8",
            "apiKey": api_key,
        }

        # Step 1: log user_search to obtain userSearchId
        try:
            resp_search = requests.post(
                "https://api.getprospect.com/api/v1/insights/search",
                headers=headers,
                json=search_filters,
                timeout=timeout,
            )
            resp_search.raise_for_status()
            search_json = resp_search.json()
            user_search_id = search_json.get("_id")
        except Exception as exc:
            detail = None
            try:
                detail = resp_search.text[:500] if 'resp_search' in locals() else None
            except Exception:
                detail = None
            return {
                "success": False,
                "error": f"insights/search failed: {exc}",
                "response": detail,
            }

        if not user_search_id:
            return {"success": False, "error": "insights/search did not return _id", "response": search_json}

        # Step 2: save contact to start enrichment
        save_body = {
            "listIds": [],
            "relations": [{"company": effective_company_id}],
            "userSearchId": user_search_id,
        }
        try:
            resp_save = requests.post(
                f"https://api.getprospect.com/api/v1/contacts/contact/save/insight/{self.insight_id}",
                headers=headers,
                json=save_body,
                timeout=timeout,
            )
            resp_save.raise_for_status()
            save_json = resp_save.json()
        except Exception as exc:
            detail = None
            try:
                detail = resp_save.text[:500] if 'resp_save' in locals() else None
            except Exception:
                detail = None
            return {"success": False, "error": f"contact/save failed: {exc}", "response": detail}

        # Optionally cache userSearchId for later polling
        attrs.setdefault("getprospect", {})
        attrs["getprospect"]["user_search_id"] = user_search_id
        attrs["getprospect"]["last_save_response"] = save_json
        self.attributes = attrs
        # Mark that we just checked/triggered a request
        self.gp_requested_at = timezone.now()
        self.gp_email_status = "pending"
        self.save(update_fields=["attributes", "gp_requested_at", "gp_email_status"])

        return {"success": True, "error": None, "userSearchId": user_search_id, "response": save_json}

    def refresh_getprospect_verification(self, api_key: str | None = None, timeout: int = 10) -> dict:
        """
        Refresh the stored GetProspect verification status for this contact's email.

        WARNING: this endpoint consumes GetProspect verification credits. Avoid calling it repeatedly.
        """
        import requests
        from django.conf import settings

        api_key = api_key or getattr(settings, "GETPROSPECT_API_KEY", None)
        if not api_key:
            return {"success": False, "error": "GETPROSPECT_API_KEY is not configured."}

        email = (self.email or "").strip()
        if not email:
            return {"success": False, "error": "Contact has no email to verify."}

        url = "https://api.getprospect.com/public/v1/email/verify"
        headers = {
            "accept": "application/json",
            "apiKey": api_key,
        }
        params = {"email": email}
        response = None
        try:
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            detail = None
            try:
                detail = response.text[:500] if response is not None else None
            except Exception:
                detail = None
            return {"success": False, "error": str(exc), "response": detail}

        status_value = payload.get("status")
        update_fields = []
        if status_value:
            self.gp_email_status = status_value
            update_fields.append("gp_email_status")
        self.gp_email_checked_at = timezone.now()
        update_fields.append("gp_email_checked_at")

        attrs = self.attributes or {}
        gp_attrs = attrs.setdefault("getprospect", {})
        gp_attrs["email_verification"] = payload
        self.attributes = attrs
        update_fields.append("attributes")
        self.save(update_fields=update_fields)
        return {"success": True, "status": status_value, "response": payload}


class MailingList(TimeStamped):
    """Named mailing lists that contacts can subscribe to."""

    name = models.CharField(_('Name'), max_length=255, unique=True)
    public_name = models.CharField(
        _('Public name'),
        max_length=255,
        help_text=_('Name shown on public subscription pages.')
    )
    slug = models.SlugField(
        _('Slug'),
        max_length=255,
        unique=True,
        validators=[validate_slug],
        help_text=_('URL-friendly identifier for public subscription management.')
    )
    description = models.TextField(_('Description'), blank=True)

    class Meta:
        ordering = ('name',)

    def __str__(self) -> str:
        return self.name


class Subscription(TimeStamped):
    """
    Links a contact to a mailing list and tracks subscription state.
    """

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='subscriptions')
    mailing_list = models.ForeignKey(MailingList, on_delete=models.CASCADE, related_name='subscriptions')
    subscribed_at = models.DateTimeField(_('Subscribed at'), auto_now_add=True)
    unsubscribed_at = models.DateTimeField(_('Unsubscribed at'), null=True, blank=True)
    unsubscribe_feedback = models.TextField(_('Unsubscribe feedback'), blank=True)

    class Meta:
        unique_together = ('contact', 'mailing_list')
        ordering = ('-subscribed_at',)

    def __str__(self) -> str:
        return f"{self.contact} -> {self.mailing_list}"

    @property
    def is_active(self) -> bool:
        return self.unsubscribed_at is None

    def mark_unsubscribed(self, feedback: str | None = None) -> None:
        """
        Convenience helper to record an unsubscribe event with optional feedback.
        """
        self.unsubscribed_at = timezone.now()
        if feedback:
            self.unsubscribe_feedback = feedback
        self.save(update_fields=['unsubscribed_at', 'unsubscribe_feedback', 'updated_at'])


class UnsubscribeAll(TimeStamped):
    """
    Records a global opt-out for a contact.
    """

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='unsubscribe_all_entries')
    communication = models.ForeignKey(
        'unicrm.Communication',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unsubscribe_events'
    )
    message = models.ForeignKey(
        'unicom.Message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unsubscribe_events'
    )
    unsubscribed_at = models.DateTimeField(_('Unsubscribed at'), default=timezone.now)
    feedback = models.TextField(_('Feedback'), blank=True)

    class Meta:
        ordering = ('-unsubscribed_at',)

    def __str__(self) -> str:
        return f"{self.contact} unsubscribed at {self.unsubscribed_at}"


class Segment(TimeStamped):
    """
    Defines a dynamic collection of contacts via a stored Python snippet.
    The snippet must declare a function named `apply` that accepts a QuerySet.
    """

    name = models.CharField(_('Name'), max_length=255, unique=True)
    description = models.TextField(_('Description'), blank=True)
    for_followup = models.BooleanField(
        _('Requires previous communication'),
        default=False,
        help_text=_('Auto-detected flag when the segment uses `previous_comm` in its code.'),
    )
    code = models.TextField(
        _('Filter code'),
        default=_default_segment_code,
        help_text=_(
            'Python snippet with a function `apply(qs)` returning a filtered QuerySet. '
            'The `qs` argument contains `unicrm.Contact` records.'
        )
    )

    class Meta:
        ordering = ('name',)

    def __str__(self) -> str:
        try:
            qs = self.apply()
            count = qs.count()
            return f"{self.name} ({count} contacts)"
        except Exception as exc:  # pragma: no cover - defensive
            return f"{self.name} [error: {exc}]"

    def get_callable(self) -> Callable[[QuerySet], QuerySet]:
        """
        Returns the compiled `apply` function for this segment.
        """
        if not hasattr(self, '_compiled_callable'):
            extras = {
                'timezone': timezone,
                'Contact': Contact,
                'Company': Company,
                'QuerySet': QuerySet,
                'previous_comm': None,
            }
            self._compiled_callable = compile_callable(self.code, 'apply', extras)
        return self._compiled_callable  # type: ignore[attr-defined]

    def _detect_for_followup(self) -> bool:
        """
        Determines if the segment code references `previous_comm` by inspecting the compiled bytecode.
        """
        source = self.code or ''
        try:
            compiled = compile(source, '<segment>', 'exec')
        except Exception:
            return False

        def _uses_previous(code_obj: types.CodeType) -> bool:
            target = 'previous_comm'
            if target in code_obj.co_names or target in code_obj.co_freevars or target in code_obj.co_varnames:
                return True
            for const in code_obj.co_consts:
                if isinstance(const, types.CodeType) and _uses_previous(const):
                    return True
            return False

        return _uses_previous(compiled)

    def save(self, *args, **kwargs):
        try:
            self.for_followup = self._detect_for_followup()
        except Exception:
            # Be defensive; do not block save on detection errors.
            pass
        super().save(*args, **kwargs)

    def apply(self, qs: QuerySet | None = None, previous_comm=None) -> QuerySet:
        """
        Applies the stored filter function to the provided QuerySet (or all contacts).
        """
        base_qs = qs or Contact.objects.all()
        func = self.get_callable()

        # Try to provide previous_comm via keyword argument when supported; otherwise inject into globals.
        injected = False
        original_value = None
        if previous_comm is not None:
            globals_dict = func.__globals__  # type: ignore[attr-defined]
            injected = True
            original_value = globals_dict.get('previous_comm', None)
            globals_dict['previous_comm'] = previous_comm

        try:
            try:
                return func(base_qs, previous_comm=previous_comm)
            except TypeError:
                return func(base_qs)
        finally:
            if injected:
                globals_dict = func.__globals__  # type: ignore[attr-defined]
                if original_value is None and 'previous_comm' in globals_dict:
                    globals_dict.pop('previous_comm', None)
                else:
                    globals_dict['previous_comm'] = original_value

    def sample_contacts(self, limit: int = 10) -> Sequence[Contact]:
        """
        Returns a limited list of contacts belonging to this segment for previews.
        """
        try:
            return list(self.apply().select_related('company').order_by('pk')[:limit])
        except Exception:
            return []


class TemplateVariable(TimeStamped):
    """
    Describes a template placeholder and how to compute its value for a contact.
    """

    key = models.CharField(
        _('Key'),
        max_length=100,
        unique=True,
        help_text=_('Slug-like identifier used in templates, e.g. "contact_first_name".')
    )
    label = models.CharField(
        _('Label'),
        max_length=255,
        help_text=_('Human-readable label for editors.')
    )
    description = models.TextField(
        _('Description'),
        help_text=_('Explain exactly what data this variable returns.')
    )
    code = models.TextField(
        _('Code'),
        default=_default_template_variable_code,
        help_text=_(
            'Python snippet defining `compute(contact)` which returns a string value.'
        )
    )
    is_active = models.BooleanField(_('Is active'), default=True)

    class Meta:
        ordering = ('key',)

    def __str__(self) -> str:
        values = self.sample_values(limit=3)
        preview = ', '.join(values) if values else 'no sample'
        return f"{self.label} [{self.key}] -> {preview}"

    def get_callable(self) -> Callable[[Contact], object]:
        """
        Compiles and returns the `compute` function described by this variable.
        """
        if not hasattr(self, '_compiled_callable'):
            try:
                from unicrm.services.unsubscribe_links import build_unsubscribe_link
            except Exception:  # pragma: no cover - defensive
                build_unsubscribe_link = None  # type: ignore
            extras = {
                'timezone': timezone,
                'Contact': Contact,
                'Company': Company,
                'build_unsubscribe_link': build_unsubscribe_link,
            }
            self._compiled_callable = compile_callable(self.code, 'compute', extras)
        return self._compiled_callable  # type: ignore[attr-defined]

    def sample_values(self, limit: int = 3) -> list[str]:
        """
        Returns preview values for the first few contacts to aid editors.
        """
        contacts = Contact.objects.order_by('pk')[:limit]
        values: list[str] = []
        func = None
        try:
            func = self.get_callable()
        except Exception as exc:  # pragma: no cover - defensive
            return [f"<error: {exc}>"]
        for contact in contacts:
            try:
                value = func(contact)
            except Exception as exc:  # pragma: no cover - defensive
                value = f"<error: {exc}>"
            values.append(str(value))
        return values


class Communication(TimeStamped):
    """
    Represents a planned outreach effort using rich HTML content and a segment of contacts.
    """

    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('scheduled', _('Scheduled')),
        ('sending', _('Sending')),
        ('completed', _('Completed')),
        ('ongoing', _('Ongoing')),
        ('cancelled', _('Cancelled')),
    ]

    segment = models.ForeignKey(Segment, on_delete=models.PROTECT, related_name='communications')
    mailing_list = models.ForeignKey(
        'unicrm.MailingList',
        on_delete=models.PROTECT,
        related_name='communications',
        null=True,
        blank=True,
    )
    channel = models.ForeignKey(
        'unicom.Channel',
        on_delete=models.PROTECT,
        related_name='unicrm_communications',
        verbose_name=_('Channel'),
        help_text=_('Channel used to send this communication.'),
        null=True,
        blank=True,
    )
    initiated_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='initiated_communications'
    )
    scheduled_for = models.DateTimeField(_('Scheduled for'), null=True, blank=True)
    auto_enroll_new_contacts = models.BooleanField(
        _('Auto-enroll new contacts'),
        default=False,
        help_text=_(
            'Automatically prepare and send this communication to contacts who later join the segment.'
        )
    )
    subject_template = models.CharField(
        _('Subject template'),
        max_length=255,
        blank=True,
        help_text=_('Optional Jinja2 template used for the email subject line.')
    )
    content = models.TextField(
        _('Content'),
        blank=True,
        help_text=_('HTML content customised specifically for this communication.')
    )
    status = models.CharField(_('Status'), max_length=20, choices=STATUS_CHOICES, default='draft')
    status_summary = models.JSONField(
        _('Status summary'),
        default=dict,
        blank=True,
        help_text=_('Aggregated counters for linked messages (e.g. sent, opened, clicked, failed).')
    )
    follow_up_for = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='followups',
        help_text=_('Optional parent communication this one follows up on.'),
    )
    exclude_follow_up_siblings = models.BooleanField(
        _('Exclude contacts already in sibling follow-ups'),
        default=True,
        help_text=_(
            'When true and this communication follows up on another, omit contacts already '
            'targeted by other follow-ups of the same parent.'
        ),
    )
    skip_antispam_guards = models.BooleanField(
        _('Skip anti-spam guards'),
        default=False,
        help_text=_('Send even if cooldown/unengaged limits would normally skip this contact.'),
    )
    evergreen_refreshed_at = models.DateTimeField(
        _('Evergreen refreshed at'),
        null=True,
        blank=True,
        help_text=_('Last time evergreen auto-enrollment recomputed segment membership.')
    )

    class Meta:
        ordering = ('-created_at',)

    def __str__(self) -> str:
        title = self.display_title
        return f"{title} ({self.segment.name})"

    def get_renderable_content(self) -> str:
        """
        Returns the HTML content that should be rendered for this communication.
        """
        return self.content or ''

    @property
    def display_title(self) -> str:
        if self.subject_template:
            return self.subject_template
        if self.content:
            text = self.content.strip()
            return text[:60] + ('…' if len(text) > 60 else '')
        return f"Communication {self.pk or ''}".strip()

    def refresh_status_summary(self, commit: bool = True) -> dict[str, int]:
        """
        Aggregates delivery metrics and updates the communication status.
        """

        deliveries = self.messages.select_related('message')
        total = deliveries.count()
        failures = 0
        bounced = 0
        sent = 0
        opened = 0
        clicked = 0
        replied = 0
        unsubscribed = 0
        awaiting_dispatch = False
        has_started_sending = False
        unsub_path = getattr(settings, 'UNICRM_UNSUBSCRIBE_PATH', '/unicrm/unsubscribe/')

        for delivery in deliveries:
            metadata = delivery.metadata or {}
            meta_status = (metadata.get('status') or '').lower()

            # Use same priority-based logic as _delivery_bucket
            if delivery.has_received_reply:
                replied += 1
                continue

            status = meta_status or (delivery.status or '').lower()
            if not status:
                status = 'sent' if delivery.message_id else 'scheduled'

            if status == 'unsubscribed':
                unsubscribed += 1
                continue

            if status == 'bounced':
                bounced += 1
            elif status in {'failed', 'skipped'}:
                failures += 1
            elif status == 'sent':
                message = delivery.message
                if message:
                    links = []
                    try:
                        links = getattr(message, 'clicked_links', None) or []
                    except Exception:
                        links = []
                    if not links:
                        links = metadata.get('clicked_links') or []
                    if isinstance(links, str):
                        links = [links]

                    if getattr(message, 'bounced', False):
                        bounced += 1
                    elif getattr(message, 'link_clicked', False) or getattr(message, 'clicked_links', None):
                        filtered_links = [
                            (link or '')
                            for link in getattr(message, 'clicked_links', []) or links
                            if link and unsub_path not in link and 'unsubscribe' not in str(link).lower()
                        ]
                        if filtered_links:
                            clicked += 1
                        else:
                            sent += 1
                    elif getattr(message, 'opened', False) or getattr(message, 'seen', False):
                        opened += 1
                    else:
                        sent += 1
                    has_started_sending = True
                else:
                    sent += 1
            else:
                awaiting_dispatch = True

            if delivery.message_id:
                has_started_sending = True

        totals = {
            'total': total,
            'failed': failures,
            'sent': sent,
            'opened': opened,
            'clicked': clicked,
            'bounced': bounced,
            'replied': replied,
            'unsubscribed': unsubscribed,
        }

        new_status = self.status
        if self.status != 'cancelled':
            if totals['total'] == 0:
                if self.status in {'scheduled', 'sending', 'ongoing'}:
                    new_status = self.status
                elif self.scheduled_for:
                    new_status = 'scheduled'
                else:
                    new_status = 'draft'
            elif awaiting_dispatch:
                if has_started_sending:
                    new_status = 'sending'
                else:
                    new_status = 'scheduled'
            else:
                new_status = 'ongoing' if self.auto_enroll_new_contacts else 'completed'

        updates = {}
        if self.status_summary != totals:
            self.status_summary = totals
            updates['status_summary'] = totals
        if new_status != self.status:
            self.status = new_status
            updates['status'] = new_status

        if updates and commit:
            self.save(update_fields=list(updates.keys()) + ['updated_at'])

        return totals


class CommunicationMessage(TimeStamped):
    """
    Associates a unicom Message with a communication and contact for aggregation.
    """
    STATUS_CHOICES = [
        ('scheduled', _('Scheduled')),
        ('sent', _('Sent')),
        ('failed', _('Failed')),
        ('bounced', _('Bounced')),
        ('skipped', _('Skipped')),
    ]

    communication = models.ForeignKey(
        Communication,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name='communications'
    )

    message = models.ForeignKey(
        'unicom.Message',
        on_delete=models.CASCADE,
        related_name='unicrm_links',
        null=True,
        blank=True
    )
    metadata = models.JSONField(_('Metadata'), default=dict, blank=True)
    status = models.CharField(_('Status'), max_length=20, choices=STATUS_CHOICES, default='scheduled')
    scheduled_at = models.DateTimeField(_('Scheduled at'), null=True, blank=True)
    has_received_reply = models.BooleanField(
        _('Has received reply'),
        default=False,
        help_text=_('True when the recipient sent a reply in the linked chat/email thread.'),
    )
    replied_at = models.DateTimeField(
        _('Replied at'),
        null=True,
        blank=True,
        help_text=_('Timestamp of the most recent reply detected for this delivery.'),
    )

    class Meta:
        unique_together = ('communication', 'contact')
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('status', 'scheduled_at')),
            models.Index(fields=('has_received_reply',)),
        ]

    def __str__(self) -> str:
        return f"{self.communication} -> {self.contact}"

    def message_status(self) -> str:
        """
        Derives a coarse status based on stored metadata and message state.
        """
        status_value = (self.status or '').lower()
        metadata_status = (self.metadata or {}).get('status')
        if not status_value and metadata_status:
            status_value = str(metadata_status).lower()

        if self.has_received_reply:
            return 'replied'

        if status_value in {'bounced', 'failed', 'sent', 'scheduled', 'skipped'}:
            return status_value

        msg = self.message
        if not msg:
            return 'scheduled'
        if getattr(msg, 'bounced', False):
            return 'bounced'
        if getattr(msg, 'seen', False) or getattr(msg, 'opened', False):
            return 'seen'
        if getattr(msg, 'sent', False):
            return 'sent'
        return 'scheduled'
