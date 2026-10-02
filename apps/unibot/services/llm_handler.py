from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from unibot.models import Bot
import base64
import uuid
import re
import json
import os
from pathlib import Path
import logging
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional, Type, Union
from openai import OpenAI
from unicom.models.message import Message
from unicom.models.tool_call import ToolCall
from .tool_result_handler import handle_tool_result, prepare_file_response
from .tool_exceptions import ToolHandlerError, ToolHandlerWarning
from django.db import transaction
from django.conf import settings

logger = logging.getLogger(__name__)


def _validated_nested_required(tool_name: str, parameter_name: str, schema: dict):
    """Return a valid nested JSON Schema required list, if one was supplied."""
    if 'required' not in schema:
        return None

    required = schema['required']
    properties = schema.get('properties')
    if not isinstance(required, list) or not all(isinstance(key, str) for key in required):
        raise ValueError(
            f"Tool {tool_name!r} parameter {parameter_name!r} must define "
            "'required' as a list of property names."
        )
    if not isinstance(properties, dict):
        raise ValueError(
            f"Tool {tool_name!r} parameter {parameter_name!r} defines "
            "'required' without an object 'properties' mapping."
        )
    unknown = [key for key in required if key not in properties]
    if unknown:
        raise ValueError(
            f"Tool {tool_name!r} parameter {parameter_name!r} requires "
            f"unknown properties: {', '.join(unknown)}."
        )
    missing = [key for key in properties if key not in required]
    if missing:
        raise ValueError(
            f"Tool {tool_name!r} parameter {parameter_name!r} must require every "
            f"property in strict mode; missing: {', '.join(missing)}."
        )
    return required


def _request_was_superseded(request):
    if request is None:
        return False
    initial_request = request.initial_request or request
    return initial_request.message.chat.messages.filter(
        is_outgoing=False,
        timestamp__gt=initial_request.message.timestamp,
    ).exclude(media_type__in=['tool_call', 'tool_response']).exists()


def build_openai_tools(tools_list: Optional[List[object]], bot=None, message=None, openai_client=None, request=None, tool_call=None) -> (List[dict], Dict[str, Callable], Dict[str, List[str]]):
    """
    Build OpenAI tool schema and a map of tool name to run function from a list of tool objects.
    Args:
        tools_list: List of tool objects, each with a get_definition() method.
        tool_call: Optional ToolCall instance to pass to tool execution context.
    Returns:
        openai_tools: List of OpenAI tool schemas.
        tool_map: Dict mapping tool name to its run function.
    """
    openai_tools = []
    tool_map = {}
    auto_params_map: Dict[str, List[str]] = {}
    for tool in (tools_list or []):
        defn = tool.get_definition(bot=bot, message=message, openai_client=openai_client, request=request, tool_call=tool_call)
        if not defn:
            print(f"[DEBUG] Tool {tool} skipped: get_definition() returned None or empty.")
            continue
        run_fn = defn.pop('run', None)
        name = defn.get('name')
        if not name:
            print(f"[DEBUG] Tool {tool} skipped: definition missing 'name'. Definition: {defn}")
            continue
        if run_fn:
            tool_map[name] = run_fn
        else:
            print(f"[DEBUG] Tool {tool} ('{name}') skipped: definition missing 'run' function. Definition: {defn}")
            continue
        # Build JSON Schema for parameters
        raw_params = defn.get('parameters', {}) or {}
        auto_params = []

        # Inject progress_updates_for_user if missing to force LLM to describe intent
        if 'progress_updates_for_user' not in raw_params:
            raw_params = dict(raw_params)
            raw_params['progress_updates_for_user'] = {
                "type": "string",
                "description": "In one concise line, explain what you are doing and why (user-visible progress update)."
            }
            auto_params.append('progress_updates_for_user')

        if auto_params:
            auto_params_map[name] = auto_params
        props: dict = {}
        required: list = []
        for pname, pinfo in raw_params.items():
            ptype = pinfo.get('type', 'string')
            # Preserve enum/items for the LLM; map common aliases for scalars.
            if isinstance(ptype, str):
                if ptype in ('str', 'string'):
                    otype = 'string'
                elif ptype in ('int', 'integer'):
                    otype = 'integer'
                elif ptype in ('float', 'number'):
                    otype = 'number'
                elif ptype in ('bool', 'boolean'):
                    otype = 'boolean'
                else:
                    otype = ptype
            else:
                # Allow JSON Schema style: list/union types
                otype = ptype

            prop = {'type': otype}
            # Carry through common JSON Schema fields if present.
            for key in (
                'description',
                'enum',
                'items',
                'properties',
                'additionalProperties',
                'format',
                'minimum',
                'maximum',
                'minItems',
                'maxItems',
                'anyOf',
                'oneOf',
                'allOf',
            ):
                if key in pinfo:
                    prop[key] = pinfo[key]
            nested_required = _validated_nested_required(name, pname, pinfo)
            if nested_required is not None:
                prop['required'] = nested_required
            if 'default' in pinfo:
                prop['default'] = pinfo['default']
            # OpenAI strict function schemas require every property to appear
            # in `required`, including properties that advertise a default.
            # The default still documents the preferred value for the model
            # and remains useful to non-strict consumers.
            required.append(pname)
            props[pname] = prop

        param_schema = {
            'type': 'object',
            'properties': props,
            'additionalProperties': False,
        }
        if required:
            param_schema['required'] = required
        openai_tools.append({
            'type': 'function',
            'function': {
                'name': name,
                'description': defn.get('description', ''),
                'parameters': param_schema
            },
            'strict': True
        })

    return openai_tools, tool_map, auto_params_map


def process_llm_content(msg: object) -> dict:
    """
    Convert an OpenAI message object to a reply dict for the message.reply_with method.
    Handles audio, image, and text blocks.
    """
    # First, handle new-style audio responses returned in msg.audio (OpenAI SDK 1.14+)
    if hasattr(msg, 'audio') and msg.audio and hasattr(msg.audio, 'data'):
        audio_data = msg.audio.data
        transcript = getattr(msg.audio, 'transcript', '')
        audio_id = getattr(msg.audio, 'id', None)
        # Default to opus/ogg if format not provided
        # OpenAI SDK may expose 'format' in msg.audio, but fallback to opus
        audio_format = getattr(msg.audio, 'format', 'opus') or 'opus'
        ext = 'ogg' if audio_format in {'opus', 'ogg'} else audio_format
        audio_file_name = f"media/{uuid.uuid4()}.{ext}"
        with open(audio_file_name, "wb") as f:
            f.write(base64.b64decode(audio_data))
        reply_dict = {
            'type': 'audio',
            'file_path': audio_file_name,
        }
        if audio_id:
            reply_dict['audio_id'] = audio_id
        if transcript:
            reply_dict['text'] = transcript
        return reply_dict

    content = getattr(msg, 'content', None)
    if isinstance(content, list):
        out = None
        for block in content:
            t = block.get('type')
            if t == 'input_audio':
                data = block['input_audio']['data']
                ext = block['input_audio'].get('format','wav')
                path = f"media/{uuid.uuid4()}.{ext}"
                with open(path,'wb') as f:
                    f.write(base64.b64decode(data))
                out = { 'type': 'audio', 'file_path': path, 'text': '' }
            elif t == 'image_url':
                m = re.match(r"data:(.*?);base64,(.*)", block['image_url']['url'])
                if m:
                    ext = m.group(1).split('/')[-1]
                    path = f"media/{uuid.uuid4()}.{ext}"
                    with open(path,'wb') as f:
                        f.write(base64.b64decode(m.group(2)))
                    out = { 'type': 'image', 'file_path': path, 'text': '' }
            elif t == 'text' and out is None:
                out = { 'type': 'text', 'text': block['text'] }
        # Ensure text messages are never empty to avoid Telegram API 400 error
        result = out or { 'type': 'text', 'text': '' }
        if result['type'] == 'text' and not result['text']:
            result['text'] = ' '
        return result
    return { 'type': 'text', 'text': content or '' }


def run_llm_handler(
    bot: Bot,
    message: Message,
    tools_list: Optional[List[object]] = None,
    model_audio: str = "gpt-4o-audio-preview",
    model_default: str = "o4-mini-2025-04-16",
    system_instruction: Optional[str] = None,
    max_function_calls: int = 7,
    as_llm_chat_params: Optional[dict] = None,
    tool_choice: str = "auto",
    debug: bool = False,
    request=None,
    openai_client: OpenAI = None,
    api_mode: str = "chat_completions",
    stream: bool = False,
    stream_event_sink=None,
    native_responses_tools: Optional[List[dict]] = None,
) -> None:
    """
    Modular LLM handler for bots supporting audio, text, images, and tool use.
    Args:
        message: The input message object (Message).
        openai_client: The OpenAI client instance.
        tools_list: List of tool objects (optional).
        model_audio: Model name for audio messages.
        model_default: Model name for text messages.
        system_instruction: System/developer prompt (optional).
        max_function_calls: Max number of tool call loops.
        as_llm_chat_params: Dict of params for as_llm_chat (depth, mode, etc.).
        tool_choice: OpenAI tool_choice parameter (default 'auto').
        debug: Print debug info if True.
    Returns:
        None (calls message.reply_with with the reply dict).
    """
    # First get chat history with multimodal=True to check for audio messages
    llm_chat_args = dict(depth=129, mode="thread", system_instruction=system_instruction, multimodal=True)
    if as_llm_chat_params:
        llm_chat_args.update(as_llm_chat_params)
    messages = message.as_llm_chat(**llm_chat_args)

    # Check if any user messages in the conversation are audio
    multimodal = False
    for msg in messages:
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for content_block in msg["content"]:
                if content_block.get("type") == "input_audio":
                    multimodal = True
                    break
            if multimodal:
                break

    model = model_audio if multimodal else model_default
    print(f"[DEBUG] tools_list: {tools_list}")
    print(f"[DEBUG] multimodal detected: {multimodal}, using model: {model}")
    # Note: tool_call will be set per-tool during execution, passing None here for initial schema building
    openai_tools, tool_map, auto_params_map = build_openai_tools(tools_list, bot=bot, message=message, openai_client=openai_client, request=request, tool_call=None)
    if debug:
        print("[DEBUG] Initial messages:", messages)
        print("[DEBUG] OpenAI tools:", openai_tools)

    if api_mode not in {"chat_completions", "responses"}:
        raise ValueError("api_mode must be 'chat_completions' or 'responses'")

    # Single LLM call instead of loop - unicom handles tool call coordination
    kwargs = {}
    if multimodal:
        kwargs.update({ 'modalities': ['text','audio'],
                        'audio': { 'voice': 'alloy', 'format': 'opus' } })
    if openai_tools:
        kwargs.update({ 'tools': openai_tools, 'tool_choice': tool_choice })
    if debug:
        print(f"[DEBUG] Calling OpenAI: model={model}, kwargs={kwargs}")
    if api_mode == "responses":
        if multimodal:
            raise ValueError(
                "Responses mode does not yet support Unibot audio output; "
                "select a text-capable model or use chat_completions."
            )
        from unicom.services.llm.responses import create_response

        result = create_response(
            client=openai_client,
            model=model,
            messages=messages,
            tools=openai_tools,
            stream=stream,
            event_sink=stream_event_sink,
            tool_choice=tool_choice if openai_tools else None,
            native_tools=native_responses_tools,
        )
        tool_calls = [
            SimpleNamespace(
                id=call.call_id,
                function=SimpleNamespace(
                    name=call.name,
                    arguments=json.dumps(call.arguments),
                ),
            )
            for call in result.tool_calls
        ]
        msg = SimpleNamespace(content=result.content or result.text, tool_calls=tool_calls)
    else:
        resp = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )
        msg = resp.choices[0].message
    if debug:
        print("[DEBUG] OpenAI response:", msg)

    tool_calls = getattr(msg, 'tool_calls', None)
    if tool_calls:
        if debug:
            print(f"[DEBUG] Detected {len(tool_calls)} tool call(s)")

        # A Responses result can contain user-facing prose before its function
        # calls. Persist it before creating the tool messages so refreshes and
        # every renderer preserve the provider's actual chronological order.
        # Mark it as non-final so Dashboard completion notifications wait for
        # the eventual response after the tool continuation.
        preamble = process_llm_content(msg)
        if (
            preamble.get('type') == 'text'
            and str(preamble.get('text') or '').strip()
        ):
            preamble['_message_raw'] = {'assistant_phase': 'tool_preamble'}
            message.reply_with(preamble)

        # Convert OpenAI tool calls to unicom format
        tool_call_data = []
        for call in tool_calls:
            fname = call.function.name
            fargs = json.loads(call.function.arguments or '{}')
            tool_call_data.append({
                "name": fname,
                "arguments": fargs,
                "id": call.id,  # Use OpenAI's call ID
                "auto_params": auto_params_map.get(fname, []),
            })

        # Submit all tool calls to unicom (atomic operation)
        unicom_tool_calls = request.submit_tool_calls(tool_call_data)
        if not unicom_tool_calls:
            # A newer user turn won the request lock while this LLM call was in flight.
            return

        def execute_tool_calls():
            # Execute each tool and respond immediately unless the tool returns None (which means the tool handles its own response asynchronously)
            file_paths = []  # Accumulate file paths from tool calls
            for i, call in enumerate(tool_calls):
                if _request_was_superseded(request):
                    ToolCall.interrupt_unresolved(request.tool_calls.all())
                    return
                fname = call.function.name
                fargs = json.loads(call.function.arguments or '{}')
                tool_call_instance = unicom_tool_calls[i]

                if debug:
                    print(f"[DEBUG] Executing {fname} with args {fargs}")

                # Rebuild tool map with tool_call context for this specific tool
                _, tool_map_with_context, auto_params_map_with_context = build_openai_tools(
                    tools_list,
                    bot=bot,
                    message=message,
                    openai_client=openai_client,
                    request=request,
                    tool_call=tool_call_instance
                )

                # Execute tool with tool_call in context
                status = 'SUCCESS'
                auto_params = auto_params_map_with_context.get(fname, [])
                # Strip auto-injected params the tool didn't declare
                for auto_param in auto_params:
                    fargs.pop(auto_param, None)
                try:
                    result = tool_map_with_context[fname](**fargs)
                except ToolHandlerWarning as e:
                    status = getattr(e, 'status', 'WARNING')
                    result = e.payload if e.payload is not None else {"warning": str(e)}
                    if debug:
                        print(f"[DEBUG] {fname} raised ToolHandlerWarning with status {status}: {result}")
                except ToolHandlerError as e:
                    status = getattr(e, 'status', 'ERROR')
                    result = e.payload if e.payload is not None else {"error": str(e)}
                    if debug:
                        print(f"[DEBUG] {fname} raised ToolHandlerError with status {status}: {result}")
                except Exception as exc:  # pragma: no cover - guard against unexpected tool crashes
                    logger.exception("Unexpected failure while executing %s", fname)
                    payload = {"error": "Unexpected tool error"}
                    if getattr(settings, "DEBUG", False):
                        payload["details"] = str(exc)
                    tool_call_instance.respond(payload, status="ERROR")
                    continue

                # If tool returns None, it handles its own response - mark as ACTIVE
                if result is None:
                    tool_call_instance.mark_active()
                    if debug:
                        print(f"[DEBUG] {fname} returned None - tool is now ACTIVE and waiting for async response")
                    continue

                # Handle file results (existing code)
                file_path = handle_tool_result(result)
                if file_path:
                    if debug:
                        print(f"[DEBUG] Tool returned a file: {file_path}")
                    file_paths.append(file_path)
                    result = f"File processed: {file_path}"

                # Respond to unicom tool call automatically
                tool_call_instance.respond(result, status=status)

                if debug:
                    print(f"[DEBUG] {fname} result:", result)

            # Child request will be automatically created by unicom when all tool calls are responded to

        # Ensure tool call messages commit before executing tools
        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(execute_tool_calls)
        else:
            execute_tool_calls()
        return

    # No tool calls: send final response
    if _request_was_superseded(request):
        return
    reply = process_llm_content(msg)

    # If reply is text but the text is empty/whitespace, remove text key and
    # attempt to infer a better type from any attached file_path.
    if reply.get('type') == 'text' and (not reply.get('text') or not str(reply['text']).strip()):
        reply.pop('text', None)
        fpath = reply.get('file_path')
        if fpath:
            # If multiple paths, take first for type inference
            if isinstance(fpath, list):
                fpath = fpath[0]
            ext = Path(fpath).suffix.lower()
            if ext in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}:
                reply['type'] = 'image'
            elif ext in {'.mp3', '.wav', '.opus', '.ogg', '.m4a'}:
                reply['type'] = 'audio'
            else:
                reply['type'] = 'file'
        else:
            # Nothing to send; fallback to a minimal placeholder to avoid empty text error
            reply['text'] = '...'  # will be treated as short text

    if debug:
        print("[DEBUG] Sending final reply:", reply)
    message.reply_with(reply)
