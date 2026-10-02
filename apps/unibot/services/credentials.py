import inspect
from typing import List, Optional, Dict
from unibot.models import CredentialFieldDefinition, Account, Bot, CredentialSetupSession, EncryptedCredential
from unicom.models import Message
from unicom.services.get_public_origin import get_public_origin
from django.urls import reverse
from django.utils import timezone
import time

def get_credentials(
    fields: List[dict], 
    update: bool = False
) -> Optional[Dict]:
    """
    Fetches or sets up credentials for the current user/account.

    Args:
        fields (list of dict): List of credential field definitions. Each dict must have:
            - "key" (str, required): Globally unique identifier for this credential (e.g., 'GOOGLE_PLACES_API_KEY').
            - Optional fields:
                - "label" (str): Human-readable label for the credential (default: key as title).
                - "field_type" or "type" (str): Type of the credential field. One of:
                    * "text" (default)
                    * "email"
                    * "number"
                    * "phone"
                    * "password"
                    * "pin"
                - "help_text" or "description" (str): Description/help text for the field.
                - "placeholder" (str): Placeholder text for the input field.
                - "regex_pattern" (str): Optional regex pattern for validation.
                - "min_length" (int): Minimum length for the value.
                - "max_length" (int): Maximum length for the value.
                - "required" (bool): Whether the field is required (default: True).
                - "order" (int): Order for display (default: 0).

        update (bool): If True, always prompt for new values (even if already set).

    Returns:
        dict: If all credentials are available, returns a dict of {key: value, ...}.
        None: If any credential is missing or could not be retrieved.

    Examples:
        # Example 1: Using label, regex_pattern, and placeholder
        creds = get_credentials([
            {"key": "GOOGLE_PLACES_API_KEY", "label": "Google Places API Key", "regex_pattern": "^[A-Za-z0-9]{32}$", "placeholder": "Enter your API key here"}
        ])

        # Example 2: Using type, min_length, max_length, description, and required
        creds = get_credentials([
            {"key": "SERVICE_USERNAME", "type": "text", "min_length": 4, "max_length": 32, "description": "Your service username", "required": True},
            {"key": "SERVICE_PASSWORD", "type": "password", "min_length": 8, "description": "Your service password", "required": True}
        ])
    """
    # Get the caller's frame and its globals
    frame = inspect.currentframe().f_back
    caller_globals = frame.f_globals

    account = caller_globals.get("account")
    bot = caller_globals.get("bot")
    message = caller_globals.get("message")

    if not account or not message:
        raise ValueError("Account and message are required")

    # Map field dicts to CredentialFieldDefinition objects (fetch or create as needed)
    keys = [f["key"] for f in fields]
    credential_defs = list(CredentialFieldDefinition.objects.filter(key__in=keys))
    found_keys = set(cd.key for cd in credential_defs)
    missing_fields = [f for f in fields if f["key"] not in found_keys]

    # Create missing CredentialFieldDefinition objects
    for field in missing_fields:
        cfd = CredentialFieldDefinition(
            key=field["key"],
            label=field.get("label", field["key"].replace('_', ' ').title()),
            field_type=field.get("type", "text"),
            regex_pattern=field.get("regex_pattern", ""),
            min_length=field.get("min_length"),
            max_length=field.get("max_length"),
            help_text=field.get("description", ""),
            placeholder=field.get("placeholder", ""),
            required=field.get("required", True),
            order=field.get("order", 0),
        )
        cfd.full_clean()
        cfd.save()
        credential_defs.append(cfd)

    # Sort credential_defs to match the order of keys
    credential_defs = sorted(credential_defs, key=lambda c: keys.index(c.key))

    return request_credentials(account, bot, message, credential_defs, update=update)

def request_credentials(account: Account, bot: Bot, message: Message, credentials: List[CredentialFieldDefinition], update: bool = False) -> Optional[Dict]:
    """
    Checks for existing credentials. If missing or update=True, creates a setup session and waits for completion.
    Returns a dict of key-value pairs if successful, else None.
    """
    # Check for existing credentials
    creds = {c.key: None for c in credentials}
    existing = EncryptedCredential.objects.filter(account=account, key__in=creds.keys())
    for cred in existing:
        creds[cred.key] = cred.decrypted_value
    missing_keys = [k for k, v in creds.items() if v is None]

    if not missing_keys and not update:
        # All credentials present, return them
        return creds

    # Need to collect credentials from user
    session = CredentialSetupSession.create_session(
        account=account,
        field_definitions=credentials,
        expires_in_minutes=30,
        max_attempts=3,
        metadata={"bot_id": bot.id if bot else None}
    )
    setup_url = reverse('unibot:credential_setup', kwargs={'session_id': session.id})
    absolute_url = f"{get_public_origin()}{setup_url}"  # Relative URL is sufficient (matches admin link)
    msg = (
        "To use this tool, you need to securely provide the following credentials: " +
        ", ".join([c.label for c in credentials]) + ".\n" +
        f"Please use [this secure link]({absolute_url}) to set them up\n" +
        "Your credentials are encrypted and only accessible to you."
    )
    # Use HTML for WebChat so the setup link is clickable; other platforms keep Markdown text
    if message.platform == "WebChat":
        html_msg = (
            "To use this tool, you need to securely provide the following credentials: "
            f"{', '.join([c.label for c in credentials])}.<br>"
            f'Please use <a href="{absolute_url}" target="_blank" rel="noopener noreferrer">this secure link</a> to set them up.<br>'
            "Your credentials are encrypted and only accessible to you."
        )
        message.reply_with({"type": "html", "html": html_msg, "text": html_msg})
    else:
        message.reply_with({"text": msg})

    # Poll for session completion or expiration
    timeout = 0 # 180  # seconds
    poll_interval = 0 # 3  # seconds
    waited = 0
    while waited < timeout:
        session.refresh_from_db()
        if session.is_completed:
            # Fetch the new credentials
            new_creds = {c.key: None for c in credentials}
            updated = EncryptedCredential.objects.filter(account=account, key__in=new_creds.keys())
            for cred in updated:
                new_creds[cred.key] = cred.decrypted_value
            if all(new_creds.values()):
                return new_creds
            else:
                return None
        if session.is_expired:
            return None
        time.sleep(poll_interval)
        waited += poll_interval
    # Timeout
    return None
