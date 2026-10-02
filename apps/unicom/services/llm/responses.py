"""Optional OpenAI Responses API adapter for Unicom.

The adapter deliberately has no knowledge of application authentication,
billing, or WebSockets. Applications inject an OpenAI-compatible client and, when live
updates are wanted, an event sink.  Existing Chat Completions callers never
import or execute this module unless they opt into ``api_mode="responses"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import ast
import json
import logging
import uuid
from typing import Any, Callable, Iterable, Mapping, Optional


logger = logging.getLogger(__name__)

StreamEventSink = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class ResponsesToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ResponsesResult:
    text: str
    content: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ResponsesToolCall] = field(default_factory=list)
    response_id: Optional[str] = None
    usage: Optional[dict[str, Any]] = None
    raw_response: Any = None


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    for method_name in ("model_dump", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            dumped = method()
            if isinstance(dumped, dict):
                return dumped
    return {}


def _user_facing_error(exc: Exception) -> str:
    """Extract an API message without leaking its JSON/error wrapper into chat UI."""
    body = getattr(exc, "body", None)
    if isinstance(body, Mapping):
        error = body.get("error")
        if isinstance(error, Mapping) and error.get("message"):
            return str(error["message"])
        if body.get("message"):
            return str(body["message"])
    return str(exc)


def _parse_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _responses_tool_output(content: Any) -> Any:
    """Recover structured multimodal output from Unicom's persisted wrapper."""
    output: Any = content if isinstance(content, str) else json.dumps(content)
    decoded: Any = None
    if isinstance(output, str):
        try:
            decoded = json.loads(output)
        except (TypeError, ValueError, json.JSONDecodeError):
            # Tool responses are persisted as a Python-repr wrapper such as
            # {'result': '<JSON string>', 'status': 'SUCCESS'}.
            try:
                decoded = ast.literal_eval(output)
            except (TypeError, ValueError, SyntaxError):
                decoded = None
    if isinstance(decoded, Mapping) and "result" in decoded:
        result = decoded.get("result")
        if isinstance(result, str):
            try:
                decoded = json.loads(result)
            except (TypeError, ValueError, json.JSONDecodeError):
                return output
        elif isinstance(result, Mapping):
            decoded = result
    if isinstance(decoded, Mapping) and isinstance(decoded.get("_responses_content"), list):
        return decoded["_responses_content"]
    return output


def chat_tools_to_responses(tools: Optional[Iterable[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    """Convert Chat Completions function tools into Responses function tools."""
    converted: list[dict[str, Any]] = []
    for tool in tools or ():
        function = tool.get("function") if isinstance(tool, Mapping) else None
        if not isinstance(function, Mapping) or not function.get("name"):
            continue
        item = {
            "type": "function",
            "name": function["name"],
            "description": function.get("description", ""),
            "parameters": function.get("parameters") or {"type": "object", "properties": {}},
        }
        if "strict" in tool:
            item["strict"] = bool(tool["strict"])
        converted.append(item)
    return converted


def chat_history_to_responses(messages: Iterable[Mapping[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Translate Unicom's persisted Chat-style history into Responses input."""
    instructions: list[str] = []
    inputs: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "")
        content = message.get("content", "")
        if role in {"system", "developer"}:
            if isinstance(content, str) and content.strip():
                instructions.append(content)
            continue

        if role == "assistant" and message.get("tool_calls"):
            if isinstance(content, str) and content:
                inputs.append({"role": "assistant", "content": content})
            for call in message.get("tool_calls") or ():
                function = call.get("function") or {}
                inputs.append(
                    {
                        "type": "function_call",
                        "call_id": call.get("id"),
                        "name": function.get("name"),
                        "arguments": (
                            function.get("arguments")
                            if isinstance(function.get("arguments"), str)
                            else json.dumps(function.get("arguments") or {})
                        ),
                    }
                )
            continue

        if role == "tool":
            inputs.append(
                {
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id"),
                    "output": _responses_tool_output(content),
                }
            )
            continue

        if role in {"user", "assistant"}:
            if isinstance(content, list):
                converted_content: list[dict[str, Any]] = []
                for block in content:
                    if not isinstance(block, Mapping):
                        continue
                    block_type = block.get("type")
                    if block_type == "text":
                        converted_content.append(
                            {
                                "type": "input_text" if role == "user" else "output_text",
                                "text": str(block.get("text") or ""),
                            }
                        )
                    elif block_type == "image_url" and role == "user":
                        image = block.get("image_url") or {}
                        image_url = image.get("url") if isinstance(image, Mapping) else None
                        if image_url:
                            converted_content.append(
                                {"type": "input_image", "image_url": image_url}
                            )
                    elif block_type == "input_audio" and role == "user":
                        audio = block.get("input_audio")
                        if isinstance(audio, Mapping):
                            converted_content.append(
                                {"type": "input_audio", "input_audio": dict(audio)}
                            )
                inputs.append({"role": role, "content": converted_content})
            else:
                inputs.append({"role": role, "content": content})

    return "\n\n".join(instructions), inputs


def _emit(sink: Optional[StreamEventSink], event: dict[str, Any]) -> None:
    if sink is None:
        return
    try:
        sink(event)
    except Exception:  # Streaming is a projection; it must not fail the durable reply.
        logger.exception("Unicom Responses stream sink failed")


def _tool_call_from_item(item: Any) -> Optional[ResponsesToolCall]:
    data = _as_dict(item)
    if data.get("type") != "function_call":
        return None
    call_id = str(data.get("call_id") or data.get("id") or "")
    name = str(data.get("name") or "")
    if not call_id or not name:
        return None
    return ResponsesToolCall(call_id=call_id, name=name, arguments=_parse_arguments(data.get("arguments")))


def _content_from_item(item: Any) -> Optional[dict[str, Any]]:
    """Normalize durable non-text output carried by one Responses item."""
    data = _as_dict(item)
    if data.get("type") == "image_generation_call" and data.get("result"):
        return {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{data['result']}"},
        }
    return None


def _result_from_response(response: Any) -> ResponsesResult:
    data = _as_dict(response)
    text = str(getattr(response, "output_text", None) or data.get("output_text") or "")
    tool_calls = [
        call
        for item in (getattr(response, "output", None) or data.get("output") or ())
        if (call := _tool_call_from_item(item)) is not None
    ]
    usage_obj = getattr(response, "usage", None) or data.get("usage")
    usage = _as_dict(usage_obj) if usage_obj is not None else None
    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})
    for item in (getattr(response, "output", None) or data.get("output") or ()):
        item_content = _content_from_item(item)
        if item_content is not None:
            content.append(item_content)
    return ResponsesResult(
        text=text,
        content=content,
        tool_calls=tool_calls,
        response_id=getattr(response, "id", None) or data.get("id"),
        usage=usage,
        raw_response=response,
    )


def create_response(
    *,
    client: Any,
    model: str,
    messages: Iterable[Mapping[str, Any]],
    tools: Optional[Iterable[Mapping[str, Any]]] = None,
    stream: bool = False,
    event_sink: Optional[StreamEventSink] = None,
    stream_id: Optional[str] = None,
    native_tools: Optional[Iterable[Mapping[str, Any]]] = None,
    **kwargs: Any,
) -> ResponsesResult:
    """Execute one Responses call and return a provider-neutral result."""
    instructions, input_items = chat_history_to_responses(messages)
    request: dict[str, Any] = {
        "model": model,
        "input": input_items,
        **{key: value for key, value in kwargs.items() if value is not None},
    }
    if instructions:
        request["instructions"] = instructions
    response_tools = chat_tools_to_responses(tools)
    response_tools.extend(dict(tool) for tool in (native_tools or ()))
    if response_tools:
        request["tools"] = response_tools

    if not stream:
        return _result_from_response(client.responses.create(**request))

    sid = stream_id or str(uuid.uuid4())
    _emit(event_sink, {"type": "response.started", "stream_id": sid})
    text_parts: list[str] = []
    tool_calls: dict[str, ResponsesToolCall] = {}
    streamed_content: list[dict[str, Any]] = []
    completed_response: Any = None
    sequence = 0
    try:
        for event in client.responses.create(**request, stream=True):
            data = _as_dict(event)
            event_type = str(getattr(event, "type", None) or data.get("type") or "")
            if event_type == "response.output_text.delta":
                delta = str(getattr(event, "delta", None) or data.get("delta") or "")
                if delta:
                    text_parts.append(delta)
                    sequence += 1
                    _emit(
                        event_sink,
                        {
                            "type": "response.text.delta",
                            "stream_id": sid,
                            "sequence": sequence,
                            "delta": delta,
                        },
                    )
            elif event_type == "response.output_item.done":
                item = getattr(event, "item", None) or data.get("item")
                call = _tool_call_from_item(item)
                if call is not None:
                    tool_calls[call.call_id] = call
                item_content = _content_from_item(item)
                if item_content is not None:
                    streamed_content.append(item_content)
            elif event_type == "response.completed":
                completed_response = getattr(event, "response", None) or data.get("response")

        base = _result_from_response(completed_response) if completed_response is not None else ResponsesResult(text="")
        result = ResponsesResult(
            text=base.text or "".join(text_parts),
            content=base.content or streamed_content,
            tool_calls=base.tool_calls or list(tool_calls.values()),
            response_id=base.response_id,
            usage=base.usage,
            raw_response=base.raw_response,
        )
        _emit(
            event_sink,
            {
                "type": "response.finished",
                "stream_id": sid,
                "response_id": result.response_id,
                "text": result.text,
            },
        )
        return result
    except Exception as exc:
        _emit(
            event_sink,
            {"type": "response.failed", "stream_id": sid, "error": _user_facing_error(exc)},
        )
        raise
