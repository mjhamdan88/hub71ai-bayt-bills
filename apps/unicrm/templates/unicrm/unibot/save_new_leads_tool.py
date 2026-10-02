from typing import Any, List

from unicrm.models import Contact, MailingList


def _normalize_insight_ids(raw_ids: Any) -> List[str]:
    """
    Accepts:
    - list of strings
    - comma/semicolon-separated string
    - JSON-like string of list
    Returns a cleaned list with duplicates removed (order preserved).
    """
    cleaned: List[str] = []
    seen = set()

    def _add(val: str):
        if not val:
            return
        if val in seen:
            return
        seen.add(val)
        cleaned.append(val)

    if isinstance(raw_ids, str):
        text = raw_ids.strip()
        # Try JSON-ish list string
        if text.startswith("[") and text.endswith("]"):
            text = text.strip("[]")
            parts = [p.strip().strip("\"'") for p in text.split(",")]
            for p in parts:
                _add(p)
        else:
            # split on common delimiters
            parts = [p.strip().strip("\"'") for p in text.replace(";", ",").split(",")]
            for p in parts:
                _add(p)
    elif isinstance(raw_ids, list):
        for item in raw_ids:
            if isinstance(item, str):
                _add(item.strip())
            else:
                _add(str(item).strip())
    else:
        _add(str(raw_ids).strip())

    return cleaned


def _format_name_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title() or slug


def save_new_leads(
    insight_ids: Any,
    mailing_list_slug: str,
    mailing_list_name: str = "",
    mailing_list_public_name: str = "",
    mailing_list_description: str = "",
) -> Any:
    """
    Add the provided contacts to a mailing list, then request missing emails from GetProspect.

    - Requires a mailing_list_slug; will create the list if it does not exist (optional name/public_name/description).
    - Only sends GetProspect requests for contacts without an email; existing emails incur no credit cost.
    - Shows a confirmation message detailing mailing list impact and expected credits before running.
    """
    clean_ids = _normalize_insight_ids(insight_ids)
    if not clean_ids:
        return {"success": False, "error": "No insight_ids provided."}

    slug = (mailing_list_slug or "").strip()
    if not slug:
        return {"success": False, "error": "mailing_list_slug is required."}

    contacts = list(Contact.objects.filter(insight_id__in=clean_ids).prefetch_related("subscriptions__mailing_list"))
    found_ids = {c.insight_id for c in contacts}
    missing = [iid for iid in clean_ids if iid not in found_ids]
    if missing:
        return {"success": False, "error": f"Missing contacts for insight_ids: {', '.join(missing)}"}

    mailing_list = MailingList.objects.filter(slug=slug).first()
    mailing_list_exists = mailing_list is not None
    mailing_list_label = mailing_list.name if mailing_list else (mailing_list_name or mailing_list_public_name or _format_name_from_slug(slug))
    mailing_list_public_label = mailing_list.public_name if mailing_list else (mailing_list_public_name or mailing_list_name or mailing_list_label)

    # Determine which contacts are already on the list vs will be added
    already_on_list = 0
    will_be_added = 0
    for c in contacts:
        if mailing_list:
            sub = next((s for s in c.subscriptions.all() if s.mailing_list_id == mailing_list.id and s.unsubscribed_at is None), None)
            if sub:
                already_on_list += 1
                continue
        will_be_added += 1

    # Mailing list counts
    current_active_count = mailing_list.subscriptions.filter(unsubscribed_at__isnull=True).count() if mailing_list else 0
    expected_total = current_active_count + will_be_added

    with_email = [c for c in contacts if c.email]
    missing_email = [c for c in contacts if not c.email]

    # Prepare preview text (first 10 contacts)
    preview_lines = []
    for c in contacts[:10]:
        role = c.job_title or (c.attributes or {}).get("job_title") or ""
        name = str(c)
        email_flag = "email on file" if c.email else "no email"
        preview_lines.append(f"- {name} ({role}) [{email_flag}]" if role else f"- {name} [{email_flag}]")

    summary_lines = [
        f"Confirm adding {len(clean_ids)} lead(s) to mailing list '{mailing_list_label}' (slug: {slug}).",
        f"Current active subscribers: {current_active_count}; after confirm: {expected_total} (+{will_be_added} new, {already_on_list} already on list).",
        f"Emails on file: {len(with_email)}; Missing emails: {len(missing_email)} (credits needed).",
    ]
    if mailing_list_description or (mailing_list and mailing_list.description):
        desc = mailing_list.description if mailing_list else mailing_list_description
        if desc:
            summary_lines.append(f"List description: {desc}")
    summary = "\n".join(summary_lines)
    if preview_lines:
        summary += "\n\nPreview (up to 10):\n" + "\n".join(preview_lines)

    # Cross-platform buttons with callback data
    message.reply_with(
        {
            "text": summary,
            "buttons": [
                [
                    {
                        "text": "✅ Confirm",
                        "type": "callback",
                        "callback_data": {
                            "tool": "save_new_leads",
                            "action": "confirm",
                            "insight_ids": clean_ids,
                            "mailing_list_slug": slug,
                            "mailing_list_name": mailing_list_name,
                            "mailing_list_public_name": mailing_list_public_name,
                            "mailing_list_description": mailing_list_description,
                        },
                    },
                    {
                        "text": "❌ Cancel",
                        "type": "callback",
                        "callback_data": {
                            "tool": "save_new_leads",
                            "action": "cancel",
                            "insight_ids": clean_ids,
                        },
                    },
                ]
            ],
        }
    )

    # Return None so the LLM waits for button response
    return None


tool_definition = {
    "name": "save_new_leads",
    "description": (
        "Add leads to a mailing list and request GetProspect emails for those missing email addresses. "
        "Charges one credit per lead without an email after user confirmation."
    ),
    "parameters": {
        "insight_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Insight IDs to save/request emails for. Accepts an array, a comma-separated string, or a JSON-like list string.",
        },
        "mailing_list_slug": {
            "type": "string",
            "description": "Slug of the mailing list to add these leads to (required). Will be created if it does not exist.",
        },
        "mailing_list_name": {
            "type": "string",
            "description": "Optional: internal name for a new mailing list (fallbacks to slug if omitted).",
        },
        "mailing_list_public_name": {
            "type": "string",
            "description": "Optional: public name for a new mailing list (fallbacks to name/slug if omitted).",
        },
        "mailing_list_description": {
            "type": "string",
            "description": "Optional: description for a new mailing list. Should ideally define the ICP of this list",
        },
    },
    "required": ["insight_ids", "mailing_list_slug"],
    "run": save_new_leads,
}
