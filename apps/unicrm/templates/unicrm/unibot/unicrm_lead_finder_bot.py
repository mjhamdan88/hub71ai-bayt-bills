from textwrap import dedent

from unicrm.models import MailingList

bot_tools = [
    "GPT Web Search",
    # "Email Validation",
    # "Company Domain Deduplicator",
    # "Company & Staff Import",
    "Lead Search",
    "Save New Leads",
]


def _mailing_list_summary(limit: int = 20) -> str:
    mailing_lists = list(MailingList.objects.order_by("name")[:limit])
    if not mailing_lists:
        return "No mailing lists exist yet. You can create one when calling save_new_leads."

    lines = []
    for ml in mailing_lists:
        active = ml.subscriptions.filter(unsubscribed_at__isnull=True).count()
        lines.append(f"- {ml.slug}: {ml.public_name or ml.name} (active subscribers: {active})")
    if len(mailing_lists) >= limit:
        lines.append("(limited view shown)")
    return "\n".join(lines)


def handle_incoming_message(message, bot, tools_list):
    mailing_list_context = _mailing_list_summary()
    system_instruction = dedent(
        f"""
        You are the Unicrm AI, you can help users with CRM related tasks.

        You can use the lead_search tool (GetProspect) to discover potential contacts and companies.

        Use the save_new_leads tool to add contacts to a mailing list and request emails from GetProspect (credits apply only to contacts without an email). Always provide a mailing_list_slug; the tool can create a list if needed.

        Available mailing lists (slug -> name and active subscribers):
        {mailing_list_context}

        Avoid making too many tool calls when there's no progress. Instead ask the user for advice while sharing what you're stuck with
        """
    ).strip()

    return bot.reply_using_llm(
        message,
        tools_list,
        system_instruction=system_instruction,
        request=request
    )
