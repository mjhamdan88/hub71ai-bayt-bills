import uuid
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from unicom.models import Account, Channel, Chat, Message, Request, ToolCall
from unicom.services.llm.tool_calls import save_tool_call


class ToolCallBatchTests(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(
            name="batch-tests", platform="WebChat", config={}
        )
        self.account = Account.objects.create(
            id="batch-user", channel=self.channel, platform="WebChat", raw={}
        )
        self.chat = Chat.objects.create(
            id="batch-chat", channel=self.channel, platform="WebChat"
        )
        self.message = self._user_message("Run both")
        self.request = Request.objects.create(
            message=self.message,
            account=self.account,
            channel=self.channel,
        )

    def _user_message(self, text):
        return Message.objects.create(
            id=f"message-{uuid.uuid4()}",
            channel=self.channel,
            platform="WebChat",
            sender=self.account,
            chat=self.chat,
            is_outgoing=False,
            sender_name="User",
            text=text,
            timestamp=timezone.now(),
            raw={"skip_request_creation": True},
        )

    def _tool_call(self, suffix, *, status="ACTIVE"):
        call_id = f"call-{suffix}"
        call_message = save_tool_call(
            self.chat, "test_tool", {}, call_id=call_id,
            reply_to_message=self.message,
        )
        return ToolCall.objects.create(
            call_id=call_id,
            tool_name="test_tool",
            arguments={},
            status=status,
            request=self.request,
            tool_call_message=call_message,
            initial_user_message=self.message,
        )

    @patch.object(Request, "categorize")
    @patch.object(Request, "identify_member")
    def test_parallel_batch_continues_once_after_all_calls_respond(
        self, _identify_member, _categorize
    ):
        first = self._tool_call("first")
        second = self._tool_call("second")

        _message, continuation = first.respond({"result": "first"})
        self.assertIsNone(continuation)

        _message, continuation = second.respond({"result": "second"})
        self.assertIsNotNone(continuation)
        self.assertEqual(self.request.child_requests.count(), 1)
        context = continuation.message.as_llm_chat(mode="thread", multimodal=False)
        self.assertEqual(
            [item["role"] for item in context],
            ["user", "assistant", "tool", "assistant", "tool"],
        )
        self.assertEqual(
            [
                item["tool_calls"][0]["id"]
                for item in context if item.get("tool_calls")
            ],
            [first.call_id, second.call_id],
        )
        tool_contents = [item["content"] for item in context if item["role"] == "tool"]
        self.assertIn("first", tool_contents[0])
        self.assertIn("second", tool_contents[1])

    def test_newer_user_message_suppresses_late_tool_response(self):
        tool_call = self._tool_call("late")
        self._user_message("Stop")

        response_message, continuation = tool_call.respond({"result": "late"})

        self.assertIsNone(response_message)
        self.assertIsNone(continuation)
        tool_call.refresh_from_db()
        self.assertEqual(tool_call.status, "INTERRUPTED")
        self.assertEqual(tool_call.response_messages.count(), 1)
        self.assertEqual(tool_call.response_messages.get().raw["tool_response"]["result"]["status"], "ERROR")
        self.assertEqual(self.request.child_requests.count(), 0)

    @patch.object(Request, "categorize")
    @patch.object(Request, "identify_member")
    def test_later_user_turn_retains_every_parallel_sibling(
        self, _identify_member, _categorize
    ):
        first = self._tool_call("first")
        second = self._tool_call("second")
        first.respond({"device": "alpine"})
        _response, continuation = second.respond({"device": "ubuntu"})
        assistant = continuation.message.reply_with({"type": "text", "text": "Both done"})
        later_user = self._user_message("What happened?")
        later_user.reply_to_message = assistant
        later_user.save(update_fields=["reply_to_message"])
        Request.objects.create(
            message=later_user, account=self.account, channel=self.channel,
        )

        context = later_user.as_llm_chat(mode="thread", multimodal=False)

        call_ids = [
            item["tool_calls"][0]["id"] for item in context
            if item.get("tool_calls")
        ]
        self.assertEqual(call_ids, [first.call_id, second.call_id])
        self.assertEqual(
            [item["tool_call_id"] for item in context if item["role"] == "tool"],
            call_ids,
        )

    def test_interrupted_historical_call_gets_synthetic_projection(self):
        tool_call = self._tool_call("historical", status="PENDING")
        ToolCall.objects.filter(pk=tool_call.pk).update(status="INTERRUPTED")
        interrupt = self._user_message("Stop now")
        interrupt.reply_to_message = self.message
        interrupt.save(update_fields=["reply_to_message"])
        Request.objects.create(
            message=interrupt, account=self.account, channel=self.channel,
        )

        context = interrupt.as_llm_chat(mode="thread", multimodal=False)

        self.assertEqual(context[-3]["tool_calls"][0]["id"], tool_call.call_id)
        self.assertEqual(context[-2]["role"], "tool")
        self.assertEqual(context[-2]["tool_call_id"], tool_call.call_id)
        self.assertIn("Interrupted", context[-2]["content"])
        self.assertEqual(context[-1]["content"], "Stop now")

    def test_stale_llm_output_cannot_submit_calls_after_new_user_turn(self):
        self._user_message("Newer input")

        calls = self.request.submit_tool_calls([{
            "id": "call-stale", "name": "test_tool", "arguments": {},
        }])

        self.assertEqual(calls, [])
        self.assertFalse(ToolCall.objects.filter(call_id="call-stale").exists())

    def test_projection_does_not_merge_edited_user_sibling_branch(self):
        common = self.message
        branch_a = self._user_message("Branch A")
        branch_a.reply_to_message = common
        branch_a.save(update_fields=["reply_to_message"])
        request_a = Request.objects.create(
            message=branch_a, account=self.account, channel=self.channel,
        )
        branch_b = self._user_message("Branch B")
        branch_b.reply_to_message = common
        branch_b.save(update_fields=["reply_to_message"])
        request_b = Request.objects.create(
            message=branch_b, account=self.account, channel=self.channel,
        )
        endpoints = {}
        for request, message, suffix in (
            (request_a, branch_a, "branch-a"),
            (request_b, branch_b, "branch-b"),
        ):
            call_message = save_tool_call(
                self.chat, "test_tool", {}, call_id=f"call-{suffix}",
                reply_to_message=message,
            )
            call = ToolCall.objects.create(
                call_id=f"call-{suffix}", tool_name="test_tool", arguments={},
                status="PENDING", request=request,
                tool_call_message=call_message, initial_user_message=message,
            )
            endpoints[suffix] = call.interrupt()

        context = endpoints["branch-a"].as_llm_chat(mode="thread", multimodal=False)
        call_ids = [
            item["tool_calls"][0]["id"] for item in context
            if item.get("tool_calls")
        ]
        self.assertIn("call-branch-a", call_ids)
        self.assertNotIn("call-branch-b", call_ids)

    @patch.object(Request, "categorize")
    @patch.object(Request, "identify_member")
    def test_later_active_responses_remain_recurring_continuations(
        self, _identify_member, _categorize
    ):
        tool_call = self._tool_call("recurring")

        tool_call.respond({"day": 1})
        tool_call.respond({"day": 2})

        self.assertEqual(self.request.child_requests.count(), 2)
