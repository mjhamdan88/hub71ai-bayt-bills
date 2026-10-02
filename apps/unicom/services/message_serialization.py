"""Canonical JSON serialization for Unicom messages."""

from unicom.services.tool_presentations import extract_tool_presentation


def serialize_message(message) -> dict:
    """Return the transport-neutral public representation of a Message."""
    raw = message.raw or {}
    tool_call = raw.get("tool_call", {}) if message.media_type == "tool_call" else {}
    tool_response = raw.get("tool_response", {}) if message.media_type == "tool_response" else {}
    tool_record = (
        message.tool_call_record.first()
        if message.media_type == "tool_call"
        else None
    )
    return {
        "id": message.pk,
        "text": message.text,
        "html": message.html,
        "is_outgoing": message.is_outgoing,
        "sender_name": message.sender_name,
        "timestamp": message.timestamp.isoformat(),
        "media_type": message.media_type,
        "media_url": message.media.url if message.media else None,
        "reply_to_message_id": message.reply_to_message_id,
        "interactive_buttons": raw.get("interactive_buttons"),
        "progress_updates_for_user": (
            tool_call.get("arguments", {}).get("progress_updates_for_user")
            if message.media_type == "tool_call"
            else None
        ),
        "tool_name": tool_call.get("name") or tool_response.get("tool_name"),
        "call_id": tool_call.get("id") or tool_response.get("call_id"),
        "tool_status": tool_record.status if tool_record else None,
        "result_status": (
            tool_response.get("result", {}).get("status")
            if isinstance(tool_response.get("result"), dict)
            else None
        ),
        "tool_presentation": (
            extract_tool_presentation(raw)
            if message.media_type == "tool_response"
            else None
        ),
    }
