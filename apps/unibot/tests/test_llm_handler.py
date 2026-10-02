from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from unibot.services.llm_handler import run_llm_handler


class LlmHandlerOrderingTests(SimpleTestCase):
    @patch("unibot.services.llm_handler._request_was_superseded", return_value=False)
    @patch("unicom.services.llm.responses.create_response")
    @patch("unibot.services.llm_handler.build_openai_tools")
    def test_text_before_tool_call_is_persisted_before_tool_activity(
        self, build_tools, create, _superseded,
    ):
        events = []
        message = SimpleNamespace(
            media_type="text",
            as_llm_chat=lambda **_kwargs: [{"role": "user", "content": "help"}],
            reply_with=lambda reply: events.append(("reply", reply.copy())),
        )
        tool_call = SimpleNamespace(mark_active=lambda: events.append(("active", None)))
        request = SimpleNamespace(
            submit_tool_calls=lambda calls: events.append(("submit", calls)) or [tool_call],
        )
        create.return_value = SimpleNamespace(
            text="First, choose the scope.", content=[], response_id="response-1",
            tool_calls=[SimpleNamespace(call_id="call-1", name="ask", arguments={})],
        )
        build_tools.return_value = (
            [{"type": "function", "function": {"name": "ask"}}],
            {"ask": lambda: None},
            {"ask": []},
        )

        run_llm_handler(
            bot=SimpleNamespace(), message=message, tools_list=[], request=request,
            api_mode="responses", openai_client=SimpleNamespace(),
        )

        self.assertEqual([event[0] for event in events[:2]], ["reply", "submit"])
        self.assertEqual(events[0][1]["text"], "First, choose the scope.")
        self.assertEqual(
            events[0][1]["_message_raw"],
            {"assistant_phase": "tool_preamble"},
        )
