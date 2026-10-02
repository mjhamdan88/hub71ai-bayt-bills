from types import SimpleNamespace

from django.test import SimpleTestCase

from unicom.services.llm.responses import (
    _user_facing_error,
    chat_history_to_responses,
    chat_tools_to_responses,
    create_response,
)
from unicom.models.message import Message


class _ResponsesEndpoint:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self.result) if kwargs.get("stream") else self.result


class _Client:
    def __init__(self, result):
        self.responses = _ResponsesEndpoint(result)


class ResponsesAdapterTests(SimpleTestCase):
    def test_api_error_uses_human_message_instead_of_json_wrapper(self):
        error = RuntimeError("wrapped error")
        error.body = {"error": {"message": "No AI balance is available. Top up on Account Overview."}}
        self.assertEqual(
            _user_facing_error(error),
            "No AI balance is available. Top up on Account Overview.",
        )

    def test_message_default_still_uses_chat_completions_unchanged(self):
        calls = []

        class FakeMessage:
            media_type = "text"
            platform = "WebChat"

            def as_llm_chat(self, **_kwargs):
                return [{"role": "user", "content": "hello"}]

            def reply_with(self, reply):
                return reply

        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: (
                        calls.append(kwargs)
                        or SimpleNamespace(
                            choices=[SimpleNamespace(message=SimpleNamespace(content="legacy"))]
                        )
                    )
                )
            ),
            responses=SimpleNamespace(
                create=lambda **_kwargs: self.fail("Responses API must remain opt-in")
            ),
        )

        reply = Message.reply_using_llm(FakeMessage(), "legacy-model", openai_client=client)
        self.assertEqual(reply["text"], "legacy")
        self.assertEqual(calls[0]["messages"][0]["content"], "hello")

    def test_translates_persisted_function_call_history(self):
        instructions, items = chat_history_to_responses(
            [
                {"role": "system", "content": "Be concise"},
                {"role": "user", "content": "Look it up"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {"name": "lookup", "arguments": {"id": 7}},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": '{"ok": true}'},
            ]
        )
        self.assertEqual(instructions, "Be concise")
        self.assertEqual(items[1]["type"], "function_call")
        self.assertEqual(items[1]["call_id"], "call_1")
        self.assertEqual(items[2]["type"], "function_call_output")

    def test_converts_chat_image_blocks_to_responses_input_images(self):
        _instructions, items = chat_history_to_responses(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is this?"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,AAAA"},
                        },
                    ],
                }
            ]
        )
        self.assertEqual(items[0]["content"][0]["type"], "input_text")
        self.assertEqual(items[0]["content"][1]["type"], "input_image")
        self.assertEqual(
            items[0]["content"][1]["image_url"],
            "data:image/png;base64,AAAA",
        )

    def test_converts_structured_tool_image_output(self):
        _instructions, items = chat_history_to_responses([
            {
                "role": "tool",
                "tool_call_id": "call_image",
                "content": '{"_responses_content":[{"type":"input_image","image_url":"data:image/png;base64,AAAA"}]}',
            }
        ])
        self.assertEqual(items[0]["type"], "function_call_output")
        self.assertEqual(items[0]["output"][0]["type"], "input_image")

    def test_converts_unicom_wrapped_structured_tool_image_output(self):
        wrapped = str({
            "result": '{"path":"/photo.png","_responses_content":[{"type":"input_image","image_url":"data:image/png;base64,AAAA"}]}',
            "status": "SUCCESS",
        })
        _instructions, items = chat_history_to_responses([
            {"role": "tool", "tool_call_id": "call_image", "content": wrapped}
        ])
        self.assertEqual(items[0]["output"], [{
            "type": "input_image",
            "image_url": "data:image/png;base64,AAAA",
        }])

    def test_converts_chat_function_schema_without_mutating_source(self):
        source = [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Find an item",
                    "parameters": {"type": "object", "properties": {}},
                },
                "strict": True,
            }
        ]
        converted = chat_tools_to_responses(source)
        self.assertEqual(converted[0]["name"], "lookup")
        self.assertNotIn("function", converted[0])
        self.assertIn("function", source[0])

    def test_non_streaming_text_and_tool_calls_are_normalized(self):
        response = SimpleNamespace(
            id="resp_1",
            output_text="done",
            output=[
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "lookup",
                    "arguments": '{"id": 7}',
                }
            ],
            usage=SimpleNamespace(input_tokens=10, output_tokens=2),
        )
        client = _Client(response)
        result = create_response(
            client=client,
            model="test-model",
            messages=[{"role": "user", "content": "hello"}],
        )
        self.assertEqual(result.text, "done")
        self.assertEqual(result.tool_calls[0].arguments, {"id": 7})
        self.assertEqual(client.responses.calls[0]["input"][0]["role"], "user")
        self.assertNotIn("stream", client.responses.calls[0])

    def test_native_tools_and_generated_images_are_preserved(self):
        response = SimpleNamespace(
            id="resp_image",
            output_text="",
            output=[{"type": "image_generation_call", "result": "AAAA"}],
            usage=None,
        )
        client = _Client(response)
        result = create_response(
            client=client,
            model="test-model",
            messages=[{"role": "user", "content": "Draw a cat"}],
            native_tools=[{"type": "image_generation"}],
        )
        self.assertEqual(client.responses.calls[0]["tools"], [{"type": "image_generation"}])
        self.assertEqual(result.content[0]["type"], "image_url")
        self.assertEqual(result.content[0]["image_url"]["url"], "data:image/png;base64,AAAA")

    def test_streaming_emits_ordered_deltas_and_final_result(self):
        events = [
            {"type": "response.output_text.delta", "delta": "hel"},
            {"type": "response.output_text.delta", "delta": "lo"},
            {
                "type": "response.completed",
                "response": {"id": "resp_1", "output_text": "hello", "output": []},
            },
        ]
        client = _Client(events)
        published = []
        result = create_response(
            client=client,
            model="test-model",
            messages=[{"role": "user", "content": "hello"}],
            stream=True,
            event_sink=published.append,
            stream_id="stream_1",
        )
        self.assertEqual(result.text, "hello")
        deltas = [event for event in published if event["type"] == "response.text.delta"]
        self.assertEqual([event["sequence"] for event in deltas], [1, 2])
        self.assertEqual(published[0]["type"], "response.started")
        self.assertEqual(published[-1]["type"], "response.finished")

    def test_streaming_preserves_generated_image_from_completed_output_item(self):
        events = [
            {
                "type": "response.output_item.done",
                "item": {"type": "image_generation_call", "result": "AAAA"},
            },
            {
                "type": "response.completed",
                # The streaming completion summary does not repeat the image bytes.
                "response": {"id": "resp_image", "output_text": "", "output": []},
            },
        ]
        result = create_response(
            client=_Client(events),
            model="test-model",
            messages=[{"role": "user", "content": "Edit this image"}],
            stream=True,
            native_tools=[{"type": "image_generation"}],
        )
        self.assertEqual(result.content, [{
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,AAAA"},
        }])

    def test_stream_sink_failure_does_not_abort_durable_response(self):
        events = [
            {"type": "response.output_text.delta", "delta": "ok"},
            {"type": "response.completed", "response": {"output_text": "ok", "output": []}},
        ]

        def broken_sink(_event):
            raise RuntimeError("relay unavailable")

        result = create_response(
            client=_Client(events),
            model="test-model",
            messages=[{"role": "user", "content": "hello"}],
            stream=True,
            event_sink=broken_sink,
        )
        self.assertEqual(result.text, "ok")
