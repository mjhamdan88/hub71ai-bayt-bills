## Context Variables Available in Bot Code

All bots have access to the following context variables when processing requests:

- **`bot`**: The Bot instance processing this request
- **`message`**: The Message object being processed  
- **`account`**: The Account/user who sent the message (message.sender)
- **`request`**: The Request object containing status, category, etc.
- **`member`**: The Member object if available (request.member)
- **`openai_client`**: OpenAI client instance

You can access these directly in your bot handler functions:
```python
def handle_incoming_message(message, bot, tools_list):
    user_id = account.id
    request_id = request.id
    # Make request available to tools by passing it
    return bot.reply_using_llm(
        message, tools_list,
        system_instruction="You are a helpful AI assistant",
        request=request  # This passes request context to tools
    )
```

## Basic Bot Template

The simplest bot implementation looks like this:

```python
def handle_incoming_message(message, bot, tools_list):
    # Available globals: bot, message, account, request, member (if available), openai_client
    return bot.reply_using_llm(
        message, tools_list,
        system_instruction="You are a helpful AI assistant",
        request=request  # Pass request object to make it available in tools
    )
```

## Message Handling Examples

### Different Response Types
```python
# Text messages
message.reply_with({"text": "Hello!"})

# HTML responses (only supported if message.platform == 'Email')
message.reply_with({"html": "<p>Formatted <b>response</b></p>"})

# Audio processing
if message.media_type == 'audio':
    return message.reply_using_llm(model="gpt-4-audio-preview")
```

### Advanced Features
```python
# Using tools with conversation context
response = message.reply_using_llm(
    tools_list=tools_list,
    mode="thread"  # Maintains conversation history
)

# File handling
message.reply_with({
    "text": "Here's your file",
    "files": ["path/to/file.pdf"]
})
