from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Iterable, Sequence

from django.apps import apps as django_apps
from django.core.exceptions import AppRegistryNotReady
from django.db import transaction

from .models import Segment


logger = logging.getLogger(__name__)
UNICRM_UNIBOT_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "unicrm" / "unibot"


@dataclass(frozen=True)
class SegmentSeed:
    """
    Encapsulates the metadata required to create a default Segment instance.
    """

    name: str
    description: str
    code: str


DEFAULT_SEGMENTS: Sequence[SegmentSeed] = (
    SegmentSeed(
        name="All Eligible",
        description="All contacts with email, excluding bounced and unsubscribe-all.",
        code="""\
def apply(qs):
    return qs.filter(
        email__isnull=False,
    ).exclude(
        email__exact='',
    ).exclude(
        email_bounced=True,
    ).exclude(
        unsubscribe_all_entries__isnull=False,
    ).distinct()
""",
    ),
    SegmentSeed(
        name="All Contacts",
        description="All contacts that have an email address.",
        code="""\
def apply(qs):
    return qs.filter(
        email__isnull=False,
    ).exclude(
        email__exact='',
    ).distinct()
""",
    ),
    SegmentSeed(
        name="Staff Contacts",
        description="Staff-owned contacts that have an email address.",
        code="""\
def apply(qs):
    return qs.filter(
        owner__isnull=False,
        owner__is_staff=True,
        email__isnull=False,
    ).exclude(
        email__exact='',
    ).distinct()
""",
    ),
    SegmentSeed(
        name="Verified Users",
        description="Contacts linked to auth users with verified email addresses.",
        code="""\
def apply(qs):
    return qs.filter(
        attributes__auth_user_id__isnull=False,
        attributes__auth_user_email_verified=True,
        email__isnull=False,
    ).exclude(
        email__exact='',
    ).distinct()
""",
    ),
    SegmentSeed(
        name="Active Users",
        description="Contacts linked to active auth users with email addresses.",
        code="""\
def apply(qs):
    return qs.filter(
        user__isnull=False,
        user__is_active=True,
        email__isnull=False,
    ).exclude(
        email__exact='',
    ).distinct()
""",
    ),
    # Follow-up focused segments using `previous_comm`.
    SegmentSeed(
        name="Follow-up: Clicked link (6-12h window, morning send)",
        description="Contacts who clicked a link in the previous communication 6-12 hours ago (no reply/unsubscribe), last send was 24h+ ago, and follow-up is limited to morning hours (6-11am).",
        code="""\
from datetime import timedelta
from django.utils import timezone


def apply(qs, previous_comm=None):
    if previous_comm is None:
        return qs.none()

    now = timezone.now()
    click_gte = now - timedelta(hours=12)
    click_lte = now - timedelta(hours=2)
    last_send_lte = now - timedelta(hours=24)

    # Only allow morning sends to mimic "next morning" delivery.
    if not (6 <= now.hour <= 11):
        return qs.none()

    return qs.filter(
        communications__communication=previous_comm,
        communications__has_received_reply=False,
        communications__message__bounced=False,
        communications__message__opened=True,
        communications__message__link_clicked=True,
        communications__message__time_link_clicked__gte=click_gte,
        communications__message__time_link_clicked__lte=click_lte,
        communications__message__timestamp__lte=last_send_lte,
    ).exclude(
        communications__metadata__status__iexact='unsubscribed',
    ).distinct()
""",
    ),
    SegmentSeed(
        name="Follow-up: Clicked/Open 24h+ (weekday mornings)",
        description="Contacts who clicked or opened 24h+ ago (no reply/unsubscribe), last send was 24h+ ago, and follow-up is limited to weekday mornings (6-11am).",
        code="""\
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q


def apply(qs, previous_comm=None):
    if previous_comm is None:
        return qs.none()

    now = timezone.now()
    cutoff = now - timedelta(hours=24)

    if now.weekday() >= 5 or not (6 <= now.hour <= 11):
        return qs.none()

    return qs.filter(
        communications__communication=previous_comm,
        communications__has_received_reply=False,
        communications__message__bounced=False,
        communications__message__timestamp__lte=cutoff,
    ).filter(
        Q(
            communications__message__link_clicked=True,
            communications__message__time_link_clicked__lte=cutoff,
        )
        | Q(
            communications__message__opened=True,
            communications__message__time_opened__lte=cutoff,
        )
    ).exclude(
        communications__metadata__status__iexact='unsubscribed',
    ).distinct()
""",
    ),
    SegmentSeed(
        name="Follow-up: Clicked more than 24h ago",
        description="Contacts who clicked a link 24h+ ago, no reply/unsubscribe, and last send was at least 24h ago.",
        code="""\
from datetime import timedelta
from django.utils import timezone


def apply(qs, previous_comm=None):
    if previous_comm is None:
        return qs.none()

    now = timezone.now()
    cutoff = now - timedelta(hours=24)

    return qs.filter(
        communications__communication=previous_comm,
        communications__has_received_reply=False,
        communications__message__bounced=False,
        communications__message__link_clicked=True,
        communications__message__time_link_clicked__lte=cutoff,
        communications__message__timestamp__lte=cutoff,
    ).exclude(
        communications__metadata__status__iexact='unsubscribed',
    ).distinct()
""",
    ),
    SegmentSeed(
        name="Follow-up: Clicked or opened more than 24h ago",
        description="Contacts who clicked or opened 24h+ ago (no reply/unsubscribe) and last send was 24h+ ago.",
        code="""\
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q


def apply(qs, previous_comm=None):
    if previous_comm is None:
        return qs.none()

    now = timezone.now()
    cutoff = now - timedelta(hours=24)

    return qs.filter(
        communications__communication=previous_comm,
        communications__has_received_reply=False,
        communications__message__bounced=False,
        communications__message__timestamp__lte=cutoff,
    ).filter(
        Q(
            communications__message__link_clicked=True,
            communications__message__time_link_clicked__lte=cutoff,
        )
        | Q(
            communications__message__opened=True,
            communications__message__time_opened__lte=cutoff,
        )
    ).exclude(
        communications__metadata__status__iexact='unsubscribed',
    ).distinct()
""",
    ),
    SegmentSeed(
        name="Follow-up: All recipients (interaction-aware timing)",
        description="Every contact targeted by the previous communication who hasn’t replied or unsubscribed, with interactions eligible after 24h and passive contacts after 48h.",
        code="""\
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q


def apply(qs, previous_comm=None):
    if previous_comm is None:
        return qs.none()

    now = timezone.now()
    interacted_cutoff = now - timedelta(hours=24)
    passive_cutoff = now - timedelta(hours=48)

    return qs.filter(
        communications__communication=previous_comm,
        communications__has_received_reply=False,
        communications__message__bounced=False,
    ).filter(
        Q(
            communications__message__timestamp__lte=interacted_cutoff,
            communications__message__link_clicked=True,
        )
        | Q(
            communications__message__timestamp__lte=interacted_cutoff,
            communications__message__opened=True,
        )
        | Q(
            communications__message__timestamp__lte=passive_cutoff,
            communications__message__link_clicked=False,
            communications__message__opened=False,
        )
    ).exclude(
        communications__metadata__status__iexact='unsubscribed',
    ).distinct()
""",
    ),
    SegmentSeed(
        name="Follow-up: Multiple opens (no click/reply)",
        description="Contacts who opened the previous email 2+ times, last open 2h+ ago, no clicks/replies, and last send 24h+ ago.",
        code="""\
from datetime import timedelta
from django.utils import timezone


def apply(qs, previous_comm=None):
    if previous_comm is None:
        return qs.none()

    now = timezone.now()
    last_open_lte = now - timedelta(hours=2)
    last_send_lte = now - timedelta(hours=24)

    return qs.filter(
        communications__communication=previous_comm,
        communications__has_received_reply=False,
        communications__message__bounced=False,
        communications__message__link_clicked=False,
        communications__message__open_count__gte=2,
        communications__message__time_opened__lte=last_open_lte,
        communications__message__timestamp__lte=last_send_lte,
    ).exclude(
        communications__metadata__status__iexact='unsubscribed',
    ).distinct()
""",
    ),
    SegmentSeed(
        name="Follow-up: Opened once, no click/reply (24h+)",
        description="Contacts who opened once at least 24h ago and have no clicks/replies/unsubscribe.",
        code="""\
from datetime import timedelta
from django.utils import timezone


def apply(qs, previous_comm=None):
    if previous_comm is None:
        return qs.none()

    now = timezone.now()
    first_open_lte = now - timedelta(hours=24)
    last_send_lte = now - timedelta(hours=24)

    return qs.filter(
        communications__communication=previous_comm,
        communications__has_received_reply=False,
        communications__message__bounced=False,
        communications__message__opened=True,
        communications__message__link_clicked=False,
        communications__message__time_opened__lte=first_open_lte,
        communications__message__timestamp__lte=last_send_lte,
    ).exclude(
        communications__metadata__status__iexact='unsubscribed',
    ).distinct()
""",
    ),
    SegmentSeed(
        name="Follow-up: Never opened (48h+)",
        description="Contacts who received the previous email 48h+ ago and have zero opens/clicks/replies.",
        code="""\
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q


def apply(qs, previous_comm=None):
    if previous_comm is None:
        return qs.none()

    now = timezone.now()
    sent_lte = now - timedelta(hours=48)

    return qs.filter(
        communications__communication=previous_comm,
        communications__has_received_reply=False,
        communications__message__bounced=False,
        communications__message__opened=False,
        communications__message__link_clicked=False,
        communications__message__timestamp__lte=sent_lte,
    ).exclude(
        communications__metadata__status__iexact='unsubscribed',
    ).distinct()
""",
    ),
    SegmentSeed(
        name="Follow-up: Cold reopen (high-interest)",
        description="Contacts who reopened after being cold for several days; last open 6-12h ago, sent 3d+ ago, and no clicks/replies.",
        code="""\
from datetime import timedelta
from django.utils import timezone
from django.db.models import F


def apply(qs, previous_comm=None):
    if previous_comm is None:
        return qs.none()

    now = timezone.now()
    reopen_gte = now - timedelta(hours=12)
    reopen_lte = now - timedelta(hours=6)
    sent_lte = now - timedelta(days=3)

    return qs.filter(
        communications__communication=previous_comm,
        communications__has_received_reply=False,
        communications__message__bounced=False,
        communications__message__opened=True,
        communications__message__link_clicked=False,
        communications__message__time_opened__gte=reopen_gte,
        communications__message__time_opened__lte=reopen_lte,
        communications__message__timestamp__lte=sent_lte,
        communications__message__time_opened__gte=F('communications__message__timestamp') + timedelta(days=3),
    ).exclude(
        communications__metadata__status__iexact='unsubscribed',
    ).distinct()
""",
    ),
)

LEGACY_SEGMENTS_TO_REMOVE: Sequence[str] = (
    "Verified Contacts",
)

LEGACY_SEGMENT_CODE_VARIANTS: dict[str, tuple[str, ...]] = {
    "All Contacts": (
        """\
def apply(qs):
    return qs.distinct()
""",
    ),
    "Staff Contacts": (
        """\
def apply(qs):
    return qs.filter(owner__isnull=False, owner__is_staff=True).distinct()
""",
    ),
}

LEGACY_SEGMENT_DESCRIPTIONS: dict[str, tuple[str, ...]] = {
    "All Contacts": (
        "Every contact stored in the CRM.",
    ),
    "Staff Contacts": (
        "Contacts owned by staff users.",
    ),
}


def ensure_default_segments(segment_seeds: Iterable[SegmentSeed] | None = None) -> list[Segment]:
    """
    Ensure that the default Segment records exist.

    Segments are only created when missing; an existing segment is preserved
    to avoid clobbering manual edits made by administrators.
    """

    seeds = tuple(segment_seeds) if segment_seeds is not None else DEFAULT_SEGMENTS
    created_segments: list[Segment] = []

    seed_names = {seed.name for seed in seeds}

    with transaction.atomic():
        if LEGACY_SEGMENTS_TO_REMOVE:
            Segment.objects.filter(name__in=LEGACY_SEGMENTS_TO_REMOVE).exclude(
                name__in=seed_names
            ).delete()

        for seed in seeds:
            segment, created = Segment.objects.get_or_create(
                name=seed.name,
                defaults={"description": seed.description, "code": seed.code},
            )
            if not created:
                fields_to_update: dict[str, str] = {}
                if segment.description != seed.description:
                    fields_to_update["description"] = seed.description
                if segment.code != seed.code:
                    fields_to_update["code"] = seed.code

                if fields_to_update:
                    for field, value in fields_to_update.items():
                        setattr(segment, field, value)
                    segment.save(update_fields=[*fields_to_update.keys(), "updated_at"])
            else:
                created_segments.append(segment)

    return created_segments


UNICRM_BOT_NAME = "Unicrm Lead Finder"
UNICRM_BOT_CATEGORY = "unicrm"
GPT_SEARCH_TEMPLATE = "gpt_search_tool.py"
EMAIL_VALIDATION_TEMPLATE = "validate_emails_tool.py"
COMPANY_DOMAIN_TEMPLATE = "company_domain_deduplicator_tool.py"
COMPANY_AND_STAFF_TEMPLATE = "company_and_staff_import_tool.py"
SEARCH_LEADS_TEMPLATE = "search_leads_tool.py"
LEAD_SEARCH_TEMPLATE = "lead_search_tool.py"
LEAD_SEARCH_V2_TEMPLATE = "lead_search_v2_tool.py"
SAVE_NEW_LEADS_TEMPLATE = "save_new_leads_tool.py"
UNICRM_LEAD_FINDER_BOT_TEMPLATE = "unicrm_lead_finder_bot.py"
BOTS_TOOL_NAMES = [
    "GPT Web Search",
    "Email Validation",
    "Company Domain Deduplicator",
    "Company & Staff Import",
    "Lead Search",
    "Save New Leads",
]




def _unibot_models_available() -> bool:
    if not django_apps.is_installed("unibot"):
        return False
    try:
        django_apps.get_model("unibot", "Bot")
        django_apps.get_model("unibot", "Tool")
    except (LookupError, AppRegistryNotReady):
        return False
    return True


def _load_unibot_template(filename: str) -> str:
    try:
        config = django_apps.get_app_config("unibot")
    except (LookupError, AppRegistryNotReady):
        return ""
    template_path = Path(config.path) / "templates" / "unibot" / filename
    try:
        return template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Unibot template %s was not found at %s", filename, template_path)
        return ""


def _load_unicrm_unibot_template(filename: str) -> str:
    template_path = UNICRM_UNIBOT_TEMPLATE_DIR / filename
    try:
        return template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Unicrm unibot template %s was not found at %s", filename, template_path)
        return ""


def _ensure_tool(tool_model, name: str, description: str, code: str):
    if not code:
        logger.debug("Skipping tool %s because no code was provided.", name)
        return None
    with transaction.atomic():
        # Lock by name to avoid races across multiple workers and dedupe existing rows
        existing = list(
            tool_model.objects.select_for_update().filter(name=name).order_by("id")
        )
        created = False
        if existing:
            tool = existing[0]
            # Remove accidental duplicates to keep get_or_create stable
            duplicates = existing[1:]
            if duplicates:
                tool_model.objects.filter(id__in=[t.id for t in duplicates]).delete()
        else:
            tool = tool_model.objects.create(
                name=name,
                description=description,
                code=code,
            )
            created = True
    updates: dict[str, str] = {}
    if not created:
        if (tool.description or "") != description:
            updates["description"] = description
        existing_code = (tool.code or "").strip()
        desired_code = code.strip()
        if existing_code != desired_code:
            updates["code"] = code
        if updates:
            for field, value in updates.items():
                setattr(tool, field, value)
            tool.save(update_fields=list(updates.keys()))
    return tool


def ensure_unicrm_bot_assets() -> bool:
    """
    Ensure the Unicrm lead finder bot plus its required tools exist when unibot is installed.
    """

    if not _unibot_models_available():
        return False

    Tool = django_apps.get_model("unibot", "Tool")
    Bot = django_apps.get_model("unibot", "Bot")

    tool_specs = [
        (
            "GPT Web Search",
            "Intelligent GPT-powered web search used for researching potential companies.",
            _load_unibot_template(GPT_SEARCH_TEMPLATE),
        ),
        (
            "Email Validation",
            "Validates email addresses through the Reacher service.",
            _load_unibot_template(EMAIL_VALIDATION_TEMPLATE),
        ),
        (
            "Company Domain Deduplicator",
            "Checks if company domains already exist before attempting to create new records.",
            _load_unicrm_unibot_template(COMPANY_DOMAIN_TEMPLATE),
        ),
        (
            "Company & Staff Import",
            "Atomically creates a new company plus its validated staff contacts.",
            _load_unicrm_unibot_template(COMPANY_AND_STAFF_TEMPLATE),
        ),
        (
            "Search Leads",
            "Find B2B contacts via GetProspect with filters for name, company, title, industry, and location.",
            _load_unicrm_unibot_template(SEARCH_LEADS_TEMPLATE),
        ),
        (
            "Lead Search",
            "Find B2B contacts via GetProspect using the unified service with full company/contact filters and insight IDs.",
            _load_unicrm_unibot_template(LEAD_SEARCH_TEMPLATE),
        ),
        (
            "Lead Search v2",
            "Find B2B contacts via GetProspect web-app endpoint with company filters; returns contact IDs for email lookup.",
            _load_unicrm_unibot_template(LEAD_SEARCH_V2_TEMPLATE),
        ),
        (
            "Save New Leads",
            "Request GetProspect emails by insight_id with user confirmation (one credit per lead).",
            _load_unicrm_unibot_template(SAVE_NEW_LEADS_TEMPLATE),
        ),
    ]

    tools = [
        _ensure_tool(Tool, name, description, code)
        for name, description, code in tool_specs
    ]
    tools = [tool for tool in tools if tool is not None]
    if not tools:
        return False

    bot_code = _load_unicrm_unibot_template(UNICRM_LEAD_FINDER_BOT_TEMPLATE)
    if not bot_code:
        return False

    bot, created = Bot.objects.get_or_create(
        name=UNICRM_BOT_NAME,
        defaults={
            "category": UNICRM_BOT_CATEGORY,
            "code": bot_code,
        },
    )
    updates: dict[str, str] = {}
    if not created:
        if bot.category != UNICRM_BOT_CATEGORY:
            updates["category"] = UNICRM_BOT_CATEGORY
        if (bot.code or "").strip() != bot_code.strip():
            updates["code"] = bot_code
        if updates:
            for field, value in updates.items():
                setattr(bot, field, value)
            bot.save(update_fields=list(updates.keys()))

    existing_tool_ids = set(bot.tools.values_list("id", flat=True))
    # Attach only the configured bot tools; keep other tools in the system unlinked
    desired_tools = [t for t in tools if t.name in BOTS_TOOL_NAMES]
    desired_ids = set(t.id for t in desired_tools)
    if existing_tool_ids != desired_ids:
        bot.tools.set(desired_tools)

    return True
