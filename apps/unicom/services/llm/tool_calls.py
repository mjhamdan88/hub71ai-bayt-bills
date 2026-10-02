"""
LLM Tool Call Storage Service

This module provides functions for storing LLM tool calls as invisible messages
in the unicom message system. Tool calls are stored with special media types
and can be included in LLM conversation history for context.
"""

import uuid
from datetime import datetime
from django.utils import timezone
from django.contrib.auth.models import User
from unicom.models import Message, Chat, Account
import json


def save_tool_call(chat, tool_name, tool_args, user=None, call_id=None, reply_to_message=None):
    """
    Save an LLM tool call as an invisible message.
    
    Args:
        chat: Chat instance where the tool call occurred
        tool_name: Name of the tool/function being called
        tool_args: Arguments passed to the tool (dict or string)
        user: Django user making the tool call (optional)
        call_id: Unique identifier for the tool call (generated if not provided)
        reply_to_message: Message this tool call is replying to (for thread mode)
    
    Returns:
        Message instance representing the tool call
    """
    if not call_id:
        call_id = f"call_{uuid.uuid4().hex[:8]}"
    
    # Ensure tool_args is a dict
    if isinstance(tool_args, str):
        try:
            tool_args = json.loads(tool_args)
        except json.JSONDecodeError:
            tool_args = {"arguments": tool_args}
    
    # Create tool call message data
    tool_call_data = {
        "tool_call": {
            "id": call_id,
            "name": tool_name,
            "arguments": tool_args
        }
    }
    
    # Get or create a system account for tool calls
    system_account = _get_system_account(chat.channel, tool_name)
    
    # Create the tool call message
    message = Message.objects.create(
        id=f"tool_call_{chat.id}_{call_id}",
        channel=chat.channel,
        platform=chat.platform,
        sender=system_account,
        user=user,
        chat=chat,
        is_outgoing=None,  # System message
        sender_name="System",
        text=f"Tool call: {tool_name}",
        reply_to_message=reply_to_message,
        timestamp=timezone.now(),
        raw=tool_call_data,
        media_type='tool_call'
    )
    
    return message


def save_tool_response(chat, call_id, result, tool_name, user=None, reply_to_message=None):
    """
    Save an LLM tool call response as an invisible message.
    
    Args:
        chat: Chat instance where the tool response occurred
        call_id: ID of the original tool call
        result: Result from the tool call (any JSON-serializable object)
        tool_name: Name of the tool that was called
        user: Django user receiving the tool response (optional)
        reply_to_message: Message this tool response is replying to (for thread mode)
    
    Returns:
        Message instance representing the tool response
    """
    # Create tool response message data
    tool_response_data = {
        "tool_response": {
            "call_id": call_id,
            "result": result,
            "tool_name": tool_name
        }
    }
    
    # Get or create a system account for tool responses
    system_account = _get_system_account(chat.channel, tool_name)
    
    # Create result summary for display
    result_summary = str(result)
    if len(result_summary) > 100:
        result_summary = result_summary[:97] + "..."
    
    # Create the tool response message
    timestamp = int(timezone.now().timestamp() * 1000)
    message = Message.objects.create(
        id=f"tool_response_{chat.id}_{call_id}_{timestamp}",
        channel=chat.channel,
        platform=chat.platform,
        sender=system_account,
        user=user,
        chat=chat,
        is_outgoing=None,  # System message
        sender_name="System",
        text=f"Tool response: {result_summary}",
        reply_to_message=reply_to_message,
        timestamp=timezone.now(),
        raw=tool_response_data,
        media_type='tool_response'
    )
    
    return message


def save_tool_call_with_response(chat, tool_name, tool_args, result, user=None, call_id=None, reply_to_message=None):
    """
    Save both a tool call and its response as invisible messages.
    
    Args:
        chat: Chat instance where the tool call occurred
        tool_name: Name of the tool/function being called
        tool_args: Arguments passed to the tool
        result: Result from the tool call
        user: Django user making the tool call (optional)
        call_id: Unique identifier for the tool call (generated if not provided)
        reply_to_message: Message this tool call is replying to (for thread mode)
    
    Returns:
        Tuple of (tool_call_message, tool_response_message)
    """
    if not call_id:
        call_id = f"call_{uuid.uuid4().hex[:8]}"
    
    tool_call_msg = save_tool_call(chat, tool_name, tool_args, user, call_id, reply_to_message)
    tool_response_msg = save_tool_response(chat, call_id, result, tool_name, user, tool_call_msg)
    
    return tool_call_msg, tool_response_msg


def get_chat_with_tool_calls(message, depth=129, mode="chat"):
    """
    Get LLM-ready chat history including tool calls.
    
    This is a wrapper around Message.as_llm_chat() that ensures
    tool calls are included in the conversation history.
    
    Args:
        message: Message instance to get conversation for
        depth: Maximum number of messages to include
        mode: Either "chat" (conversation) or "thread" (reply chain)
    
    Returns:
        List of dict objects formatted for LLM APIs
    """
    return message.as_llm_chat(depth=depth, mode=mode, multimodal=True)


def _get_system_account(channel, tool_name):
    """
    Get or create a system account for tool call messages.
    
    Args:
        channel: Channel instance where the tool call is happening
        tool_name: Name of the tool being called
    
    Returns:
        Account instance for system messages
    """
    account_id = f"tool_{tool_name}_{channel.id}"
    
    account, created = Account.objects.get_or_create(
        channel=channel,
        id=account_id,
        defaults={
            'platform': 'Internal',
            'name': f'Tool: {tool_name}',
            'is_bot': True,
            'raw': {
                'tool_name': tool_name,
                'system_account': True,
                'purpose': 'LLM tool call storage'
            }
        }
    )
    
    return account
