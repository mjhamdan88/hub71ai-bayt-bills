from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Mapping
import re
from urllib.parse import unquote

from django.utils import timezone
from django.db import IntegrityError
from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment


# Matches TinyMCE-protected placeholders such as "{{ variables.x }}" that TinyMCE wraps.
_PROTECTED_PLACEHOLDER_RE = re.compile(r'<!--\s*mce:protected\s+([^>]+?)-->')


def _datetime_format(value, fmt: str = "%Y-%m-%d %H:%M %Z") -> str:
    if not value:
        return ""
    if timezone.is_naive(value):  # pragma: no cover - defensive branch
        value = timezone.make_aware(value)
    return timezone.localtime(value).strftime(fmt)


@lru_cache(maxsize=1)
def get_jinja_environment() -> SandboxedEnvironment:
    """
    Returns a singleton sandboxed environment for rendering email templates.
    Shared between Unicom and Unicrm to keep behavior consistent.
    """
    env = SandboxedEnvironment(
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )
    env.filters['datetime'] = _datetime_format
    env.globals.update({
        'now': timezone.now,
    })
    return env


def unprotect_tinymce_markup(content: str | None) -> str:
    """
    Restore TinyMCE protected placeholders ({{ ... }}) back to plain Jinja markup.
    """
    if not content:
        return content or ''

    def _restore(match: re.Match[str]) -> str:
        encoded = match.group(1).strip()
        try:
            return unquote(encoded)
        except Exception:  # pragma: no cover - defensive
            return encoded

    return _PROTECTED_PLACEHOLDER_RE.sub(_restore, content)


@dataclass
class RenderResult:
    html: str
    context: Dict[str, Any]
    variables: Dict[str, Any]
    errors: list[str]


def render_template(
    template_html: str,
    *,
    base_context: Mapping[str, Any] | None = None,
    variables: Mapping[str, Any] | None = None,
    extra_context: Mapping[str, Any] | None = None,
) -> RenderResult:
    """
    Render arbitrary HTML with a sandboxed Jinja2 environment.

    - Does nothing destructive to callers: on template error, returns original HTML and records the error.
    - Callers can pass `variables` to expose as `variables.*` in templates; optional extra context merges in.
    """
    env = get_jinja_environment()
    rendered_context: Dict[str, Any] = {}
    if base_context:
        rendered_context.update(base_context)
    existing_vars = dict(rendered_context.get('variables') or {})
    existing_vars.update(variables or {})
    rendered_context['variables'] = existing_vars

    if extra_context:
        rendered_context.update(extra_context)

    template_html = unprotect_tinymce_markup(template_html)
    template = env.from_string(template_html)
    errors: list[str] = []
    try:
        html = template.render(rendered_context)
    except TemplateError as exc:
        errors.append(str(exc))
        html = template_html
    return RenderResult(
        html=html,
        context=rendered_context,
        variables=rendered_context['variables'],
        errors=errors,
    )


def build_unicom_message_context(
    *,
    params: Mapping[str, Any],
    channel: Mapping[str, Any] | None = None,
    user: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Construct a safe, serialisable context for Unicom standalone messages.
    Intentionally excludes CRM-only data (contacts, unsubscribe links).
    """
    message_ctx = {
        'subject': params.get('subject'),
        'text': params.get('text'),
        'html': params.get('html'),
        'to': params.get('to'),
        'cc': params.get('cc'),
        'bcc': params.get('bcc'),
        'attachments': params.get('attachments'),
        'chat_id': params.get('chat_id'),
        'reply_to_message_id': params.get('reply_to_message_id'),
        'timestamp': timezone.now(),
    }
    ctx: Dict[str, Any] = {
        'message': message_ctx,
        'channel': channel or {},
        'sender': user or {},
    }
    if extra:
        ctx.update(extra)
    return ctx


_VARIABLE_PLACEHOLDER_RE = re.compile(r"\{\{\s*variables\.([^\s\}]+)\s*\}\}")


def extract_variable_keys(template_html: str | None) -> set[str]:
    """
    Return the set of variable keys referenced as {{ variables.* }} in the template.
    """
    if not template_html:
        return set()
    unprotected = unprotect_tinymce_markup(template_html)
    return {m.group(1) for m in _VARIABLE_PLACEHOLDER_RE.finditer(unprotected)}


def _load_crm_models():
    """
    Dynamically load CRM models if unicrm is installed; otherwise return (None, None).
    """
    try:
        from django.apps import apps
        Contact = apps.get_model('unicrm', 'Contact')
        TemplateVariable = apps.get_model('unicrm', 'TemplateVariable')
        if Contact is None or TemplateVariable is None:
            return None, None
        return Contact, TemplateVariable
    except Exception:
        return None, None


def compute_crm_variables(keys: set[str], contact_email: str | None) -> Dict[str, Any]:
    """
    Best-effort evaluation of CRM TemplateVariables for a contact resolved by email.
    Safe to call when unicrm is not installed (returns {}).
    """
    if not keys or not contact_email:
        return {}
    Contact, TemplateVariable = _load_crm_models()
    if Contact is None or TemplateVariable is None:
        return {}
    contact = Contact.objects.filter(email__iexact=contact_email).first()
    if not contact:
        try:
            contact, _ = Contact.objects.get_or_create(
                email=contact_email,
                defaults={'email': contact_email},
            )
        except IntegrityError:
            contact = Contact.objects.filter(email__iexact=contact_email).first()
    if not contact:
        return {}
    results: Dict[str, Any] = {}
    for variable in TemplateVariable.objects.filter(is_active=True, key__in=keys):
        try:
            results[variable.key] = variable.get_callable()(contact)
        except Exception as exc:  # pragma: no cover - defensive
            results[variable.key] = f"<error: {exc}>"
    return results
