# Unibot - Django AI Bot Framework

A powerful Django app for creating and managing AI-powered bots with tool integration, encrypted credential management, and multi-modal message handling.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Dependencies](#dependencies)
- [Installation & Configuration](#installation--configuration)
  - [Django Settings](#django-settings)
  - [Environment Variables](#environment-variables)
  - [URL Configuration](#url-configuration)
  - [Unibot Settings](#unibot-settings)
- [Core Models](#core-models)
  - [`models.py` - Bot Model](#modelspy---bot-model)
  - [`models.py` - Tool Model](#modelspy---tool-model)
  - [`models.py` - EncryptedCredential Model](#modelspy---encryptedcredential-model)
  - [`models.py` - CredentialFieldDefinition Model](#modelspy---credentialfielddefinition-model)
  - [`models.py` - CredentialSetupSession Model](#modelspy---credentialsetupsession-model)
- [Management Commands](#management-commands)
  - [`run_worker.py` - Bot Request Processor](#run_workerpy---bot-request-processor)
  - [`sync_tools_and_bots.py` - Filesystem to Database Sync](#sync_tools_and_botspy---filesystem-to-database-sync)
- [Services & Business Logic](#services--business-logic)
  - [`services/llm_handler.py` - OpenAI Integration](#servicesllm_handlerpy---openai-integration)
  - [`services/credentials.py` - Credential Management](#servicescredentialspy---credential-management)
  - [`services/tool_result_handler.py` - Tool Execution Results](#servicestool_result_handlerpy---tool-execution-results)
- [Admin Interface](#admin-interface)
  - [`admin.py` - Django Admin Configuration](#adminpy---django-admin-configuration)
- [Web Views](#web-views)
  - [`views.py` - Credential Setup Forms](#viewspy---credential-setup-forms)
  - [`urls.py` - URL Routing](#urlspy---url-routing)
- [Templates & Examples](#templates--examples)
  - [`templates/unibot/` - Bot and Tool Templates](#templatesunibot---bot-and-tool-templates)
- [Getting Started](#getting-started)
  - [Quick Setup](#quick-setup)
  - [Creating Your First Bot](#creating-your-first-bot)
  - [Creating Tools](#creating-tools)
  - [Managing Credentials](#managing-credentials)
- [File-Based Development Workflow](#file-based-development-workflow)
  - [Directory Structure](#directory-structure)
  - [Syncing Changes](#syncing-changes)
  - [Multi-Project Setup](#multi-project-setup)
- [Architecture & Execution Flow](#architecture--execution-flow)
  - [Bot Processing Pipeline](#bot-processing-pipeline)
  - [Tool Execution Context](#tool-execution-context)
  - [Security Model](#security-model)
- [Advanced Usage](#advanced-usage)
  - [Custom Tool Development](#custom-tool-development)
  - [Bot Code Examples](#bot-code-examples)
  - [Credential Workflows](#credential-workflows)
- [Integration Guide](#integration-guide)
  - [Integrating with Existing Projects](#integrating-with-existing-projects)
  - [API Integration](#api-integration)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## Overview

Unibot is a comprehensive Django framework designed for building sophisticated AI-powered bots that can:

- **Execute Custom Tools**: Define reusable Python functions that bots can call during conversations
- **Manage Encrypted Credentials**: Securely store and manage API keys and sensitive data with Fernet encryption
- **Handle Multi-Modal Messages**: Process text, audio, images, and files through OpenAI integration
- **Provide Administrative Control**: Full Django admin interface for managing bots, tools, and credentials
- **Support Development Workflows**: File-based tool/bot definitions with database synchronization

## Key Features

🤖 **AI-Powered Bots** - OpenAI integration with tool calling capabilities
🔧 **Custom Tools** - Extensible tool system with Python function definitions
🔐 **Secure Credentials** - Encrypted storage with time-limited setup sessions
📁 **File-Based Development** - Version-controlled bot/tool definitions
🔄 **Database Sync** - Automatic synchronization between filesystem and database
🛡️ **Security First** - Fernet encryption, attempt limiting, session expiration
📊 **Admin Interface** - Full Django admin integration with code editors
🌐 **Multi-Modal** - Text, audio, image, and file processing support

---

## Dependencies

- **django-unicom**: Core messaging and account management system (provides `Account`, `Message`, `RequestCategory` models)
- All other dependencies are listed in `requirements.txt`

---

## Installation & Configuration

### Django Settings

Add to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ... other apps
    'unicom',  # Required dependency
    'unibot',
    'reversion',  # Required for model versioning
]
```

Add to your `MIDDLEWARE`:

```python
MIDDLEWARE = [
    # ... other middleware
    'reversion.middleware.RevisionMiddleware',
]
```

### Environment Variables

Set these in your environment or `.env` file:

```bash
# OpenAI API Key
OPENAI_API_KEY=your-openai-api-key

# Credential encryption key (URL-safe base64-encoded 32-byte key)
CREDENTIAL_ENCRYPTION_KEY=your-encryption-key
```

In Django settings:

```python
import os
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
CREDENTIAL_ENCRYPTION_KEY = os.getenv('CREDENTIAL_ENCRYPTION_KEY')
```

### URL Configuration

Include unibot URLs in your main `urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    # ... other URLs
    path('unibot/', include('unibot.urls')),
]
```

### Unibot Settings

Configure unibot behavior in your Django settings:

```python
# Directory containing tool and bot definitions for sync command
UNIBOT_DEFINITIONS_DIR = BASE_DIR / 'data' / 'definitions'

# Optional: Multiple definition directories
UNIBOT_DEFINITIONS_DIRS = [
    BASE_DIR / 'data' / 'definitions',
    BASE_DIR / 'custom-tools',
    '/path/to/shared-unibot-tools'
]
```

---

## Core Models

### `models.py` - Bot Model
AI bot configurations with custom Python code and tool associations.

**Key Features:**
- Custom Python code execution with context injection
- Many-to-many relationship with Tools
- Automatic RequestCategory creation for message routing
- Version control with django-reversion

**Context Variables Available in Bot Code:**
- `bot` - The Bot instance
- `message` - Message object being processed
- `account` - Account/user who sent the message
- `request` - Request object with status and metadata
- `member` - Member object if available
- `tool_call` - The ToolCall instance for this tool execution (only available in tools during execution)
- `openai_client` - OpenAI client instance

### `models.py` - Tool Model
Reusable functions that bots can execute during conversations.

**Key Features:**
- Python code with `tool_definition` dictionary
- OpenAI function calling schema generation
- Same context variables as bots, plus `tool_call` instance during execution
- Template loading for admin interface
- Support for deferred responses (return `None` to handle response later)
- Handled errors/warnings via `ToolHandlerError`/`ToolHandlerWarning` to return user-facing failures without breaking the request
- All tool outputs are wrapped with a status for the LLM (`SUCCESS` by default, or `WARNING`/`ERROR` when raised/passed)
- Auto-injected `progress_updates_for_user` parameter requires the LLM to provide a one-line “what/why” progress update; tools can ignore it or accept it explicitly

**Required Structure:**
```python
def my_function(param1: str, param2: int = 10) -> str:
    # Tool implementation
    return "result"

tool_definition = {
    "name": "my_function",
    "description": "Description of what this tool does",
    "parameters": {
        "param1": {"type": "string", "description": "First parameter"},
        "param2": {"type": "integer", "description": "Second parameter", "default": 10}
    },
    "run": my_function
}
```

### `models.py` - EncryptedCredential Model
Secure storage for API keys and sensitive data using Fernet encryption.

**Key Features:**
- Automatic encryption/decryption
- Account-specific credential storage
- Unique constraints on account+key pairs
- No plain-text credential exposure

### `models.py` - CredentialFieldDefinition Model
Schema definitions for credential fields with validation rules.

**Supported Field Types:**
- `text` - General text input
- `email` - Email address validation
- `number` - Numeric input
- `phone` - Phone number format
- `password` - Password input (hidden)
- `pin` - Numeric PIN

**Validation Features:**
- Regex pattern matching
- Length constraints (min/max)
- Required/optional fields
- Custom error messages

### `models.py` - CredentialSetupSession Model
Time-limited sessions for secure credential collection from users.

**Key Features:**
- Expiration timestamps
- Attempt limiting
- Metadata storage for context
- UUID-based secure identifiers

---

## Management Commands

### `run_worker.py` - Bot Request Processor
Processes incoming requests by matching them to appropriate bots and executing bot code.

**Usage:**
```bash
# Process all requests for all bots
python manage.py run_worker

# Process requests for specific bot
python manage.py run_worker --bot-id 1

# Limit number of requests per loop
python manage.py run_worker --limit 10

# Custom sleep time between loops
python manage.py run_worker --sleep 5
```

**Features:**
- Multi-bot support with automatic matching
- Database locking for concurrent processing
- Error handling and status tracking
- Configurable processing limits

### `sync_tools_and_bots.py` - Filesystem to Database Sync
Synchronizes tool and bot definitions from filesystem to database, enabling version-controlled development.

**Usage:**
```bash
# Preview changes without applying them
python manage.py sync_tools_and_bots --dry-run

# Apply changes to database
python manage.py sync_tools_and_bots

# Sync with verbose output
python manage.py sync_tools_and_bots --verbosity 2
```

**Features:**
- Configurable source directories via `UNIBOT_DEFINITIONS_DIR`
- Safe updates (only changes modified files)
- Validation of tool_definition and handle_incoming_message functions
- Bot-tool association management via `bot_tools` lists
- Support for external tool directories

---

## Services & Business Logic

### `services/llm_handler.py` - OpenAI Integration
Handles OpenAI API interactions with tool calling and multi-modal content support.

**Key Functions:**
- `run_llm_handler()` - Main LLM processing function
- `build_openai_tools()` - Converts tool definitions to OpenAI schema
- `process_llm_content()` - Handles multi-modal response processing

**Features:**
- Audio, image, and text content processing
- Tool calling with function execution loops
- Configurable model selection
- File handling and temporary storage

### `services/credentials.py` - Credential Management
Provides functions for requesting and managing user credentials within tools.

**Key Functions:**
- `get_credentials()` - Main credential request function
- `request_credentials()` - Session creation and polling

**Usage in Tools:**
```python
# In tool code
creds = get_credentials([
    {"key": "GOOGLE_API_KEY", "label": "Google API Key", "type": "password"},
    {"key": "USER_EMAIL", "label": "Email", "type": "email"}
])
if creds:
    api_key = creds["GOOGLE_API_KEY"]
    email = creds["USER_EMAIL"]
```

### `services/tool_result_handler.py` - Tool Execution Results
Handles tool execution results, including file processing and response formatting.

**Features:**
- File path detection and handling
- Platform-specific response formatting
- Result serialization and logging

---

## Admin Interface

### `admin.py` - Django Admin Configuration
Comprehensive admin interface for managing all unibot components.

**Features:**
- Code editor integration (ACE widget)
- Version control with django-reversion
- Secure credential management (create-only)
- Setup session link generation
- Tool/bot association management

**Admin Models:**
- BotAdmin - Bot management with code editor
- ToolAdmin - Tool management with validation
- EncryptedCredentialAdmin - Secure credential creation
- CredentialFieldDefinitionAdmin - Field schema management
- CredentialSetupSessionAdmin - Session monitoring

---

## Web Views

### `views.py` - Credential Setup Forms
Handles secure credential collection through time-limited web forms.

**Key Views:**
- `credential_setup` - Main credential collection view

**Features:**
- Session validation (expiration, attempts)
- Field validation according to CredentialFieldDefinition
- Automatic encryption and storage
- Error handling and user feedback

### `urls.py` - URL Routing
URL patterns for unibot web functionality.

**Routes:**
- `credential-setup/<uuid:session_id>/` - Credential setup forms

---

## Templates & Examples

### `templates/unibot/` - Bot and Tool Templates
Contains template files and examples for bot and tool development.

**Template Files:**
- `default_bot.py` - Basic bot template
- `default_tool.py` - Web scraping tool example
- `admin_bot.py` - Administrative bot template
- Various CRUD tools (`create_bot_tool.py`, `update_tool_tool.py`, etc.)

**Documentation:**
- [`BOT_TEMPLATES_README.md`](templates/unibot/BOT_TEMPLATES_README.md) - Bot development guide
- [`TOOL_TEMPLATES_README.md`](templates/unibot/TOOL_TEMPLATES_README.md) - Tool development guide

---

## Getting Started

### Quick Setup

1. **Install Dependencies**
```bash
pip install -r requirements.txt
```

2. **Configure Django Settings** (see [Django Settings](#django-settings))

3. **Run Migrations**
```bash
python manage.py migrate unibot
```

4. **Create Superuser**
```bash
python manage.py createsuperuser
```

5. **Set Up Tool/Bot Definitions Directory**
```bash
mkdir -p data/definitions/tools data/definitions/bots
```

### Creating Your First Bot

> 📖 **For detailed bot development guidance, see [`BOT_TEMPLATES_README.md`](templates/unibot/BOT_TEMPLATES_README.md)**

1. **Create Bot Definition File**
Create `data/definitions/bots/my_first_bot.py`:

```python
# List of tools this bot can use
bot_tools = ["web_search", "calculator"]

def handle_incoming_message(message, bot, tools_list):
    """Handle incoming messages for this bot"""
    return bot.reply_using_llm(
        message,
        tools_list,
        system_instruction="You are a helpful assistant with web search capabilities.",
        request=request
    )
```

2. **Sync to Database**
```bash
python manage.py sync_tools_and_bots
```

3. **Start Worker**
```bash
python manage.py run_worker
```

### Creating Tools

> 📖 **For detailed tool development guidance, see [`TOOL_TEMPLATES_README.md`](templates/unibot/TOOL_TEMPLATES_README.md)**

1. **Create Tool Definition File**
Create `data/definitions/tools/calculator.py`:

```python
def calculate(expression: str) -> str:
    """Safely evaluate mathematical expressions"""
    try:
        # Add safety checks here
        result = eval(expression)  # Use with caution in production
        return str(result)
    except Exception as e:
        return f"Error: {e}"

tool_definition = {
    "name": "calculate",
    "description": "Evaluate mathematical expressions",
    "parameters": {
        "expression": {
            "type": "string",
            "description": "Mathematical expression to evaluate"
        }
    },
    "run": calculate
}
```

2. **Sync Changes**
```bash
python manage.py sync_tools_and_bots --dry-run  # Preview
python manage.py sync_tools_and_bots             # Apply
```

### Managing Credentials

1. **Create Credential Field Definition**
In Django admin → Unibot → Credential Field Definitions, create:
- Key: `GOOGLE_API_KEY`
- Label: `Google API Key`
- Type: `password`
- Required: `True`

2. **Request Credentials in Tool**
```python
def search_web(query: str) -> str:
    creds = get_credentials([
        {"key": "GOOGLE_API_KEY", "label": "Google API Key", "type": "password"}
    ])

    if not creds:
        return "Please set up your Google API key first."

    # Use creds["GOOGLE_API_KEY"] for API calls
    return search_results
```

---

## File-Based Development Workflow

### Directory Structure

Recommended project structure:

```
your-project/
├── data/definitions/           # Project-specific tools/bots
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── web_search.py
│   │   └── calculator.py
│   └── bots/
│       ├── __init__.py
│       ├── assistant_bot.py
│       └── admin_bot.py
├── custom-tools/              # Additional tool collections
│   ├── tools/
│   └── bots/
└── manage.py
```

### Syncing Changes

**Development Workflow:**

1. Edit tool/bot files in your preferred editor
2. Test syntax: `python -c "import data.definitions.tools.my_tool"`
3. Preview changes: `python manage.py sync_tools_and_bots --dry-run`
4. Apply changes: `python manage.py sync_tools_and_bots`
5. Commit to version control: `git add data/definitions && git commit`

**Benefits:**
- Version controlled bot/tool code
- Team collaboration through git
- Easy rollback and change tracking
- No manual database updates

### Multi-Project Setup

Configure multiple definition directories:

```python
# settings.py
UNIBOT_DEFINITIONS_DIR = BASE_DIR / 'data' / 'definitions'

# Or multiple directories:
UNIBOT_DEFINITIONS_DIRS = [
    BASE_DIR / 'data' / 'definitions',      # Project-specific
    BASE_DIR / 'shared-unibot-tools',       # Shared across projects
    '/opt/company-wide-tools'               # Company-wide tools
]
```

---

## Architecture & Execution Flow

### Bot Processing Pipeline

1. **Request Creation** - Incoming messages create Request objects
2. **Bot Matching** - Requests matched to Bots via RequestCategory
3. **Code Execution** - Bot code executed with injected context
4. **LLM Processing** - OpenAI API called with available tools
5. **Tool Execution** - AI-requested tools executed in sandbox
6. **Response Generation** - Results processed and sent back

### Tool Execution Context

Tools have access to:
- `bot` - Bot instance processing the request
- `message` - Message object with content and metadata
- `account` - User account that sent the message
- `request` - Request object with processing status
- `member` - Member object if available
- `tool_call` - ToolCall instance for this execution (use `tool_call.call_id` to track, return `None` to defer response)
- `openai_client` - Pre-configured OpenAI client

**Deferred Response Pattern:**
- Return a value: Tool response sent immediately to LLM
- Return `None`: Tool call marked as `IN_PROGRESS`, tool handles response later via `tool_call.respond(result)`

### Security Model

**Credential Security:**
- Fernet encryption for all stored credentials
- Time-limited setup sessions
- Attempt limiting on credential forms
- Account-specific credential isolation

**Code Execution:**
- Bot/tool code runs in controlled environment
- Context variable injection limits scope
- No direct database access in tool code
- All changes tracked via django-reversion

---

## Advanced Usage

### Custom Tool Development

> 📖 **For detailed tool development guidance, see [`TOOL_TEMPLATES_README.md`](templates/unibot/TOOL_TEMPLATES_README.md)**

**Advanced Tool Pattern:**
```python
from unibot.services.credentials import get_credentials

def advanced_web_scraper(url: str, css_selector: str = None) -> dict:
    """Advanced web scraping with authentication"""

    # Request credentials if needed
    creds = get_credentials([
        {"key": "PROXY_URL", "label": "Proxy URL", "type": "text", "required": False},
        {"key": "USER_AGENT", "label": "User Agent", "type": "text", "required": False}
    ], update=False)

    # Use credentials in implementation
    headers = {}
    if creds and creds.get("USER_AGENT"):
        headers["User-Agent"] = creds["USER_AGENT"]

    # Implementation with error handling
    try:
        # Scraping logic here
        return {"success": True, "data": scraped_data}
    except Exception as e:
        return {"success": False, "error": str(e)}

tool_definition = {
    "name": "advanced_web_scraper",
    "description": "Scrape web content with authentication and custom selectors",
    "parameters": {
        "url": {"type": "string", "description": "URL to scrape"},
        "css_selector": {
            "type": "string",
            "description": "CSS selector for content extraction",
            "default": None
        }
    },
    "run": advanced_web_scraper
}
```

### Bot Code Examples

> 📖 **For detailed bot development guidance, see [`BOT_TEMPLATES_README.md`](templates/unibot/BOT_TEMPLATES_README.md)**

**Specialized Bot with Custom Logic:**
```python
# data/definitions/bots/customer_service_bot.py

bot_tools = ["search_knowledge_base", "create_ticket", "send_email"]

def handle_incoming_message(message, bot, tools_list):
    """Customer service bot with routing logic"""

    # Check if this is an urgent request
    if any(word in message.content.lower() for word in ['urgent', 'emergency', 'critical']):
        # Use different system instruction for urgent requests
        system_instruction = """You are an urgent customer service assistant.
        Prioritize immediate resolution and escalate if needed."""
    else:
        system_instruction = """You are a helpful customer service assistant.
        Search the knowledge base first, then create tickets if needed."""

    return bot.reply_using_llm(
        message,
        tools_list,
        system_instruction=system_instruction,
        model_default="gpt-4",  # Use better model for customer service
        request=request
    )
```

### Credential Workflows

**Complex Credential Setup:**
```python
def setup_integration(service: str) -> str:
    """Set up third-party service integration"""

    # Different credentials based on service
    if service == "salesforce":
        fields = [
            {"key": "SALESFORCE_USERNAME", "type": "email"},
            {"key": "SALESFORCE_PASSWORD", "type": "password"},
            {"key": "SALESFORCE_SECURITY_TOKEN", "type": "password"}
        ]
    elif service == "slack":
        fields = [
            {"key": "SLACK_BOT_TOKEN", "type": "password", "regex_pattern": "^xoxb-.*"},
            {"key": "SLACK_SIGNING_SECRET", "type": "password"}
        ]
    else:
        return f"Unknown service: {service}"

    creds = get_credentials(fields, update=True)  # Force re-setup

    if not creds:
        return f"Please complete the {service} setup using the provided link."

    # Test the credentials
    if test_connection(service, creds):
        return f"{service} integration configured successfully!"
    else:
        return f"Failed to connect to {service}. Please check your credentials."
```

---

## Integration Guide

### Integrating with Existing Projects

**Minimal Integration:**
1. Add unibot to INSTALLED_APPS
2. Run migrations
3. Configure OPENAI_API_KEY
4. Create basic bot in admin interface

**Advanced Integration:**
1. Set up file-based development workflow
2. Create project-specific tools directory
3. Configure UNIBOT_DEFINITIONS_DIR
4. Set up automated sync in deployment pipeline

### API Integration

**Custom Message Sources:**
```python
# In your app
from unibot.models import Bot
from unicom.models import Message, Account

def process_webhook(request_data):
    """Process incoming webhook as unibot message"""

    # Create or get account
    account = Account.objects.get_or_create(
        username=request_data['user_id']
    )[0]

    # Create message
    message = Message.objects.create(
        content=request_data['text'],
        sender=account,
        # ... other fields
    )

    # Get bot and process
    bot = Bot.objects.get(name="webhook_handler")
    bot.process_request(message.requests.first())
```

---

## Troubleshooting

**Common Issues:**

1. **Sync Command Not Found**
   - Ensure unibot is in INSTALLED_APPS
   - Check management/commands/__init__.py files exist
   - Verify UNIBOT_DEFINITIONS_DIR is set

2. **Tool Definition Errors**
   - Check tool_definition dictionary is present
   - Verify function signature matches parameters
   - Use `--dry-run` to validate before syncing

3. **Credential Encryption Errors**
   - Generate proper encryption key: `from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())`
   - Ensure CREDENTIAL_ENCRYPTION_KEY is set in environment

4. **OpenAI Integration Issues**
   - Verify OPENAI_API_KEY is valid and has sufficient credits
   - Check model availability (some models require special access)
   - Monitor API rate limits

**Debug Mode:**
```bash
# Enable verbose output
python manage.py sync_tools_and_bots --verbosity 2

# Check Django settings
python manage.py shell -c "from django.conf import settings; print(settings.UNIBOT_DEFINITIONS_DIR)"

# Test tool definitions
python -c "
import data.definitions.tools.my_tool as tool
print(tool.tool_definition)
"
```

---

## Contributing

1. Follow Django app development best practices
2. Add tests for new features
3. Update README.md for significant changes
4. Use type hints in new code
5. Document any new settings or environment variables

**Development Setup:**
```bash
git clone <repository>
cd unibot
pip install -r requirements-dev.txt
python manage.py test
```

---

*This README covers unibot version with sync_tools_and_bots management command. For the latest documentation, check the repository or run `python manage.py help sync_tools_and_bots` for command-specific help.*
