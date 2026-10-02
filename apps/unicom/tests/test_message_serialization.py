from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils import timezone

from unicom.services.message_serialization import serialize_message


class _RelatedRecord:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class MessageSerializationTests(SimpleTestCase):
    def _message(self, *, media_type, raw, tool_status=None):
        return SimpleNamespace(
            pk="message-1",
            text="Tool",
            html="",
            is_outgoing=None,
            sender_name="System",
            timestamp=timezone.now(),
            media_type=media_type,
            media=None,
            reply_to_message_id="parent-1",
            raw=raw,
            tool_call_record=_RelatedRecord(
                SimpleNamespace(status=tool_status) if tool_status else None
            ),
        )

    def test_tool_call_includes_canonical_terminal_status(self):
        payload = serialize_message(self._message(
            media_type="tool_call",
            tool_status="INTERRUPTED",
            raw={"tool_call": {
                "id": "call-1",
                "name": "example",
                "arguments": {"progress_updates_for_user": "Working"},
            }},
        ))

        self.assertEqual(payload["call_id"], "call-1")
        self.assertEqual(payload["tool_name"], "example")
        self.assertEqual(payload["tool_status"], "INTERRUPTED")
        self.assertEqual(payload["progress_updates_for_user"], "Working")

    def test_tool_response_includes_result_status(self):
        payload = serialize_message(self._message(
            media_type="tool_response",
            raw={"tool_response": {
                "call_id": "call-1",
                "tool_name": "example",
                "result": {"status": "ERROR", "error": "Interrupted"},
            }},
        ))

        self.assertEqual(payload["call_id"], "call-1")
        self.assertEqual(payload["result_status"], "ERROR")
        self.assertIsNone(payload["tool_status"])
