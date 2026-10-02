# LLM Tool Call Storage

This module provides functionality to store LLM tool calls as invisible messages within the unicom messaging system. Tool calls are stored with special message types and automatically included in LLM conversation history for contextual awareness.

## Overview

When an LLM worker needs to call external tools/functions, this system allows you to:

1. **Store tool calls** as invisible system messages in the chat
2. **Store tool responses** as invisible system messages 
3. **Include tool calls in conversation history** for LLM context
4. **Render tool calls** in the chat UI with distinct styling

## How It Works

### Message Types

Two new message types have been added to `Message.TYPE_CHOICES`:

- `tool_call`: Represents an LLM calling a tool/function
- `tool_response`: Represents the result of a tool call

### Data Storage

Tool call data is stored in the existing `Message.raw` JSON field:

```python
# Tool call message
{
    "tool_call": {
        "id": "call_abc123",
        "name": "search_database", 
        "arguments": {"query": "user info", "limit": 10}
    }
}

# Tool response message  
{
    "tool_response": {
        "call_id": "call_abc123",
        "result": {"users": [...], "count": 5}
    }
}
```

### Message Properties

Tool call messages have these characteristics:

- `media_type`: Either `'tool_call'` or `'tool_response'`
- `is_outgoing`: `None` (system message)
- `sender_name`: "System"
- `platform`: Same as the chat platform
- No Request objects are created (skipped in signals)

## Usage

### Basic Usage

```python
from unicom.services.llm.tool_calls import save_tool_call, save_tool_response
from unicom.models import Chat

# Get the chat where tool call happened
chat = Chat.objects.get(id="some_chat_id")

# Save a tool call
tool_call_msg = save_tool_call(
    chat=chat,
    tool_name="search_database",
    tool_args={"query": "user info", "limit": 10},
    user=request.user  # optional
)

# Save the tool response
tool_response_msg = save_tool_response(
    chat=chat,
    call_id=tool_call_msg.raw['tool_call']['id'],
    result={"users": [...], "count": 5},
    user=request.user  # optional
)
```

### Combined Usage

```python
from unicom.services.llm.tool_calls import save_tool_call_with_response

# Save both call and response in one operation
tool_call_msg, tool_response_msg = save_tool_call_with_response(
    chat=chat,
    tool_name="search_database", 
    tool_args={"query": "user info"},
    result={"users": [...], "count": 5},
    user=request.user  # optional
)
```

### OOP Interface (Recommended)

**Message-based (most common - replies to a message):**
```python
# Save just tool call
message.log_tool_interaction(
    tool_call={"name": "search", "arguments": {"query": "users"}, "id": "call_123"}
)

# Save just response  
message.log_tool_interaction(
    tool_response={"call_id": "call_123", "result": {"users": [...], "count": 5}}
)

# Save both together
message.log_tool_interaction(
    tool_call={"name": "search", "arguments": {"query": "users"}, "id": "call_123"},
    tool_response={"call_id": "call_123", "result": {"users": [...], "count": 5}}
)
```

**Chat-based (system-initiated):**
```python
# System-initiated tool call (no reply target)
chat.log_tool_interaction(
    tool_call={"name": "cleanup", "arguments": {}, "id": "call_456"}
)

# System-initiated with specific reply target
chat.log_tool_interaction(
    tool_call={"name": "search", "arguments": {"query": "users"}, "id": "call_789"}, 
    reply_to=some_message
)

# Save response only (will auto-find original call)
chat.log_tool_interaction(
    tool_response={"call_id": "call_123", "result": {...}}
)
```

### Getting LLM-Ready Conversation

```python
from unicom.services.llm.tool_calls import get_chat_with_tool_calls

# Get conversation including tool calls
message = chat.messages.last()
conversation = get_chat_with_tool_calls(message, depth=20)

# Or use the Message method directly
conversation = message.as_llm_chat(depth=20, mode="chat")
```

The conversation will include tool calls formatted for LLM APIs:

```python
[
    {"role": "user", "content": "Search for user info"},
    {
        "role": "assistant", 
        "content": "",
        "tool_calls": [{
            "id": "call_abc123",
            "type": "function", 
            "function": {
                "name": "search_database",
                "arguments": {"query": "user info", "limit": 10}
            }
        }]
    },
    {
        "role": "tool",
        "tool_call_id": "call_abc123", 
        "content": '{"users": [...], "count": 5}'
    },
    {"role": "assistant", "content": "Found 5 users matching your query..."}
]
```

## API Reference

### OOP Interface (Recommended)

#### `message.log_tool_interaction(tool_call=None, tool_response=None, user=None)`

Save tool call and/or response as replies to this message.

**Parameters:**
- `tool_call`: Dict with tool call data (e.g., `{"name": "search", "arguments": {...}, "id": "call_123"}`)
- `tool_response`: Dict with response data (e.g., `{"call_id": "call_123", "result": {...}}`)
- `user`: Django user making the call (optional)

**Returns:** Tuple of (tool_call_message, tool_response_message) or single message if only one provided

**Validation:**
- At least one of `tool_call` or `tool_response` must be provided
- `tool_call` must include `name` field
- `tool_response` must include `call_id` field
- If only `tool_response` provided, will auto-lookup original tool call for tool name

#### `chat.log_tool_interaction(tool_call=None, tool_response=None, reply_to=None, user=None)`

Save tool call and/or response in this chat.

**Parameters:**
- `tool_call`: Dict with tool call data
- `tool_response`: Dict with response data  
- `reply_to`: Message to reply to (optional)
- `user`: Django user making the call (optional)

**Returns:** Tuple of (tool_call_message, tool_response_message) or single message if only one provided

### Functional Interface

### `save_tool_call(chat, tool_name, tool_args, user=None, call_id=None, reply_to_message=None)`

Save an LLM tool call as an invisible message.

**Parameters:**
- `chat`: Chat instance where the tool call occurred
- `tool_name`: Name of the tool/function being called
- `tool_args`: Arguments passed to the tool (dict or JSON string)
- `user`: Django user making the tool call (optional)
- `call_id`: Unique identifier for the tool call (auto-generated if not provided)
- `reply_to_message`: Message this tool call is replying to (for thread mode)

**Returns:** Message instance representing the tool call

### `save_tool_response(chat, call_id, result, tool_name, user=None, reply_to_message=None)`

Save an LLM tool call response as an invisible message.

**Parameters:**
- `chat`: Chat instance where the tool response occurred
- `call_id`: ID of the original tool call
- `result`: Result from the tool call (any JSON-serializable object)
- `tool_name`: Name of the tool that was called
- `user`: Django user receiving the tool response (optional)
- `reply_to_message`: Message this tool response is replying to (for thread mode)

**Returns:** Message instance representing the tool response

### `save_tool_call_with_response(chat, tool_name, tool_args, result, user=None, call_id=None, reply_to_message=None)`

Save both a tool call and its response as invisible messages.

**Parameters:**
- `chat`: Chat instance where the tool call occurred
- `tool_name`: Name of the tool/function being called
- `tool_args`: Arguments passed to the tool
- `result`: Result from the tool call
- `user`: Django user making the tool call (optional)  
- `call_id`: Unique identifier for the tool call (auto-generated if not provided)
- `reply_to_message`: Message this tool call is replying to (for thread mode)

**Returns:** Tuple of (tool_call_message, tool_response_message)

### `get_chat_with_tool_calls(message, depth=129, mode="chat")`

Get LLM-ready chat history including tool calls.

**Parameters:**
- `message`: Message instance to get conversation for
- `depth`: Maximum number of messages to include (default: 129)
- `mode`: Either "chat" (conversation) or "thread" (reply chain)

**Returns:** List of dict objects formatted for LLM APIs

## Chat UI Rendering

Tool calls are rendered in the chat interface with:

- **Tool calls**: Gray background with cog icon, collapsible arguments
- **Tool responses**: Gray background with check icon, collapsible results
- **Reduced opacity**: 80% to indicate they're system messages
- **Collapsible details**: Click to expand/collapse arguments and results

## Thread Mode Compatibility

Tool call messages properly support thread mode by maintaining the `reply_to_message` chain:

- **Tool calls** can reply to any message (usually the user's request)
- **Tool responses** automatically reply to their corresponding tool call message
- **Thread mode** (`mode="thread"`) will include tool calls in the reply chain
- **Chat mode** (`mode="chat"`) includes tool calls in chronological order

Example thread structure:
```
User Message: "Search for users named John"
  └── Tool Call: search_users(name="John") 
      └── Tool Response: [{"id": 1, "name": "John Doe"}, ...]
          └── Assistant Response: "I found 3 users named John..."
```

## Integration with Existing Systems

### Request Processing

Tool call messages automatically skip Request object creation via the updated signal handler in `signals.py`. This prevents them from being processed as user requests.

### Chat History

Tool calls are automatically included when using:
- `Message.as_llm_chat()` method
- Chat history views and templates
- Any system that queries message history

### LLM Integration

The tool call format is compatible with:
- OpenAI Chat Completions API
- Anthropic Claude API (when tool calling is supported)
- Other LLM APIs that follow similar patterns

## Example Workflow

1. **User sends message**: "Search for all users named John"

2. **LLM processes and decides to use tool**:
   ```python
   # LLM worker code
   save_tool_call(chat, "search_users", {"name": "John"})
   ```

3. **Tool executes and returns result**:
   ```python
   # Tool execution code
   result = search_users(name="John")
   save_tool_response(chat, call_id, result)
   ```

4. **LLM gets context with tool calls**:
   ```python
   conversation = message.as_llm_chat(depth=129)
   # Includes the tool call and response for context
   ```

5. **LLM generates final response**: "I found 3 users named John..."

6. **User sees**: Original question → LLM response (tool calls are invisible but provide context)

## Notes

- Tool calls are "invisible" to regular users but provide crucial context for LLMs
- Tool call messages use the same platform as the chat they belong to
- A system account is automatically created for tool call messages
- Tool calls are included in chat exports and backups
- No additional database tables required - uses existing Message infrastructure
