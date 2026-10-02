# Django Unicom

**Unified communication layer for Django** — easily integrate Telegram bots, WhatsApp bots, Email bots, and Web Chat with a consistent API across all platforms.

## 📑 Table of Contents

- [Quick Start](#-quick-start)
- [Available Platforms](#-available-platforms)
- [Core Models & Usage](#-core-models--usage)
  - [Channel Model](#channel-model)
  - [Message Model](#message-model)
  - [Chat Model](#chat-model)
  - [Template System](#template-system)
  - [Draft Messages & Scheduling](#draft-messages--scheduling)
- [Advanced Features](#-advanced-features)
  - [Email-Specific Features](#email-specific-features)
  - [Telegram-Specific Features](#telegram-specific-features)
    - [Typing Indicators](#-typing-indicators)
    - [Interactive Buttons & Callbacks](#-interactive-messages-with-action-buttons)
      - [Handling Button Clicks](#-handling-button-clicks)
      - [Tool-Generated Buttons](#-tool-generated-buttons-advanced)
      - [Button Routing Best Practices](#-button-routing-best-practices)
    - [Editing Messages](#-editing-telegram-messages)
    - [File Downloads and Voice Messages](#-file-downloads-and-voice-messages)
  - [WebChat-Specific Features](#webchat-specific-features)
    - [Web-Based Chat Interface](#-web-based-chat-interface)
    - [Setting Up WebChat](#-setting-up-webchat)
    - [WebChat Component Options](#-webchat-component-options)
    - [WebChat User Types](#-webchat-user-types)
    - [Programmatic WebChat Usage](#-programmatic-webchat-usage)
    - [WebChat API Endpoints](#-webchat-api-endpoints)
    - [Multi-Chat Features](#-multi-chat-features)
    - [Custom Filtration (Project-Based Chats)](#-custom-filtration-project-based-chats)
    - [Real-Time Updates (WebSocket Support)](#-real-time-updates-websocket-support)
    - [Guest User Migration](#-guest-user-migration)
    - [WebChat Security](#-webchat-security)
    - [WebChat Architecture](#-webchat-architecture)
    - [WebChat Testing](#-webchat-testing)
    - [WebChat Optional Enhancements](#-webchat-optional-enhancements)
  - [LLM Integration](#llm-integration)
- [Delayed Tool Calls](#delayed-tool-calls)
- [Message Scheduling](#message-scheduling)
- [Production Setup](#-production-setup)
  - [IMAP Listeners](#imap-listeners)
  - [Scheduled Message Processing](#scheduled-message-processing)
- [Management Commands](#-management-commands)
- [Contributing](#-contributing)
- [License](#-license)
- [Release Automation](#-release-automation)

---

## 🚀 Quick Start

1. **Install the package (plus Playwright browser binaries):**
   ```bash
   pip install django-unicom
   # Install the headless Chromium browser that powers PDF export
   python -m playwright install --with-deps
   ```

2. **Add required apps to your Django settings:**

   ```python
   INSTALLED_APPS = [
       ...
       'django_ace',  # Required for the JSON configuration editor
       'unicom',
   ]
   ```

3. **Include `unicom` URLs in your project's `urls.py`:**

   > This is required so that webhook URLs can be constructed correctly.

   ```python
   from django.urls import path, include

   urlpatterns = [
       ...
       path('unicom/', include('unicom.urls')),
   ]
   ```

4. **Define your public origin:**
   In your Django `settings.py`:

   ```python
   DJANGO_PUBLIC_ORIGIN = "https://yourdomain.com"
   ```

   Or via environment variable:

   ```env
   DJANGO_PUBLIC_ORIGIN=https://yourdomain.com
   ```

5. **Set up media file handling:**
   In your Django `settings.py`:
   ```python
   MEDIA_URL = '/media/'
   MEDIA_ROOT = os.path.join(BASE_DIR, '')
   ```
   In your main project `urls.py`:
   ```python
   from django.conf import settings
   from django.conf.urls.static import static
   urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
   ```

6. *(Optional, but recommended)* **Set your TinyMCE Cloud API key** — required if you plan to compose **Email** messages from the Django admin UI.

   Obtain a free key at <https://www.tiny.cloud>, then add it to your `settings.py`:

   ```python
   UNICOM_TINYMCE_API_KEY = "your-tinymce-api-key"
   ```

   Or via environment variable:

   ```env
   UNICOM_TINYMCE_API_KEY=your-tinymce-api-key
   ```

   and then you would still have to load it in settings.py

   ```python
   UNICOM_TINYMCE_API_KEY = os.getenv('UNICOM_TINYMCE_API_KEY', '')
   ```

7. *(Optional)* **Set your OpenAI API key** — required if you plan to use the AI-powered template population service.

   Obtain a key from <https://platform.openai.com/api-keys>, then set it as an environment variable:

   ```env
   OPENAI_API_KEY="your-openai-api-key"
   ```

   The application will automatically pick it up from the environment.

8. **Install ffmpeg:**
   - `ffmpeg` is required for converting audio files (e.g., Telegram voice notes) to formats compatible with OpenAI and other services. Make sure `ffmpeg` is installed on your system or Docker image.

That's it! Unicom can now register and manage public-facing webhooks (e.g., for Telegram bots) based on your defined base URL and can automatically sync with email clients.

---

## 📱 Available Platforms

Django Unicom supports the following communication platforms:

- **Email** - SMTP/IMAP with auto-discovery, rich HTML content, link tracking
- **Telegram** - Bot API integration with webhooks, media support, typing indicators, interactive buttons
- **WhatsApp** - Business API integration, template messages, delivery status
- **WebChat** - Web-based chat interface with multi-chat support, real-time updates, guest users, interactive buttons
- **Internal** - System-to-system messaging within your application

**Cross-Platform Features:**
- 🌐 **Interactive Buttons**: Work on both Telegram and WebChat with the same API
- 🔒 **Secure Button Clicks**: Session-based security with expiration support
- 🎯 **Unified Handlers**: Same signal receivers handle clicks from all platforms

Throughout this documentation, features will be marked as:
- ✅ **All platforms**: Works across all communication channels
- 📧 **Email only**: Specific to email channels
- 📱 **Telegram only**: Specific to Telegram channels
- 💬 **WhatsApp only**: Specific to WhatsApp channels
- 🌐 **WebChat only**: Specific to WebChat channels
- 🤖 **LLM features**: AI integration (platform-agnostic)

---

## 📝 Core Models & Usage

### Channel Model

Channels represent communication endpoints for different platforms.

#### Creating Channels Programmatically

```python
from unicom.models import Channel

# Email Channel - Auto-discovers SMTP/IMAP settings
email_channel = Channel.objects.create(
    name="Customer Support Email",
    platform="Email",
    config={
        "EMAIL_ADDRESS": "support@example.com",
        "EMAIL_PASSWORD": "your-app-password"
    }
)

# Email Channel - Custom SMTP/IMAP settings
email_channel_custom = Channel.objects.create(
    name="Marketing Email", 
    platform="Email",
    config={
        "EMAIL_ADDRESS": "marketing@example.com",
        "EMAIL_PASSWORD": "password",
        "IMAP_USERNAME": "imap-user@example.com",    # 📧 Optional override for IMAP credentials
        "IMAP_PASSWORD": "imap-password",
        "SMTP_USERNAME": "smtp-user@example.com",    # 📧 Optional override for SMTP credentials
        "SMTP_PASSWORD": "smtp-password",
        "IMAP": {
            "host": "imap.example.com",
            "port": 993,
            "use_ssl": True,
            "protocol": "IMAP"
        },
        "SMTP": {
            "host": "smtp.example.com", 
            "port": 587,
            "use_ssl": True,
            "protocol": "SMTP"
        },
        "TRACKING_PARAMETER_ID": "utm_source",  # 📧 Custom tracking parameter
        "MARK_SEEN_WHEN": "on_request_completed"  # 📧 When to mark emails as seen
    }
)

# Telegram Channel - Auto-generates webhook secret
telegram_channel = Channel.objects.create(
    name="Customer Bot",
    platform="Telegram",
    config={
        "API_TOKEN": "your-bot-token-from-botfather"
    }
)

# WebChat Channel - No configuration needed
webchat_channel = Channel.objects.create(
    name="Customer Support WebChat",
    platform="WebChat"
)

# Validate channel (sets up webhooks/connections)
# Note: WebChat doesn't require validation, automatically active
channel.validate()  # Returns True if successful
```

You can also supply `IMAP_USERNAME`, `IMAP_PASSWORD`, `SMTP_USERNAME`, and `SMTP_PASSWORD`
in the configuration to override the default credentials used for each protocol. When those
keys are absent, Unicom reuses `EMAIL_ADDRESS`/`EMAIL_PASSWORD`.

#### System Email Channel

Built-in workflows such as signup welcomes, password resets, and device transfer notifications send their messages through an Email channel. Control which channel they use via the `SYSTEM_EMAIL_CHANNEL_ID` environment variable:

| Environment Variable      | Description                                                                          | Default                                          |
|---------------------------|--------------------------------------------------------------------------------------|--------------------------------------------------|
| `SYSTEM_EMAIL_CHANNEL_ID` | ID of the Email channel used for system-generated emails sent via `Channel.send_message`. | First active Email channel (smallest ID value). |

When the variable is unset, Unicom automatically picks the earliest active Email channel, so you only need to set it when you want to override the default mailbox.

#### Creating Channels via Admin Interface

1. Go to Django Admin > Unicom > Channels
2. Click "Add Channel"
3. Fill in the name, select platform, and add configuration JSON
4. Save - the channel will automatically validate and set up webhooks

#### Sending Messages with Channels

```python
# ✅ All platforms: Basic message sending
message = channel.send_message({
    'chat_id': 'recipient_chat_id',
    'text': 'Hello from Django Unicom!'
})

# 📧 Email only: New email thread
message = email_channel.send_message({
    'to': ['recipient@example.com'],
    'subject': 'Welcome!',
    'html': '<h1>Welcome to our service!</h1>'
})

# 📧 Email only: Email with CC/BCC
message = email_channel.send_message({
    'to': ['primary@example.com'],
    'cc': ['manager@example.com'],
    'bcc': ['archive@example.com'],
    'subject': 'Team Update',
    'html': '<p>Here is the latest update...</p>'
})

# 📧 Email only: Reply to existing email thread
message = email_channel.send_message({
    'chat_id': 'existing_email_thread_id',
    'html': '<p>Thanks for your message!</p>'
    # Subject is automatically derived from thread
})

# 🌐 WebChat only: Message to web user's chat
message = webchat_channel.send_message({
    'chat_id': 'webchat_abc123def',
    'text': 'Hello! How can I help you today?'
})

# 🌐 WebChat only: Message with image
message = webchat_channel.send_message({
    'chat_id': 'webchat_abc123def',
    'text': 'Here is the information you requested',
    'file_path': '/path/to/image.png'
})

# 📱 Telegram only: Message with interactive buttons
from unicom.services.telegram.create_inline_keyboard import create_callback_button, create_inline_keyboard

# For initial messages, use legacy mode (no message parameter)
# Buttons will work but won't be linked to CallbackExecution
message = telegram_channel.send_message({
    'chat_id': 'user_chat_id',
    'text': 'Choose an option:',
    'reply_markup': create_inline_keyboard([
        [create_callback_button("Confirm", {"action": "confirm"})],
        [create_callback_button("Cancel", {"action": "cancel"})]
    ])
})
# See "Interactive Buttons & Callbacks" section for full details
```

### Message Model

Messages represent individual communications across all platforms with rich metadata and tracking capabilities.

#### Key Message Fields by Platform

The Message model contains many important fields that provide detailed information about message status, tracking, and content. **Important:** Each field is only populated by specific platforms:

```python
from unicom.models import Message

# Content fields (✅ All platforms)
message.text          # Plain text content  
message.sender_name   # Display name of sender
message.timestamp     # When message was created
message.is_outgoing   # True=outgoing, False=incoming, None=system
message.platform      # 'Email', 'Telegram', 'WhatsApp', 'Internal'
message.media_type    # 'text', 'html', 'image', 'audio', 'tool_call', 'tool_response'
message.media         # Attached media file
message.raw           # Raw platform-specific data (JSON)

# 📧 Email-only content fields
message.html          # HTML content
message.subject       # Email subject line  
message.to            # List of recipient email addresses (array)
message.cc            # List of CC email addresses (array)
message.bcc           # List of BCC email addresses (array)
message.imap_uid      # IMAP UID for server operations

# 💬 WhatsApp-only status tracking
message.sent          # Updated when WhatsApp confirms message sent
message.delivered     # Updated when WhatsApp confirms message delivered
message.seen          # Updated when WhatsApp confirms message read
message.time_sent     # When WhatsApp confirmed message sent
message.time_delivered # When WhatsApp confirmed message delivered  
message.time_seen     # When WhatsApp confirmed message read

# 📧 Email-only tracking (via tracking pixels & links)
message.opened        # Set to True when recipient opens email
message.time_opened   # When email was first opened (via tracking pixel)
message.link_clicked  # Set to True when any tracked link is clicked
message.time_link_clicked # When first link was clicked
message.clicked_links # Array of all URLs that have been clicked
message.tracking_id   # UUID used for tracking pixel and link tracking
```

#### Platform-Specific Usage Examples

```python
# 💬 WhatsApp: Check delivery status (only WhatsApp provides this data)
whatsapp_msg = Message.objects.get(id='whatsapp_message_id')
if whatsapp_msg.delivered:
    print(f"WhatsApp message delivered at: {whatsapp_msg.time_delivered}")
if whatsapp_msg.seen:
    print(f"WhatsApp message read at: {whatsapp_msg.time_seen}")

# 📧 Email: Check tracking data (only emails have open/click tracking)  
email_msg = Message.objects.get(id='email_message_id')
if email_msg.opened:
    print(f"Email opened at: {email_msg.time_opened}")
if email_msg.link_clicked:
    print(f"Links clicked: {email_msg.clicked_links}")
    print(f"First click at: {email_msg.time_link_clicked}")

# ✅ All platforms: Basic message info
for message in Message.objects.filter(channel=channel):
    print(f"{message.platform}: {message.sender_name} - {message.text}")
    if message.is_outgoing:
        print("  (Outgoing message)")
    elif message.is_outgoing is False:
        print("  (Incoming message)")  
    else:
        print("  (System message)")

# 💬 WhatsApp-specific queries
unread_whatsapp = Message.objects.filter(
    platform='WhatsApp',
    is_outgoing=True,
    seen=False  # Only WhatsApp populates this field
)

# 📧 Email-specific queries  
opened_emails = Message.objects.filter(
    platform='Email',
    opened=True  # Only emails have open tracking
)

clicked_emails = Message.objects.filter(
    platform='Email', 
    link_clicked=True  # Only emails have click tracking
).values('subject', 'clicked_links', 'time_link_clicked')
```

#### Understanding Field Limitations

**Important Notes:**
- **Delivery tracking** (`delivered`, `time_delivered`): Only WhatsApp provides delivery confirmations
- **Read tracking** (`seen`, `time_seen`): Only WhatsApp provides read receipts  
- **Email open tracking** (`opened`, `time_opened`): Only works when recipient loads images/tracking pixels
- **Email click tracking** (`link_clicked`, `time_link_clicked`, `clicked_links`): Only works for links that go through tracking system
- **Email "seen" status**: Use `imap_uid` field and IMAP operations, not the `seen` field

#### Accessing Messages

```python
from unicom.models import Message

# Get message by ID
message = Message.objects.get(id='message_id')

# Get recent messages for a channel
recent_messages = Message.objects.filter(
    channel=channel
).order_by('-timestamp')[:10]

# Get conversation history
chat_messages = Message.objects.filter(
    chat_id='chat_id'
).order_by('timestamp')
```

#### Replying to Messages

```python
# ✅ All platforms: Reply with text
reply = message.reply_with({
    'text': 'Thanks for your message!'
})

# 📧 Email only: Reply with HTML
reply = message.reply_with({
    'html': '<p>Thank you for contacting us!</p><p>We will get back to you soon.</p>'
})

# ✅ All platforms: Reply with media
reply = message.reply_with({
    'text': 'Here is the file you requested',
    'file_path': '/path/to/file.pdf'
})

# 📱 Telegram only: Reply with interactive buttons
from unicom.services.telegram.create_inline_keyboard import create_inline_keyboard, create_callback_button

reply = message.reply_with({
    'text': 'Would you like to continue?',
    'reply_markup': create_inline_keyboard([
        [create_callback_button("Yes", {"action": "continue", "value": True}, message=message)],
        [create_callback_button("No", {"action": "continue", "value": False}, message=message)]
    ])
})
# See "Interactive Buttons & Callbacks" section for handling button clicks
```

#### Via Admin Interface

1. Go to Django Admin > Unicom > Messages  
2. Find the message you want to reply to
3. Click on the message ID to open details
4. Use the "Reply" button in the interface
5. Compose your reply using the rich text editor (📧 email) or plain text

### Chat Model

Chats represent conversations/threads across platforms.

#### Working with Chats

```python
from unicom.models import Chat

# Get chat by ID
chat = Chat.objects.get(id='chat_id')

# Send message to chat
message = chat.send_message({
    'text': 'Hello everyone!'
})

# 📧 Email only: Reply to last incoming message in email thread
reply = chat.send_message({
    'html': '<p>Following up on our previous conversation...</p>'
})

# Reply to specific message in chat
reply = chat.send_message({
    'reply_to_message_id': 'specific_message_id',
    'text': 'Replying to your specific question...'
})
```

### Template System

Create reusable message templates for consistent communication, and optionally render Jinja-style template variables for richer personalization.

#### Creating Templates Programmatically

```python
from unicom.models import MessageTemplate

# Create a basic template
template = MessageTemplate.objects.create(
    title='Welcome Email',
    content='<h1>Welcome {{name}}!</h1><p>Thank you for joining {{company}}.</p>',
    category='Onboarding'
)

# Make template available for specific channels
template.channels.add(email_channel)
template.channels.add(telegram_channel)

# 🤖 AI-powered template population (requires OpenAI API key)
populated_content = template.populate(
    html_prompt="User name is John Doe, company is Acme Corp",
    model="gpt-4"
)
```

#### Creating Templates via Admin Interface

1. Go to Django Admin > Unicom > Message Templates
2. Click "Add Message Template" 
3. Fill in title, description, category
4. Create your HTML content using TinyMCE editor (📧 email templates get rich editor)
5. Select which channels can use this template
6. Save template

#### Using Templates in Messages

```python
# Get template and use its content
template = MessageTemplate.objects.get(title='Welcome Email')

# Use template content directly
message = channel.send_message({
    'to': ['newuser@example.com'],
    'subject': 'Welcome!', 
    'html': template.content.replace('{{name}}', 'John Doe')
})

# Or use AI population
populated = template.populate("User is John Doe from Acme Corp")
message = channel.send_message({
    'to': ['john@acme.com'],
    'subject': 'Welcome!',
    'html': populated
})
```

#### Template Variables & Rendering

There are two layers of templating:
- **Unicom rendering (standalone messages):** Jinja2 rendering with a safe Unicom context. It is used automatically for ad-hoc/admin email compose and scheduled drafts. Context exposed to templates: `message` (subject/html/text/to/cc/bcc/attachments/chat_id/reply_to_message_id/timestamp), `channel` (id/name/platform), and `sender` (id/username/email when available). You can add more by passing `render_variables` (merged into `variables.*`) or `render_context` when calling `channel.send_message`.
- **Unicrm rendering (mass-mail):** Jinja2 rendering with CRM data. Context exposed: `contact` (and nested `company`, `subscriptions`), `communication`, and `variables` (all active CRM TemplateVariables), plus `variables.unsubscribe_link` (HTML link) when a Communication is provided. This path is unchanged and remains tied to CRM mailings.

Using variables in templates (applies to both renderers):
```html
<h1>Hello {{ variables.first_name }}</h1>
<p>You’re receiving this on {{ now()|datetime("%Y-%m-%d") }}</p>
```

Creating CRM TemplateVariables (only available in CRM Communications):
```python
from unicrm.models import TemplateVariable

TemplateVariable.objects.create(
    key="contact_first_name",
    label="Contact first name",
    description="Returns the contact's first name",
    code="""
def compute(contact):
    return (contact.first_name or '').strip() or 'there'
""",
    is_active=True,
)
```
The callable must be `compute(contact)` and can access `contact`, `contact.company`, and helpers like `build_unsubscribe_link` (for unsubscribe variables). Values become available as `{{ variables.contact_first_name }}` in CRM emails.

Opting into rendering for custom sends (programmatic):
```python
channel.send_message({
    'to': ['a@example.com'],
    'subject': 'Hello',
    'html': '<p>Hello {{ variables.name }}</p>',
    'render_template': True,                 # enable rendering (admin email compose & scheduled drafts set this for you)
    'render_variables': {'name': 'Alice'},   # merged into variables.*
    # Optionally pass a custom render_context if you want to add more fields
})
```
If you omit `render_template`/context/variables, the HTML is sent as-is. The Django admin email composer and scheduled drafts already enable rendering by default; you only need to pass the flag when sending programmatically.

### Draft Messages & Scheduling

Create draft messages and schedule them for later sending.

#### Creating Draft Messages

```python
from unicom.models import DraftMessage
from django.utils import timezone

# Create a scheduled email
draft = DraftMessage.objects.create(
    channel=email_channel,
    to=['customer@example.com'],
    subject='Weekly Newsletter', 
    html='<h1>This week\'s updates...</h1>',
    send_at=timezone.now() + timezone.timedelta(hours=24),
    is_approved=True,
    status='scheduled'
)

# Create a Telegram draft  
telegram_draft = DraftMessage.objects.create(
    channel=telegram_channel,
    chat_id='telegram_chat_id',
    text='Scheduled announcement for tomorrow',
    send_at=timezone.now() + timezone.timedelta(days=1),
    is_approved=True,
    status='scheduled'
)

# Send draft immediately (if approved and time has passed)
sent_message = draft.send()
```

#### Creating Drafts via Admin Interface

1. Go to Django Admin > Unicom > Draft Messages
2. Click "Add Draft Message"
3. Select channel and fill in recipient details
4. Compose message content
5. Set "Send at" time for scheduling
6. Mark as "Approved" when ready to send  
7. Status will automatically update to "Scheduled"

---

## 🚀 Advanced Features

### Email-Specific Features

#### 📧 Link Tracking

Email channels automatically track which links recipients click:

```python
# Send email with trackable links
message = email_channel.send_message({
    'to': ['user@example.com'], 
    'subject': 'Check out our new features',
    'html': '''
        <p>Visit our <a href="https://example.com/features">features page</a></p>
        <p>Or check the <a href="https://example.com/docs">documentation</a></p>
    '''
})

# Check tracking data later
if message.link_clicked:
    print(f"First link clicked at: {message.time_link_clicked}")
    print(f"Clicked links: {message.clicked_links}")

if message.opened:
    print(f"Email opened at: {message.time_opened}")
```

#### 📧 Rich HTML Content with TinyMCE

The admin interface provides a rich text editor for composing HTML emails with features like:
- Font formatting, colors, styles
- Image uploads and inline images
- Tables, lists, links
- Template insertion
- AI-powered content generation

#### 📧 DKIM and SPF Verification

Email channels automatically validate DKIM and SPF records for incoming messages, ensuring email authenticity and preventing spoofing.

#### 📧 Pre-Send Email Validation (Reacher)

If you run a Reacher instance alongside Unicom you can block known-bad addresses before the SMTP hand-off. Configure it through environment variables loaded into `settings.py`. When embedding Unicom inside your own Django project, drop the following snippet (taken from `unicom_project/settings.py`) into your project's settings file so the values become available on `django.conf.settings`:

```python
# Optional Reacher email verification configuration
REACHER_BASE_URL = (
    os.environ.get('REACHER_BASE_URL')
    or os.environ.get('REACHER_HOSTNAME')
    or os.environ.get('REACHER_HOST')
)
REACHER_STRICTNESS = (os.environ.get('REACHER_STRICTNESS') or 'strict').lower()
```

- `REACHER_HOSTNAME` *(or `REACHER_BASE_URL`)* – Base URL of the Reacher API. Leaving it unset disables validation.
- `REACHER_STRICTNESS` – Controls which Reacher classifications still go out. Options:
  - `strict` *(default)*: only `"safe"` addresses are sent.
  - `moderate`: allows `"safe"` and `"risky"` addresses.
  - `lenient`: allows `"safe"`, `"risky"` and `"unknown"` addresses.

When Reacher denies an address the Message is stored as bounced with the raw payload under `message.raw["reacher_validation"]` so operators can review the decision without resending.

### Telegram-Specific Features

#### 📱 Typing Indicators

```python
from unicom.services.telegram import start_typing_in_telegram, stop_typing_in_telegram

# Show typing indicator
start_typing_in_telegram(telegram_channel, chat_id="telegram_chat_id")

# Your processing logic here
import time
time.sleep(2)

# Stop typing and send message  
stop_typing_in_telegram(telegram_channel, chat_id="telegram_chat_id")
message = telegram_channel.send_message({
    'chat_id': 'telegram_chat_id',
    'text': 'Here is your response!'
})
```

#### 🌐 Interactive Messages with Action Buttons (Cross-Platform)

Interactive buttons work across **Telegram and WebChat** with the same API. Pass any JSON-serializable `callback_data`:

```python
# ✅ Cross-platform: Works on both Telegram and WebChat
message.reply_with({
    'text': 'Do you want to continue?',
    'buttons': [
        [
            {"text": "Yes", "callback_data": {"action": "confirm"}, "type": "callback"},
            {"text": "No", "callback_data": {"action": "cancel"}, "type": "callback"}
        ],
        [
            {"text": "Visit Website", "url": "https://example.com", "type": "url"}
        ]
    ]
})

# Rich data structures with any JSON-serializable data
message.reply_with({
    'text': 'Choose a product:',
    'buttons': [
        [
            {"text": "Product A", "callback_data": {"product_id": 123, "price": 29.99}, "type": "callback"},
            {"text": "Product B", "callback_data": {"product_id": 456, "price": 49.99}, "type": "callback"}
        ]
    ]
})

# 📱 Telegram-specific (legacy): Still supported for Telegram-only code
from unicom.services.telegram.create_inline_keyboard import create_inline_keyboard, create_callback_button

incoming_message.reply_with({
    'text': 'Telegram-specific buttons:',
    'reply_markup': create_inline_keyboard([
        [create_callback_button("Yes", {"action": "confirm"}, message=incoming_message)]
    ])
})

incoming_message.reply_with({
    'text': 'Limited time offer!',
    'reply_markup': create_inline_keyboard([
        [create_callback_button(
            "Claim Offer",
            {"offer_id": 789, "discount": 0.5},
            message=incoming_message,
            expires_at=timezone.now() + timedelta(hours=24)
        )]
    ])
})
```

#### 🌐 Handling Button Clicks (Cross-Platform)

When users click buttons, handle them with Django signals - **works for both Telegram and WebChat automatically**:

```python
from django.dispatch import receiver
from unicom.signals import telegram_callback_received

@receiver(telegram_callback_received)  # Handles BOTH Telegram AND WebChat clicks!
def handle_button_clicks(sender, callback_execution, clicking_account, original_message, tool_call, **kwargs):
    """
    Handle button clicks from any platform.

    Args:
        callback_execution: CallbackExecution instance with callback_data
        clicking_account: The unicom.Account that clicked the button
        original_message: The Message containing the buttons
        tool_call: Optional ToolCall if button was from a tool (None otherwise)

    Note: unicom.Account represents a platform user (e.g., Telegram user, WebChat session).
    To access Django auth.User: clicking_account.member.user (if member exists)
    """
    data = callback_execution.callback_data

    # Handle dict callback_data
    if isinstance(data, dict):
        if data.get('action') == 'confirm':
            process_confirmation(clicking_account)
            original_message.reply_with({'text': '✅ Confirmed!'})

        elif data.get('action') == 'buy_product':
            product_id = data['product_id']
            product = get_product(product_id)

            # Create new buttons - works on both platforms
            original_message.reply_with({
                'text': f'Product: {product.name}\nPrice: ${product.price}',
                'buttons': [
                    [
                        {"text": "Confirm Purchase", "callback_data": {"action": "confirm_purchase", "product_id": product_id}, "type": "callback"},
                        {"text": "Cancel", "callback_data": {"action": "cancel"}, "type": "callback"}
                    ]
                ]
            })
                    [create_callback_button('Cancel', {'action': 'cancel'}, message=original_message, account=clicking_account)]
                ])
            })

    # Handle string callback_data
    elif data == 'cancel':
        original_message.reply_with({'text': '❌ Cancelled'})

    # Access Django User if needed
    if clicking_account.member and clicking_account.member.user:
        django_user = clicking_account.member.user
        # Do something with django_user

    # If button was from a tool, you can respond to the tool call
    if tool_call and data.get('action') == 'confirm':
        # Inform the LLM that the user confirmed
        tool_call.respond({'confirmed': True, 'user_id': clicking_account.id})
```

**Where to put your callback handler:**

Create a file like `your_app/callback_handlers.py` and import it in your app's `apps.py`:

```python
# your_app/apps.py
from django.apps import AppConfig

class YourAppConfig(AppConfig):
    name = 'your_app'

    def ready(self):
        import your_app.callback_handlers  # Register signal handlers
```

Make sure your app is in `INSTALLED_APPS` in settings.py.

**Key Features:**

- **Flexible Data**: Store any JSON-serializable data (dict, list, str, int, bool, None)
- **Security**: Only the intended account can click the button
- **Expiration**: Optional `expires_at` parameter for time-limited buttons
- **Reusable**: Buttons can be clicked multiple times (developers control behavior)
- **Efficient**: Callback data stored in DB, only ID sent to Telegram
- **No Message Creation**: Button clicks don't create Message objects - they only trigger handlers
- **Tool Integration**: When buttons are from tools, handlers can use `tool_call.respond()` to inform the LLM

#### 🌐 Tool-Generated Buttons (Cross-Platform)

Tools can create interactive buttons that work on both Telegram and WebChat:

```python
# In your tool code (e.g., unibot Tool model)
def my_interactive_tool(question: str) -> str:
    """Ask user a question with buttons and wait for response."""

    # Send cross-platform message with buttons
    message.reply_with({
        'text': f'Question: {question}',
        'buttons': [
            [
                {"text": "Yes", "callback_data": {"tool": "my_interactive_tool", "action": "answer", "value": "yes"}, "type": "callback"},
                {"text": "No", "callback_data": {"tool": "my_interactive_tool", "action": "answer", "value": "no"}, "type": "callback"}
            ]
        ]
    })

    # Return None to prevent duplicate messages
    return None

# 📱 Telegram-specific (legacy): Still supported
def my_telegram_tool(question: str) -> str:
    message.reply_with({
        'text': f'Question: {question}',
        'reply_markup': create_inline_keyboard([
            [create_callback_button(
                "Yes",
                {"tool": "my_interactive_tool", "action": "answer", "value": "yes"},
                message=message,
                tool_call=tool_call  # Links to ToolCall for LLM response
            )]
        ])
    })
    return None
                {"tool": "my_interactive_tool", "action": "answer", "value": "no"},
                message=message,
                tool_call=tool_call
            )]
        ])
    })

    # Return None to defer response - tool will respond when user clicks
    return None

# In your callback handler (callback_handlers.py)
@receiver(telegram_callback_received)
def handle_tool_buttons(sender, callback_execution, clicking_account, original_message, tool_call, **kwargs):
    data = callback_execution.callback_data

    # Route to correct handler based on tool name
    if isinstance(data, dict) and data.get('tool') == 'my_interactive_tool':
        if data.get('action') == 'answer':
            # User clicked a button from the tool
            answer = data['value']

            # Respond to the tool call - this will notify the LLM
            if tool_call:
                tool_call.respond({
                    'question_answered': True,
                    'answer': answer,
                    'user_id': clicking_account.id
                })

            # Also send confirmation to user
            original_message.reply_with({
                'text': f'✅ You answered: {answer}'
            })
```

#### 📱 Button Routing Best Practices

When building applications with multiple button types, use a consistent routing strategy:

**Recommended Pattern: Use a "type" or "handler" field**

```python
# Define button types as constants for consistency
BUTTON_TYPES = {
    'PRODUCT': 'product_handler',
    'NAVIGATION': 'nav_handler',
    'SETTINGS': 'settings_handler',
    'TOOL': 'tool_handler'
}

# Create buttons with type field
create_callback_button(
    "Buy Product A",
    {
        "type": "product_handler",  # Routes to product handler
        "action": "buy",
        "product_id": 123
    },
    message=message
)

create_callback_button(
    "Settings",
    {
        "type": "settings_handler",  # Routes to settings handler
        "action": "show_settings"
    },
    message=message
)

# In your callback handler - route based on type
@receiver(telegram_callback_received)
def handle_all_buttons(sender, callback_execution, clicking_account, original_message, tool_call, **kwargs):
    data = callback_execution.callback_data

    if not isinstance(data, dict):
        return  # Skip non-dict data

    # Route to appropriate handler based on type
    handler_type = data.get('type')

    if handler_type == 'product_handler':
        handle_product_buttons(data, clicking_account, original_message)
    elif handler_type == 'settings_handler':
        handle_settings_buttons(data, clicking_account, original_message)
    elif handler_type == 'tool_handler':
        handle_tool_buttons(data, clicking_account, original_message, tool_call)
    else:
        # Unknown type - log or handle gracefully
        print(f"Unknown button type: {handler_type}")

def handle_product_buttons(data, account, message):
    """Handle product-related button clicks"""
    if data.get('action') == 'buy':
        product_id = data['product_id']
        # Process purchase...
        message.reply_with({'text': f'Processing purchase for product {product_id}'})

def handle_settings_buttons(data, account, message):
    """Handle settings-related button clicks"""
    if data.get('action') == 'show_settings':
        # Show settings menu...
        message.edit_original_message({'text': '⚙️ Settings Menu'})

def handle_tool_buttons(data, account, message, tool_call):
    """Handle tool-generated button clicks"""
    if tool_call and data.get('action') == 'confirm':
        tool_call.respond({'confirmed': True})
        message.reply_with({'text': '✅ Confirmed'})
```

**Alternative Pattern: Multiple Signal Receivers**

```python
# Register separate handlers for different button types
@receiver(telegram_callback_received)
def handle_product_buttons(sender, callback_execution, **kwargs):
    data = callback_execution.callback_data
    # Only handle product buttons
    if isinstance(data, dict) and data.get('type') == 'product':
        # Handle product actions...
        pass

@receiver(telegram_callback_received)
def handle_navigation_buttons(sender, callback_execution, **kwargs):
    data = callback_execution.callback_data
    # Only handle navigation buttons
    if isinstance(data, dict) and data.get('type') == 'nav':
        # Handle navigation...
        pass
```

**Scalable Data Structure Example:**

```python
# Well-structured callback data for complex applications
callback_data = {
    "type": "product_handler",      # Routes to correct handler
    "action": "add_to_cart",        # Specific action
    "entity_type": "product",       # Type of entity
    "entity_id": 123,               # Entity identifier
    "metadata": {                   # Additional context
        "source": "search_results",
        "page": 2
    }
}
```


#### 📱 Editing Telegram Messages

Telegram allows you to edit messages in place instead of sending new ones:

```python
# Edit a message you sent
message = telegram_channel.send_message({
    'chat_id': 'user_chat_id',
    'text': 'Processing your request...'
})

# Later, update the same message
from unicom.services.telegram.edit_telegram_message import edit_telegram_message
edit_telegram_message(telegram_channel, message, {
    'text': '✅ Request completed!'
})

# Edit messages with buttons (common in callback handlers)
from django.dispatch import receiver
from unicom.signals import telegram_callback_received
from unicom.services.telegram.create_inline_keyboard import create_inline_keyboard, create_callback_button

@receiver(telegram_callback_received)
def handle_navigation(sender, callback_execution, clicking_account, original_message, tool_call, **kwargs):
    button_data = callback_execution.callback_data

    if button_data == 'show_settings':
        # Edit the original message to show settings
        original_message.edit_original_message({
            'text': '⚙️ Settings Menu',
            'reply_markup': create_inline_keyboard([
                [create_callback_button("Account", "settings_account", message=original_message, account=clicking_account)],
                [create_callback_button("Privacy", "settings_privacy", message=original_message, account=clicking_account)],
                [create_callback_button("🔙 Back", "main_menu", message=original_message, account=clicking_account)]
            ])
        })
```

**Common use cases:**
- Updating status messages (e.g., "Processing..." → "Complete!")
- Creating navigation menus that update in place
- Building interactive forms without spamming the chat
- Showing real-time progress updates

#### 📱 File Downloads and Voice Messages

Telegram channels automatically handle file downloads and voice message processing:

```python
# Voice messages are automatically converted to compatible formats
# and can be processed by LLM services
if message.media_type == 'audio':
    # Voice message is available in message.media
    # Converted to MP3 format for compatibility
    llm_response = message.reply_using_llm(
        model="gpt-4-vision-preview",
        multimodal=True  # Enables audio processing
    )
```

### WebChat-Specific Features

#### 🌐 Web-Based Chat Interface

WebChat provides a ChatGPT/Claude-like web interface for your Django application with support for both authenticated and guest users.

**Key Features:**
- 💬 Multi-chat support - Users can create unlimited separate conversations
- 👤 Hybrid authentication - Works for both Django authenticated users and guest sessions
- 📱 Mobile-responsive - Sidebar collapses on mobile devices
- 🔄 Auto-refresh - Polls for new messages every 5 seconds (configurable)
- 📎 Media uploads - Images and audio files
- 🎨 Customizable theming - CSS custom properties for colors and styling
- 🔐 Secure - Access control, CSRF protection, isolated chats
- 🔄 Guest migration - Guest chat history preserved when logging in

#### 🌐 Setting Up WebChat

**1. Create a WebChat Channel:**

```python
from unicom.models import Channel

# Create WebChat channel (no configuration needed)
webchat_channel = Channel.objects.create(
    name="Customer Support WebChat",
    platform="WebChat"
)

# Channel is automatically active, no validation needed
```

**2. Embed in Your Django Template:**

```django
{% load static %}

<!DOCTYPE html>
<html>
<head>
    <title>Customer Support Chat</title>
</head>
<body>
    <h1>Need Help?</h1>

    <!-- Import LitElement from CDN -->
    <script type="importmap">
    {
        "imports": {
            "lit": "https://cdn.jsdelivr.net/npm/lit@3.2.0/+esm",
            "lit/directives/unsafe-html.js": "https://cdn.jsdelivr.net/npm/lit@3.2.0/directives/unsafe-html.js/+esm"
        }
    }
    </script>

    <!-- Load WebChat component -->
    <script type="module" src="{% static 'unicom/webchat/webchat-with-sidebar.js' %}"></script>

    <!-- Embed chat interface -->
    <unicom-chat-with-sidebar
        api-base="/unicom/webchat"
        theme="light"
        max-messages="50"
        auto-refresh="5"
        style="height: 700px;">
    </unicom-chat-with-sidebar>
</body>
</html>
```

**3. Access the Demo Page:**

When `DEBUG=True`, visit `/unicom/webchat/demo/` to see the interactive demo with multiple theme examples.

#### 🌐 WebChat Component Options

The `<unicom-chat-with-sidebar>` component accepts these attributes:

- **`api-base`**: API endpoint base URL (default: `/unicom/webchat`)
- **`channel-id`**: Target a specific WebChat channel (optional; defaults to the first active WebChat channel)
- **`theme`**: `"light"` or `"dark"` (default: `"light"`)
- **`max-messages`**: Max messages to load per chat (default: 50)
- **`auto-refresh`**: Polling interval in seconds (default: 5, set to 0 to disable)
- **`disable-websocket`**: Force HTTP polling only (default: false)
- **`enable-websocket-only`**: Force WebSocket only with retry on failure (default: false)

**WebSocket Connection Modes:**

```html
<!-- Default: Try WebSocket first, fallback to polling if it fails -->
<unicom-chat-with-sidebar api-base="/unicom/webchat"></unicom-chat-with-sidebar>

<!-- WebSocket-only: Retry with exponential backoff, never fallback to polling -->
<unicom-chat-with-sidebar 
    api-base="/unicom/webchat" 
    channel-id="123" 
    enable-websocket-only="true">
</unicom-chat-with-sidebar>

<!-- Polling-only: Never attempt WebSocket connection -->
<unicom-chat-with-sidebar 
    api-base="/unicom/webchat" 
    disable-websocket="true">
</unicom-chat-with-sidebar>
```

**Customization via CSS Custom Properties:**

```html
<unicom-chat-with-sidebar
    theme="dark"
    style="
        height: 800px;
        --unicom-primary-color: #ff5722;
        --unicom-background-color: #1e1e1e;
        --unicom-border-radius: 16px;
        --unicom-message-bg-outgoing: #ff5722;
        --unicom-message-text-outgoing: #ffffff;
    ">
</unicom-chat-with-sidebar>
```

Available CSS variables:
- `--unicom-primary-color` - Primary brand color (default: #007bff)
- `--unicom-secondary-color` - Secondary color for subtle text (default: #6c757d)
- `--unicom-background-color` - Main background color (default: #ffffff)
- `--unicom-text-color` - Primary text color (default: #212529)
- `--unicom-border-color` - Border color (default: #dee2e6)
- `--unicom-border-radius` - Component border radius (default: 0px)
- `--unicom-bubble-radius` - Message bubble border radius (default: 16px)
- `--unicom-control-radius` - Input controls border radius (default: 12px)
- `--unicom-media-radius` - Media files border radius (default: 12px)
- `--unicom-message-bg-incoming` - Incoming message background (default: #f1f3f4)
- `--unicom-message-bg-outgoing` - Outgoing message background (default: #007bff)
- `--unicom-message-text-incoming` - Incoming message text color (default: #212529)
- `--unicom-message-text-outgoing` - Outgoing message text color (default: #ffffff)
- `--unicom-scrollbar-track` - Scrollbar track color (default: rgba(0, 0, 0, 0.04))
- `--unicom-scrollbar-thumb` - Scrollbar thumb color (default: rgba(0, 0, 0, 0.18))
- `--unicom-sidebar-bg` - Sidebar background color (default: same as background)
- `--unicom-sidebar-border-color` - Sidebar border color (default: same as border)
- `--unicom-sidebar-text-color` - Sidebar text color (default: same as text)
- `--unicom-sidebar-secondary-text` - Sidebar secondary text color (default: same as secondary)
- `--unicom-sidebar-header-bg` - Sidebar header background (default: same as primary)
- `--unicom-sidebar-header-text` - Sidebar header text color (default: #ffffff)
- `--unicom-sidebar-item-border` - Sidebar item border color (default: same as border)
- `--unicom-sidebar-item-hover` - Sidebar item hover background (default: rgba(0, 0, 0, 0.03))
- `--unicom-sidebar-item-selected` - Selected sidebar item background (default: same as primary)
- `--unicom-sidebar-item-selected-text` - Selected sidebar item text color (default: #ffffff)
- `--unicom-sidebar-item-selected-subtext` - Selected sidebar item subtext color (default: rgba(255, 255, 255, 0.8))
- `--unicom-font-family` - Font family (default: system fonts)

#### 🌐 WebChat User Types

**Authenticated Users:**
```python
# For logged-in Django users, account ID is based on user.id
# Account ID format: webchat_user_{user.id}
# Chats are permanently linked to the user account
```

**Guest Users:**
```python
# For anonymous users, account ID is based on session key
# Account ID format: webchat_guest_{session_key}
# Chat history is preserved if user logs in later via automatic migration
```

#### 🌐 Programmatic WebChat Usage

```python
from unicom.models import Channel, Message

# Get WebChat channel
channel = Channel.objects.get(platform='WebChat')

# Send message to a specific chat
channel.send_message({
    'chat_id': 'webchat_abc123def',
    'text': 'Hello! How can I help you today?'
})

# Send message with image
channel.send_message({
    'chat_id': 'webchat_abc123def',
    'text': 'Here is the information you requested',
    'file_path': '/path/to/image.png'
})

# Reply to a message
message = Message.objects.get(id='message_id')
message.reply_with({
    'text': 'Thanks for reaching out! We will get back to you shortly.'
})
```

#### 🌐 WebChat API Endpoints

The WebChat system provides REST APIs for the frontend:

**Send Message:**
```
POST /unicom/webchat/send/
Body: text, chat_id (optional), media (file upload, optional)
```

**Get Messages:**
```
GET /unicom/webchat/messages/?chat_id=<chat_id>&limit=50&before=<message_id>&after=<message_id>
```

**List Chats:**
```
GET /unicom/webchat/chats/
```

**Update Chat (Rename/Archive):**
```
PATCH /unicom/webchat/chat/<chat_id>/
Body: title (optional), is_archived (optional)
```

**Delete Chat:**
```
DELETE /unicom/webchat/chat/<chat_id>/delete/?hard_delete=true
```

#### 🌐 Multi-Chat Features

WebChat supports unlimited separate conversations per user:

```javascript
// Users can:
// - Create new chats by clicking "New Chat" button
// - Switch between chats via sidebar
// - Each chat has isolated message history
// - Chats get auto-generated titles from first message
// - Rename chats via API
// - Archive or delete chats via API
```

**Chat Title Auto-Generation:**
```python
# When user sends first message: "Hello, I need help with my account"
# Chat title is auto-generated: "I need help with my account"
# Skips common greetings (hello, hi, hey)
# Truncates to 50 characters with "..."
```

#### 🌐 Custom Filtration (Project-Based Chats)

WebChat supports custom filtration for scenarios where chats need to be scoped to specific contexts (e.g., projects, departments, workspaces).

**Use Case Examples:**
- Project management app: Users see only chats related to current project
- Multi-tenant SaaS: Filter chats by tenant/organization
- Department-specific support: Sales vs Engineering support chats
- Customer segmentation: VIP vs regular customer chat queues

**Implementation:**

1. **Add metadata when creating a chat:**

```javascript
// Frontend: Create a chat with project_id metadata
const response = await api.sendMessage(
  'Hello, I need help with this project',
  null,  // No chat_id = new chat
  null,  // No media file
  { project_id: 123, department: 'engineering' }  // Custom metadata
);
```

```python
# Backend: Create a chat with metadata programmatically
from unicom.models import Chat

chat = Chat.objects.create(
    id=f"webchat_{uuid.uuid4()}",
    platform='WebChat',
    channel=channel,
    metadata={
        'project_id': 123,
        'department': 'engineering',
        'priority': 'high'
    }
)
```

2. **Filter chats by metadata:**

```javascript
// Frontend: Get only chats for current project
const client = new RealTimeWebChatClient('/unicom/webchat');
client.setFilters({
  'metadata__project_id': 123,
  'is_archived': false
});
await client.connect();

// Or setup the component to only show chats with project_id=62 and set project_id=62 when creating new chats:
<unicom-chat-with-sidebar
    api-base="/unicom/webchat"
    filters="{&quot;metadata__project_id&quot;:62}"
    metadata-defaults="{&quot;project_id&quot;:62}">
</unicom-chat-with-sidebar>
```

```python
# Backend/API: Filter chats by metadata
GET /unicom/webchat/chats/?metadata__project_id=123&metadata__department=engineering
```

3. **Advanced filtering with Django lookups:**

```python
# Filter with comparison operators
GET /unicom/webchat/chats/?metadata__priority__gte=5  # Priority >= 5
GET /unicom/webchat/chats/?metadata__status=active&is_archived=false

# Combine multiple filters
GET /unicom/webchat/chats/?metadata__project_id=123&metadata__team=alpha
```

**Custom Filtration in WebSocket Consumer:**

```javascript
// When using WebSockets, filters are applied automatically
const client = new RealTimeWebChatClient('/unicom/webchat');
client.setFilters({ metadata__project_id: currentProjectId });
client.connect();

// Real-time updates will only show chats matching the filter
client.onChatsUpdate = (chats) => {
  console.log('Chats for project:', chats);
};
```

**Changing Filters Dynamically:**

```javascript
// Example: When user switches projects
function onProjectChange(newProjectId) {
  client.setFilters({ metadata__project_id: newProjectId });
  // Re-fetch chats with new filter
  const chats = await client.getChats();
  updateUI(chats);
}
```

**Available Filter Patterns:**

- **Exact match**: `metadata__key=value`
- **Greater than or equal**: `metadata__key__gte=value`
- **Less than or equal**: `metadata__key__lte=value`
- **Contains (string)**: `metadata__key__icontains=text`
- **Standard Chat fields**: `is_archived=false`, `name__icontains=support`

**Metadata Field Types:**

The `metadata` JSONField supports any JSON-serializable data:

```python
chat.metadata = {
    'project_id': 123,           # Integer
    'department': 'sales',       # String
    'is_urgent': True,           # Boolean
    'priority': 8.5,             # Float
    'tags': ['support', 'bug'],  # Array
    'custom_data': {             # Nested object
        'customer_tier': 'premium',
        'assigned_agent': 'john@example.com'
    }
}
```

#### 🌐 Real-Time Updates (WebSocket Support)

WebChat supports **optional** real-time updates via Django Channels. If Channels is not installed, the system automatically falls back to polling.

**Installation (Optional):**

```bash
pip install channels channels-redis
```

**Configuration in settings.py:**

```python
INSTALLED_APPS = [
    'channels',  # Keep this before Django's default apps so its runserver takes over
    ...
]

ASGI_APPLICATION = 'your_project.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [('127.0.0.1', 6379)],
        },
    },
}
```

**Configure WebSocket routing:**

```python
# your_project/asgi.py
import os
from django.core.asgi import get_asgi_application

try:
    from channels.auth import AuthMiddlewareStack
    from channels.routing import ProtocolTypeRouter, URLRouter
    from django.urls import path
    from django.conf import settings
    from unicom.consumers import WebChatConsumer
except ImportError:
    # Channels not installed – fall back to standard ASGI application.
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
    application = get_asgi_application()
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
    http_app = get_asgi_application()
    if settings.DEBUG:
        from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
        http_app = ASGIStaticFilesHandler(http_app)

    websocket_urlpatterns = [
        path("ws/unicom/webchat/<str:chat_id>/", WebChatConsumer.as_asgi()),
        path("ws/unicom/webchat/<str:chat_id>", WebChatConsumer.as_asgi()),  # optional trailing slash
    ]

    application = ProtocolTypeRouter({
        "http": http_app,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    })
```

> **Why the chat_id segment?**  
> Each WebSocket connection is scoped to a single chat. The consumer validates the
> authenticated (or guest) account against that chat and streams new messages as they
> arrive. Existing REST endpoints are still used for loading history and sending new
> messages.

> **Using the in-memory channel layer?**  
> For quick demos you can skip Redis entirely and point `CHANNEL_LAYERS['default']['BACKEND']`
> to `'channels.layers.InMemoryChannelLayer'`—this is exactly how `unicom_project/settings.py`
> is configured when Channels is installed.

**How It Works:**

```javascript
// The RealTimeWebChatClient automatically detects WebSocket availability
const client = new RealTimeWebChatClient('/unicom/webchat');

// Set up event handlers for real-time updates
client.onMessage = (message, chatId) => {
  console.log('New message received:', message);
};

client.onConnectionChange = (connected, type) => {
  if (type === 'websocket') {
    console.log('✅ Using real-time WebSocket connection');
  } else {
    console.log('📡 Using polling mode (${autoRefresh}s refresh)');
  }
};

// Connect (tries WebSocket first, falls back to polling)
await client.connect();
```

**Features Available with WebSocket:**

- ⚡ **Instant message delivery** - No polling delay
- 🔄 **Real-time chat list updates** - See new chats immediately
- 📊 **Live typing indicators** (future enhancement)
- ✅ **Read receipts** (future enhancement)
- 🔌 **Automatic reconnection** - Handles connection drops gracefully

**Polling Fallback:**

If Channels is not installed or WebSocket connection fails:
- Automatically falls back to HTTP polling
- Polls every 5 seconds (configurable via `auto-refresh` attribute)
- **Same data and behavior** as WebSocket mode
- Slightly higher latency but reliable

**Connection Status Indicator:**

The WebChat component shows the current connection mode:
- 🟢 **Real-time (WebSocket)** - Green badge when using WebSockets
- 🔄 **Polling mode (5s refresh)** - Yellow badge when using polling

#### 🌐 Guest User Migration

When a guest user logs in, their chat history is automatically preserved:

```python
from unicom.services.webchat.migrate_guest_to_user import migrate_guest_to_user

# During login process (usually in a signal or login view)
def user_logged_in_handler(sender, request, user, **kwargs):
    if request.session.session_key:
        # Migrate all guest chats to authenticated user
        migrate_guest_to_user(request.session.session_key, user)

# This transfers:
# - All messages from guest account to user account
# - All chats and chat memberships
# - All request history
# - Deletes the guest account
```

#### 🌐 WebChat Security

All WebChat operations include security measures:

```python
# ✅ Access Control
# - Users can only access their own chats
# - Verified via AccountChat relationship
# - Blocked accounts cannot send messages

# ✅ CSRF Protection
# - All mutating operations require CSRF token
# - Automatically handled by JavaScript API client

# ✅ Chat Isolation
# - Each chat has unique UUID
# - Messages cannot leak between chats
# - No cross-user access possible

# ✅ Guest Security
# - Guest sessions isolated by session key
# - No access to other guest sessions
# - Migration requires authentication
```

#### 🌐 WebChat Architecture

The WebChat system consists of:

**Backend (Django):**
- Service layer: `unicom/services/webchat/`
  - `get_or_create_account.py` - Account management
  - `save_webchat_message.py` - Message saving and request creation
  - `send_webchat_message.py` - Bot message sending
  - `migrate_guest_to_user.py` - Guest-to-user migration
  - `generate_chat_title.py` - Auto-title generation
- Views: `unicom/views/webchat_views.py` - REST API endpoints
- URLs: `/unicom/webchat/` - API routes

**Frontend (LitElement Web Components):**
- Main component: `<unicom-chat-with-sidebar>` - Multi-chat interface
- Sub-components:
  - `<chat-list>` - Sidebar with chat list
  - `<message-list>` - Scrollable message container
  - `<message-item>` - Individual message rendering
  - `<message-input>` - Input area with media upload
  - `<media-preview>` - File preview before sending
- Utilities:
  - API client with CSRF protection
  - DateTime formatters
  - Shared CSS styles with theming

#### 🌐 WebChat Testing

Comprehensive test suite included:

```bash
# Run WebChat tests
pytest tests/test_webchat.py -v

# Test coverage includes:
# ✅ Guest and authenticated user messaging
# ✅ Multiple separate chats
# ✅ Message retrieval with pagination
# ✅ Chat listing
# ✅ Bot replies
# ✅ Request processing
# ✅ Guest-to-user migration
# ✅ Security (access control, blocked accounts)
```

#### 🌐 WebChat Optional Enhancements

**Future Enhancements (Optional - Not Required):**

For real-time push notifications instead of polling, you can optionally install Django Channels:

```bash
pip install channels channels-redis daphne
```

This enables:
- WebSocket connections for instant message delivery
- Typing indicators
- Read receipts
- No polling overhead

**Note:** Channels is completely optional. The current polling-based system works perfectly for most use cases.

### LLM Integration

#### 🤖 AI-Powered Responses (Platform-Agnostic)

```python
# Basic LLM reply to any message
response = message.reply_using_llm(
    model="gpt-4",
    system_instruction="You are a helpful customer service assistant",
    depth=129  # Include last 129 messages for context
)

# 🤖 Multimodal support (images, audio)
response = message.reply_using_llm(
    model="gpt-4-vision-preview",
    multimodal=True,  # Process images and audio
    voice="alloy"  # Voice for audio responses
)
```

#### 🤖 Tool Call System

The LLM system can call external functions and tools:

```python
# Log tool interactions
message.log_tool_interaction(
    tool_call={
        "name": "search_database", 
        "arguments": {"query": "user orders", "limit": 5},
        "id": "call_123"
    }
)

# Log tool response
message.log_tool_interaction(
    tool_response={
        "call_id": "call_123",
        "result": {"orders": [...], "count": 3}
    }
)

# Get LLM-ready conversation including tool calls
conversation = message.as_llm_chat(depth=20, mode="chat")
```

#### 🤖 Chat-Level Tool Interactions

```python
# System-initiated tool call
chat.log_tool_interaction(
    tool_call={"name": "cleanup_cache", "arguments": {}, "id": "call_456"}
)

# With specific reply target
chat.log_tool_interaction(
    tool_call={"name": "fetch_data", "arguments": {"user_id": 123}, "id": "call_789"},
    reply_to=some_message
)
```

#### Tool response presentations

WebChat clients can render safe visual output inside the existing tool activity.
Return a reserved `_unicom_presentation` object in the tool result:

```python
return {
    "result": "Image inspected",
    "_unicom_presentation": {
        "type": "image",
        "url": "data:image/png;base64,...",  # or an HTTP(S)/root-relative URL
        "alt": "Inspection result",
        "caption": "/photos/result.png",
    },
}
```

Unicom serializes this as `tool_presentation` on the persisted `tool_response`
message. A client should merge that response into its corresponding `tool_call`
using `reply_to_message_id` and render the descriptor there. Presentations do not
create assistant messages or alter LLM conversation semantics. Image URLs are
validated; arbitrary HTML and executable URL schemes are not supported.

For compatibility, persisted Responses API tool results containing an
`_responses_content` `input_image` data URL are exposed using the same descriptor.

### Delayed Tool Calls

#### 🤖 Request-Based Tool Call Management

The LLM system supports delayed tool calls that can take hours or days to complete, perfect for reminders, monitoring, and long-running processes.

**Tool Implementation - Return `None` to Defer Response:**

```python
# In your tool definition (e.g., unibot Tool model)
def set_reminder(text: str, delay_hours: int) -> str:
    """Schedule a reminder for later"""
    from django.utils import timezone
    from datetime import timedelta

    # Schedule the reminder using the tool_call context variable
    reminder_time = timezone.now() + timedelta(hours=delay_hours)

    # Store tool_call.id for later response
    # (e.g., in a database, Redis, or scheduler)
    schedule_reminder(
        tool_call_id=tool_call.call_id,
        message=text,
        scheduled_time=reminder_time
    )

    # Return None to defer the response
    # System automatically marks tool_call as IN_PROGRESS
    return None

tool_definition = {
    "name": "set_reminder",
    "description": "Set a reminder for a specific time in the future",
    "parameters": {
        "text": {"type": "string", "description": "Reminder text"},
        "delay_hours": {"type": "integer", "description": "Hours to wait"}
    },
    "run": set_reminder
}
```

**Responding Later from Any Process:**

```python
from unicom.models import ToolCall

# Hours or days later, in a background job or scheduled task...
tool_call = ToolCall.objects.get(call_id="call_123")

# Respond to the tool call
msg, child_request = tool_call.respond("Reminder: Meeting in 1 hour")
# This creates a new child request for the LLM to process

# The LLM receives the response and can continue the conversation
```

**For Periodic/Ongoing Tools (e.g., Monitoring):**

```python
def monitor_system(threshold: int) -> str:
    """Monitor system continuously and report status"""

    # Mark as ACTIVE for periodic responses
    tool_call.mark_active()

    # Start background monitoring
    start_monitoring_task(tool_call_id=tool_call.call_id, threshold=threshold)

    return None  # Or return initial status

# Later, in your monitoring task...
tool_call = ToolCall.objects.get(call_id="monitor_123", status='ACTIVE')

# Send periodic updates without creating child requests
tool_call.respond("CPU usage: 95%")  # Just logs, no child request
tool_call.respond("CPU usage: 92%")  # Just logs, no child request

# Tool call remains ACTIVE and can respond indefinitely
```

#### 🤖 Request Hierarchy and Final Response Logic

```python
# Only when ALL pending tool calls respond does system create child request
request = Request.objects.get(id='parent_request')

# Submit 3 tool calls
calls = request.submit_tool_calls([
    {"name": "search", "arguments": {"query": "data"}},
    {"name": "analyze", "arguments": {"input": "results"}}, 
    {"name": "report", "arguments": {"format": "pdf"}}
])

# Respond to each (no child request yet)
calls[0].respond("search results")     # No child - not final
calls[1].respond("analysis complete")  # No child - not final  
calls[2].respond("report generated")   # Child request created!

# Child request inherits context from initial request
child = Request.objects.filter(parent_request=request).first()
print(f"Child inherits: {child.account}, {child.category}, {child.member}")
```

Parallel calls form one batch: Unicom creates at most one continuation, and
only after every unresolved call in that request has reached a terminal state.
`Request.submit_tool_calls()` can return an empty list when a newer ordinary
user message has superseded the request while the LLM response was in flight;
orchestrators must treat that as discarded stale output rather than executing
or indexing the returned calls.

When accepting a newer user turn, an orchestrator should terminalize unfinished
batch work with `ToolCall.interrupt_unresolved(queryset)`. This operation is
idempotent, persists an `ERROR` tool response for every unresolved call, and
does not create an LLM continuation. A later `ToolCall.respond()` for an
interrupted call is ignored. Edited user messages remain genuine reply-tree
branches; parallel tool calls are reconstructed from the selected request tree
and do not create user-visible conversation branches.

`ACTIVE` is suitable only when the host application intentionally wants a
long-lived call. Whether a newer user message should cancel such calls is an
orchestrator policy; filter them out before calling `interrupt_unresolved()` if
they must survive unrelated user turns.

#### Canonical Message Serialization

Use Unicom's public serializer instead of reproducing tool-message fields in a
host application:

```python
from unicom.services.message_serialization import serialize_message

payload = serialize_message(message)
```

The payload includes the common message fields plus `tool_name`, `call_id`,
`tool_status`, `result_status`, progress text, interactive buttons, and tool
presentation data. In particular, `tool_status` lets clients render historical
terminal calls such as `INTERRUPTED` as finished even if old data has no linked
response message. Applications may extend this dictionary with their own UI or
authorization metadata.

#### 🤖 Request Tracking Fields

New fields added to Request model for LLM and tool call tracking:

```python
request.parent_request     # Parent request that spawned this one
request.initial_request    # Root request that started the chain
request.tool_call_count    # Number of tool calls made from this request
request.llm_calls_count    # Number of LLM API calls made
request.llm_token_usage    # Total tokens consumed by LLM
```

### Message Scheduling

#### Automated Scheduling System

```python
# Check and process scheduled messages manually
from unicom.services.crossplatform.scheduler import process_scheduled_messages

result = process_scheduled_messages()
print(f"Processed {result['total_due']} messages")
print(f"Sent: {result['sent']}, Failed: {result['failed']}")
```

---

## ⚙️ Production Setup

### IMAP Listeners

Email channels require IMAP listeners to receive incoming emails in real-time.

#### Development (Django runserver)
When using `python manage.py runserver`, IMAP listeners start automatically with the server.

#### Production (Gunicorn, uWSGI, etc.)
In production deployments, you need to run IMAP listeners as a separate process:

```bash
# Start IMAP listeners for all active email channels
python manage.py start_imap_listeners
```

This command will:
- Start IMAP IDLE connections for all active email channels
- Keep running until stopped with Ctrl+C
- Automatically reconnect if connections drop
- Process incoming emails in real-time

#### Docker/Containerized Deployments

Add a separate service in your `docker-compose.yml`:

```yaml
services:
  web:
    # Your main Django app
    
  imap_listener:
    # Same image as your web service  
    build: .
    command: python manage.py start_imap_listeners
    volumes:
      - .:/app
    environment:
      # Same environment as web service
    depends_on:
      - db
```

### Scheduled Message Processing

For automated sending of scheduled messages:

```bash
# Process scheduled messages every 10 seconds (default)
python manage.py send_scheduled_messages

# Custom interval (30 seconds)  
python manage.py send_scheduled_messages --interval 30
```

Use `--run-once` with either command to execute a single pass and exit.

Add this as a background service or cron job in production.

---

## 🛠️ Management Commands

Available management commands for production and development:

### `start_imap_listeners`
Starts IMAP listeners for all active email channels. Required in production when not using `runserver`.

```bash
python manage.py start_imap_listeners
```

### `send_scheduled_messages` 
Continuously processes and sends scheduled messages.

```bash
# Default 10-second interval
python manage.py send_scheduled_messages

# Custom interval
python manage.py send_scheduled_messages --interval 30
```

### `run_as_llm_chat`
Triggers an LLM response to a specific message (useful for testing AI features).

```bash  
python manage.py run_as_llm_chat <message_id>
```

---

## 🧑‍💻 Contributing

We ❤️ contributors!

### Choose your setup:

- **App-only (recommended for most contributors):** clone this repo and plug it into an existing Django project. You supply your own settings and database.
- **Workspace (maintainers / full dev stack):** use the preconfigured dev project with Docker, tests, and environment wiring at `https://github.com/meena-erian/django-unicom`.

### Workspace setup (maintainers):

1. Clone the workspace repo (with submodules):

   ```bash
   git clone --recurse-submodules https://github.com/meena-erian/django-unicom.git
   cd django-unicom
   ```

2. Create a `db.env` file in the root:

   ```env
   POSTGRES_DB=unicom_test
   POSTGRES_USER=unicom
   POSTGRES_PASSWORD=unicom
   DJANGO_PUBLIC_ORIGIN=https://yourdomain.com
   # Needed if you want to use the rich-text email composer in the admin
   UNICOM_TINYMCE_API_KEY=your-tinymce-api-key
   # Needed if you want to use the AI template population service
   OPENAI_API_KEY=your-openai-api-key
   ```

3. Start the dev environment:

   ```bash
   docker-compose up --build
   ```

4. Run tests:

   ```bash
   docker-compose exec app pytest
   ```

   or just

   ```bash
   pytest
   ```
   Note: To run ```test_telegram_live``` tests you need to create ```telegram_credentials.py``` in the tests folder and define in it ```TELEGRAM_API_TOKEN``` and ```TELEGRAM_SECRET_TOKEN```. To run ```test_email_live``` you also need to create ```email_credentials.py``` with an ```EMAIL_CONFIG``` dict that includes ```EMAIL_ADDRESS```, ```EMAIL_PASSWORD```, ```IMAP```, and ```SMTP``` (each ```IMAP```/```SMTP``` contains ```host```, ```port```, ```use_ssl```, and ```protocol```). Add ```IMAP_USERNAME```, ```IMAP_PASSWORD```, ```SMTP_USERNAME```, and ```SMTP_PASSWORD``` there if the protocol logins differ from the base address/password.

No need to modify `settings.py` — everything is pre-wired to read from `db.env`.

---

## 📄 License

MIT License © Meena (Menas) Erian

## 📦 Release Automation

To release a new version to PyPI:

1. Ensure your changes are committed and pushed.
2. Run:
   
   ```bash
   make release VERSION=1.2.3
   ```
   This will:
   - Tag the release as v1.2.3 in Git
   - Push the tag
   - Build the package
   - Upload to PyPI using your .pypirc

3. For an auto-generated version based on date/time, just run:
   
   ```bash
   make release
   ```
   This will use the current date/time as the version (e.g., 2024.06.13.1530).

The version is automatically managed by setuptools_scm from Git tags and is available at runtime as `unicom.__version__`.
