## Context Variables Available in Tool Code

All tools have access to the following context variables when executed:

- **`bot`**: The Bot instance processing this request
- **`message`**: The Message object being processed
- **`account`**: The Account/user who sent the message (message.sender)
- **`request`**: The Request object containing status, category, etc.
- **`member`**: The Member object if available (request.member)
- **`tool_call`**: The ToolCall instance for this tool execution (see Delayed Responses below)
- **`openai_client`**: OpenAI client instance

You can access these directly in your tool functions:
```python
def my_tool():
    user_id = account.id
    request_id = request.id
    message_content = message.content
    if member:
        member_info = member.id
    # Access the tool call instance
    tool_call_id = tool_call.call_id if tool_call else None
```

## Basic Tool Template

```python
def summarize_webpage(url: str, max_sentences: int = 3) -> str:
    """Fetches and summarizes webpage content"""
    response = requests.get(url, timeout=10)
    soup = BeautifulSoup(response.text, 'html.parser')
    text = soup.get_text(separator=' ')
    sentences = re.split(r'(?<=[.!?]) +', text)
    return ' '.join(sentences[:max_sentences])

tool_definition = {
    "name": "summarize_webpage",
    "description": "Fetches a web page and returns a summary",
    "parameters": {
        "url": {
            "type": "string", 
            "description": "The URL to summarize"
        },
        "max_sentences": {
            "type": "integer", 
            "description": "Maximum sentences",
            "default": 3
        }
    },
    "run": summarize_webpage
}
```

## Delayed Tool Responses

By default, tools are expected to return a result immediately, which the system automatically sends to the LLM. However, some tools need to defer their response (e.g., waiting for user confirmation, long-running processes, scheduled tasks).

**To defer a response, return `None`:**

```python
def ask_user_confirmation(question: str) -> str:
    """Ask user a question and wait for their response via button click"""
    from unicom.services.telegram.create_inline_keyboard import create_inline_keyboard, create_callback_button

    # Send message with buttons linked to this tool call
    message.reply_with({
        'text': question,
        'reply_markup': create_inline_keyboard([
            [create_callback_button("Yes", {"action": "confirm", "value": True}, message=message, tool_call=tool_call)],
            [create_callback_button("No", {"action": "confirm", "value": False}, message=message, tool_call=tool_call)]
        ])
    })

    # Return None to indicate this tool will respond later
    # The system marks the tool call as IN_PROGRESS and waits
    return None

tool_definition = {
    "name": "ask_user_confirmation",
    "description": "Ask the user a yes/no question and wait for their response",
    "parameters": {
        "question": {"type": "string", "description": "The question to ask"}
    },
    "run": ask_user_confirmation
}
```

Then in your callback handler, respond to the tool call:

```python
from django.dispatch import receiver
from unicom.signals import telegram_callback_received

@receiver(telegram_callback_received)
def handle_confirmations(sender, callback_execution, tool_call, original_message, **kwargs):
    data = callback_execution.callback_data

    if isinstance(data, dict) and data.get('action') == 'confirm':
        # Respond to the tool call - this notifies the LLM
        if tool_call:
            tool_call.respond({
                'confirmed': data['value'],
                'timestamp': str(timezone.now())
            })

        # Send confirmation to user
        original_message.reply_with({
            'text': f'✅ Response recorded: {"Yes" if data["value"] else "No"}'
        })
```

**Key points:**
- Returning `None` marks the tool call as `IN_PROGRESS`
- Store the `tool_call` instance (it's available in your tool context)
- Call `tool_call.respond(result)` later to complete the tool call (the system will wrap as `{"status": "...", ...}`)
- You can optionally pass a `status` to `tool_call.respond(result, status="SUCCESS|WARNING|ERROR")`; if omitted it defaults to `SUCCESS`
- The system automatically creates a child request when all pending tool calls are completed

## Handling Expected Errors/Warnings Without Breaking the Conversation

If your tool encounters a user-facing error that should be reported to the LLM (and the user) without failing the request pipeline, raise `ToolHandlerError`:

```python
def fetch_invoice(invoice_id: str):
    invoice = lookup_invoice(invoice_id)
    if not invoice:
        # Sends an ERROR result back to the LLM but keeps the flow alive
        raise ToolHandlerError("Invoice not found", status="ERROR", payload={"reason": "missing_invoice", "invoice_id": invoice_id})
    return {"invoice": invoice}  # Will be wrapped with status=SUCCESS by the system

def check_inventory(sku: str):
    stock = current_stock(sku)
    if stock < 5:
        # Sends a WARNING result back to the LLM; conversation continues
        raise ToolHandlerWarning("Low stock", payload={"sku": sku, "stock": stock})
    return {"stock": stock}
```

- `ToolHandlerError` and `ToolHandlerWarning` are injected into tool globals (or import from `unibot.services.tool_exceptions`).
- `status` defaults to `ERROR`/`WARNING` if not provided.
- `payload` is optional; if omitted, the error/warning message string is sent.
- Tool returns are wrapped automatically: return values become `{"status": "SUCCESS", ...}`, warnings become `{"status": "WARNING", ...}`, errors become `{"status": "ERROR", ...}`.
- Unexpected exceptions still fail the request (same as before), so reserve these exceptions for known/handled cases.

## LLM Progress Updates (Auto-Injected Parameter)

- The platform automatically injects a required parameter `progress_updates_for_user` into every tool schema to force the LLM to state (in one line) what it is doing and why; this is logged and visible in chat history and ToolCall records.
- If your tool does not declare this parameter, the platform strips it before calling your function, so existing signatures remain compatible.
- If you want to use it inside your tool, simply add `progress_updates_for_user: str` to your function signature and tool parameters to access the provided text.

## Using Credentials in a Tool

If your tool requires credentials, use `get_credentials`:

```python
from unibot.services.credentials import get_credentials

def fetch_data_with_openai_api_key(query: str):
    creds = get_credentials([
        {"key": "OPENAI_API_KEY_FOR_SUMMARIZER_TOOL", "label": "OpenAI API Key for Summarizer Tool", "type": "password", "placeholder": "Enter your OpenAI API key for summarization"}
    ])
    if creds is None:
        return "Please set up your OpenAI API key to use this tool."
    api_key = creds["OPENAI_API_KEY_FOR_SUMMARIZER_TOOL"]
    # Use api_key to fetch data from OpenAI...
```

You can require multiple fields and use advanced options:

```python
def create_github_issue():
    creds = get_credentials([
        {"key": "GITHUB_PERSONAL_ACCESS_TOKEN_FOR_ISSUE_CREATOR", "type": "password", "min_length": 40, "max_length": 100, "description": "Your GitHub personal access token for creating issues", "required": True},
        {"key": "GITHUB_USERNAME_FOR_ISSUE_CREATOR", "type": "text", "min_length": 4, "max_length": 39, "description": "Your GitHub username for issue creation", "required": True}
    ])
    if creds is None:
        return "Please set up your GitHub credentials."
    token = creds["GITHUB_PERSONAL_ACCESS_TOKEN_FOR_ISSUE_CREATOR"]
    username = creds["GITHUB_USERNAME_FOR_ISSUE_CREATOR"]
    # Use token and username to create a GitHub issue...
```
