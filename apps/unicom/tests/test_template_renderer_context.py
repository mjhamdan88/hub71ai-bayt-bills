import pytest

from unicom.services.template_renderer import (
    build_unicom_message_context,
    render_template,
)


def test_build_unicom_message_context_includes_message_channel_sender():
    params = {
        "subject": "Hi",
        "html": "<p>Hello {{ variables.name }}</p>",
        "to": ["a@example.com"],
        "reply_to_message_id": "msg-123",
    }
    channel = {"id": 1, "name": "Main", "platform": "Email"}
    user = {"id": 9, "username": "alice", "email": "alice@example.com"}
    ctx = build_unicom_message_context(params=params, channel=channel, user=user)
    assert ctx["message"]["subject"] == "Hi"
    assert ctx["message"]["to"] == ["a@example.com"]
    assert ctx["channel"]["platform"] == "Email"
    assert ctx["sender"]["username"] == "alice"
    assert ctx["message"]["reply_to_message_id"] == "msg-123"


def test_render_template_with_built_context_and_variables():
    params = {"html": "<p>Hello {{ variables.name }}</p>"}
    ctx = build_unicom_message_context(params=params, channel={}, user={})
    result = render_template(
        params["html"],
        base_context=ctx,
        variables={"name": "Bob"},
    )
    assert result.html == "<p>Hello Bob</p>"
    assert result.variables["name"] == "Bob"
