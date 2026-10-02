from __future__ import annotations
from typing import TYPE_CHECKING
from django.conf import settings
from django.core.mail import get_connection
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from unicom.services.email.auth_helpers import get_email_service_credentials
from unicom.services.email.save_email_message import save_email_message
from unicom.services.email.email_tracking import prepare_email_for_tracking, remove_tracking
from unicom.services.get_public_origin import get_public_domain
from django.apps import apps
import logging
import re
from email.utils import make_msgid, formataddr
import uuid
import html
import requests
from urllib.parse import urljoin
from django.utils import timezone
from unicom.services.html_inline_images import html_shortlinks_to_base64_images, html_base64_images_to_shortlinks
from unicom.services.template_renderer import (
    render_template as render_unicom_template,
    build_unicom_message_context,
    extract_variable_keys,
    compute_crm_variables,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from unicom.models import Channel


def email_tracking_enabled(config: dict) -> bool:
    """Tracking remains on for existing channels and can be disabled explicitly."""
    return config.get('EMAIL_TRACKING_ENABLED', True) is not False


def convert_text_to_html(text: str) -> str:
    """
    Convert plain text to HTML while preserving formatting.
    Uses <pre> tag to maintain whitespace and newlines.
    Only escapes HTML special characters for security.
    """
    if not text:
        return ""
    
    # Escape HTML special characters
    escaped_text = html.escape(text)
    
    # Wrap in pre tag to preserve formatting
    return f'<pre style="margin: 0; white-space: pre-wrap; word-wrap: break-word;">{escaped_text}</pre>'


def _wrap_email_html(content: str) -> str:
    if not content:
        return ""

    meta_block = (
        '<meta name="color-scheme" content="light dark">\n'
        '  <meta name="supported-color-schemes" content="light dark">\n'
        '  <style>\n'
        '    :root { color-scheme: light dark; }\n'
        '  </style>'
    )

    if re.search(r'<html\b', content, re.IGNORECASE):
        if re.search(r'color-scheme', content, re.IGNORECASE):
            return content
        if re.search(r'<head\b', content, re.IGNORECASE):
            return re.sub(
                r'(<head\b[^>]*>)',
                r'\1\n  ' + meta_block,
                content,
                count=1,
                flags=re.IGNORECASE,
            )
        return re.sub(
            r'(<html\b[^>]*>)',
            r'\1\n<head>\n  ' + meta_block + '\n</head>',
            content,
            count=1,
            flags=re.IGNORECASE,
        )

    return (
        '<html>\n'
        '<head>\n'
        f'  {meta_block}\n'
        '</head>\n'
        '<body>\n'
        f'  {content}\n'
        '</body>\n'
        '</html>'
    )


def _get_reacher_base_url() -> str | None:
    """
    Resolve the configured Reacher endpoint. Accepts multiple environment aliases
    to remain backwards compatible across Django projects that include Unicom.
    """
    base = getattr(settings, 'REACHER_HOSTNAME', None) or getattr(settings, 'REACHER_HOST', None) \
        or getattr(settings, 'REACHER_BASE_URL', None)
    if not base:
        return None
    base = base.strip()
    if not base:
        return None
    if not base.startswith(('http://', 'https://')):
        base = f'http://{base}'
    return base.rstrip('/')


def _reacher_allowed_statuses() -> set[str]:
    mapping = {
        'strict': {'safe'},
        'moderate': {'safe', 'risky'},
        'lenient': {'safe', 'risky', 'unknown'},
    }
    strictness = getattr(settings, 'REACHER_STRICTNESS', 'strict') or 'strict'
    strictness = str(strictness).lower()
    return mapping.get(strictness, mapping['strict'])


def _coerce_skip_reacher_flag(value) -> bool:
    """
    Convert arbitrary truthy/falsy values into a boolean for the skip flag.
    """
    if isinstance(value, str):
        return value.strip().lower() not in ('', '0', 'false', 'off', 'no')
    return bool(value)


def _validate_recipients_with_reacher(recipients: list[str], from_addr: str) -> tuple[bool, dict[str, dict]]:
    """
    Validate the recipient list using Reacher when configured.

    Returns a tuple of (all_safe, results_by_email).
    If Reacher is not configured or the request fails, we allow sending to proceed.
    """
    base_url = _get_reacher_base_url()
    if not base_url or not recipients:
        return True, {}

    endpoint = urljoin(f'{base_url}/', 'v0/check_email')
    timeout = 120
    results: dict[str, dict] = {}
    all_safe = True
    allowed_statuses = _reacher_allowed_statuses()

    seen: set[str] = set()
    for email in recipients:
        if not email or email in seen:
            continue
        seen.add(email)

        try:
            response = requests.post(endpoint, json={'to_email': email}, timeout=timeout)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            logger.warning(
                "Reacher validation failed for %s: %s. Email will be sent without pre-validation.",
                email,
                exc,
            )
            return True, {}
        except ValueError:
            logger.warning("Reacher returned non-JSON response for %s; skipping validation.", email)
            return True, {}

        results[email] = data
        status = str(data.get('is_reachable', '') or '').lower()
        if status and status not in allowed_statuses:
            all_safe = False

    return all_safe, results


def send_email_message(channel: Channel, params: dict, user: User=None):
    """
    Compose, send and save an email using the SMTP/IMAP credentials
    configured on ``channel``.

    The function handles both new email threads and replies:
    
    For new threads:
        - Must provide 'to' list with at least one recipient
        - Must provide 'subject' for the email
        - A new Chat will be created with the sent email's Message-ID
    
    For replies (either option):
        - Option 1: Provide 'chat_id' of an existing email thread
          The last message in the chat will be used as reference
        - Option 2: Provide 'reply_to_message_id' of a specific message
          The referenced message will be used directly
        - Recipients are derived from the original thread unless overridden
        - Subject is derived from parent message if not provided

    Parameters
    ----------
    channel : unicom.models.Channel
        Channel whose ``config`` dictionary supplies ``EMAIL_ADDRESS``,
        ``EMAIL_PASSWORD``, ``SMTP`` and ``IMAP`` settings.
    params : dict
        to       (list[str], required for new threads) – primary recipient addresses
        subject  (str, required for new threads) – subject line for new threads
        chat_id  (str, optional) – ID of existing email thread to reply to
        reply_to_message_id (str, optional) – specific message ID to reply to
        text     (str, optional) – plain-text body
        html     (str, optional) – HTML body. If omitted but *text* is
                                   supplied, it is generated automatically
        cc, bcc (list[str], optional) – additional recipient addresses
        attachments (list[str], optional) – absolute paths of files to attach
    user : django.contrib.auth.models.User, optional
        User responsible for the action

    Returns
    -------
    unicom.models.Message
        The persisted database record representing the sent email.

    Raises
    ------
    ValueError
        - If neither 'to' (new thread) nor 'chat_id'/'reply_to_message_id' (reply) is provided
        - If chat_id is provided but chat doesn't exist or has no messages
        - If reply_to_message_id is provided but message doesn't exist
        - If starting a new thread without a subject
    """
    Message = apps.get_model('unicom', 'Message')
    Chat = apps.get_model('unicom', 'Chat')
    from_addr = channel.config['EMAIL_ADDRESS']
    from_name = (channel.config.get('EMAIL_FROM_NAME') or '').strip()
    smtp_conf = channel.config['SMTP']
    smtp_username, smtp_password = get_email_service_credentials(channel.config, 'SMTP')
    connection = get_connection(
        host=smtp_conf['host'],
        port=smtp_conf['port'],
        username=smtp_username,
        password=smtp_password,
        use_ssl=smtp_conf['use_ssl'],
    )

    # Determine message context (new thread vs reply)
    chat_id = params.get('chat_id')
    reply_to_id = params.get('reply_to_message_id')
    to_addrs = params.get('to', [])
    cc_addrs = params.get('cc', [])
    bcc_addrs = params.get('bcc', [])
    parent = None
    
    # Case 1: Reply to specific message
    if reply_to_id:
        parent = Message.objects.get(id=reply_to_id)
        if not parent:
            raise ValueError(f"Reply-to message not found: {reply_to_id}")
        
    # Case 2: Reply in chat thread
    elif chat_id:
        chat = Chat.objects.get(id=chat_id)
        if not chat:
            raise ValueError(f"Email chat not found: {chat_id}")
            
        parent = chat.messages.filter(
            is_outgoing=False
        ).order_by('-timestamp').first()
        
        if not parent:
            parent = chat.messages.filter(
                is_outgoing=True
            ).order_by('-timestamp').first()
            if not parent:
                raise ValueError(f"No messages found in chat {chat_id} to reply to")
            
    # Case 3: New thread
    elif to_addrs:
        # Validate subject is provided for new threads
        if not params.get('subject'):
            raise ValueError("Subject is required when starting a new email thread")
    else:
        raise ValueError("Must provide either 'to' addresses for new thread, or 'chat_id'/'reply_to_message_id' for reply")

    # If this is a reply, use parent message for threading and recipients
    if parent:
        if parent.is_outgoing:
            # If replying to our own outgoing message, use original recipients
            to_addrs = to_addrs or parent.to
            cc_addrs = params.get('cc', parent.cc)
            bcc_addrs = params.get('bcc', parent.bcc)
        else:
            # If replying to an incoming message, reply to the sender
            to_addrs = to_addrs or [parent.sender.id]
            # Optionally include original recipients in CC (except our own address)
            if not params.get('cc'):
                cc_addrs = [addr for addr in (parent.to + parent.cc) 
                           if addr not in [from_addr, to_addrs] and addr not in to_addrs]
            else:
                cc_addrs = params.get('cc', [])
            bcc_addrs = params.get('bcc', [])
        reply_to_id = parent.id  # Ensure we have the message ID for threading

    logger.info(f"Preparing to send email: to={to_addrs}, cc={cc_addrs}, bcc={bcc_addrs}")

    # Build subject (fall back to "Re: <original>")
    subject = params.get('subject')
    if not subject and params.get('reply_to_message_id'):
        parent = Message.objects.filter(id=params['reply_to_message_id']).first()
        if parent:
            # Remove any existing "Re: " prefixes and add just one
            base = parent.subject or ""
            while base.lower().startswith("re: "):
                base = base[4:]
            subject = "Re: " + base
            logger.debug(f"Created reply subject: {subject} (based on parent: {parent.subject})")
        else:
            subject = ""
            logger.warning(f"Reply-to message not found: {params['reply_to_message_id']}")

    # Generate a message ID and tracking ID before constructing the message
    message_id = make_msgid(domain=get_public_domain())
    tracking_enabled = email_tracking_enabled(channel.config)
    tracking_id = uuid.uuid4() if tracking_enabled else None
    logger.info(f"Generated Message-ID: {message_id}, Tracking-ID: {tracking_id}")

    # Handle HTML content
    text_content = params.get('text', '')
    html_content = params.get('html')
    
    # If HTML is not provided but text is, convert text to HTML
    if not html_content and text_content:
        html_content = convert_text_to_html(text_content)
        logger.debug("Converted plain text to HTML")

    # Optionally render templates for non-CRM use-cases when explicitly requested.
    render_context = params.get('render_context')
    render_variables = params.get('render_variables') or {}
    render_requested = params.get('render_template') or render_context or render_variables
    if render_requested and html_content:
        crm_variables: dict[str, object] = {}
        requested_keys = extract_variable_keys(html_content)
        if requested_keys:
            # Use first To address (if any) to resolve contact for CRM variables.
            primary_email = None
            to_addrs_for_crm = params.get('to') or to_addrs
            if to_addrs_for_crm:
                primary_email = (to_addrs_for_crm[0] or '').strip()
            crm_variables = compute_crm_variables(requested_keys, primary_email)

        base_context = render_context or build_unicom_message_context(
            params=params,
            channel={
                'id': channel.id,
                'name': channel.name,
                'platform': channel.platform,
            },
            user={
                'id': getattr(user, 'id', None),
                'username': getattr(user, 'username', None),
                'email': getattr(user, 'email', None),
            } if user else {},
        )
        merged_variables = {}
        merged_variables.update(crm_variables)
        merged_variables.update(render_variables)
        render_result = render_unicom_template(
            html_content,
            base_context=base_context,
            variables=merged_variables,
        )
        if render_result.errors:
            logger.warning("Template rendering errors: %s", "; ".join(render_result.errors))
        html_content = render_result.html

    # Add tracking
    if html_content:
        from fa2svg.converter import to_inline_png_img
        html_content = _wrap_email_html(html_content)
        html_content = to_inline_png_img(html_content)  # Convert FontAwesome to inline images
        html_content, _ = html_base64_images_to_shortlinks(html_content)  # Convert to public links

    # Prepare HTML content with tracking
    original_urls = []
    if html_content and tracking_enabled:
        html_content, original_urls = prepare_email_for_tracking(html_content, tracking_id)
        logger.debug("Added tracking elements to HTML content")

    # --- Keep as shortlinks for sending (Gmail compatibility) ---
    html_content_for_sending = html_content

    # 1) construct the EmailMultiAlternatives
    email_msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=formataddr((from_name, from_addr)) if from_name else from_addr,
        to=to_addrs,
        cc=cc_addrs,
        bcc=bcc_addrs,
        connection=connection,
        headers={'Message-ID': message_id}  # Set the Message-ID explicitly
    )

    # threading headers
    if params.get('reply_to_message_id'):
        # Get the parent message to build the References header
        parent = Message.objects.filter(id=params['reply_to_message_id']).first()
        references = []
        
        if parent:
            # First add any existing References from parent
            if parent.raw and 'References' in parent.raw:
                references.extend(parent.raw['References'].split())
            # Then add the parent's Message-ID
            references.append(params['reply_to_message_id'])
        else:
            # If parent not found, just use reply_to_message_id
            references = [params['reply_to_message_id']]
            
        email_msg.extra_headers['In-Reply-To'] = params['reply_to_message_id']
        email_msg.extra_headers['References'] = ' '.join(references)
        logger.debug(f"Added threading headers: In-Reply-To={params['reply_to_message_id']}, References={references}")

    # Always attach HTML alternative since we either have original HTML or converted text
    if html_content_for_sending:
        email_msg.attach_alternative(html_content_for_sending, "text/html")
        logger.debug("Added HTML alternative content with tracking and base64 images")

    # Attach files
    for fp in params.get('attachments', []):
        email_msg.attach_file(fp)
        logger.debug(f"Attached file: {fp}")

    recipients_for_validation = list(to_addrs or []) + list(cc_addrs or []) + list(bcc_addrs or [])
    skip_reacher = _coerce_skip_reacher_flag(params.pop('skip_reacher', False))
    if skip_reacher:
        all_safe, reacher_results = True, {}
    else:
        all_safe, reacher_results = _validate_recipients_with_reacher(recipients_for_validation, from_addr)

    # Get the message object and verify the Message-ID BEFORE sending
    msg_before_send = email_msg.message()
    msg_id_before_send = msg_before_send.get('Message-ID', '').strip()
    logger.info(f"Message-ID before send: {msg_id_before_send}")
    if msg_id_before_send != message_id:
        logger.warning(f"Message-ID changed unexpectedly before send. Original: {message_id}, Current: {msg_id_before_send}")

    if not all_safe:
        logger.warning("Reacher validation blocked email send. Recipients=%s", recipients_for_validation)
        mime_bytes = email_msg.message().as_bytes()
        saved_msg = save_email_message(channel, mime_bytes, user)
        if not saved_msg:
            logger.error("save_email_message returned None while recording Reacher-blocked email.")
            return None
        saved_msg.tracking_id = tracking_id
        raw_payload = dict(saved_msg.raw or {})
        raw_payload['original_urls'] = original_urls
        raw_payload['reacher_validation'] = reacher_results
        saved_msg.raw = raw_payload
        if html_content:
            from fa2svg.converter import revert_to_original_fa
            html_for_db = remove_tracking(revert_to_original_fa(html_content), original_urls)
            saved_msg.html = html_for_db

        failure_summaries = []
        allowed_statuses = _reacher_allowed_statuses()
        for email, result in reacher_results.items():
            raw_status = result.get('is_reachable')
            status = str(raw_status).lower() if raw_status else 'unknown'
            if status in allowed_statuses:
                continue
            smtp_error = (
                result.get('smtp', {}).get('error', {}).get('message')
                if isinstance(result.get('smtp'), dict)
                else None
            )
            parts = [status]
            if smtp_error:
                parts.append(smtp_error)
            failure_summaries.append(f"{email}: {' - '.join([part for part in parts if part])}")

        saved_msg.bounced = True
        saved_msg.bounce_type = saved_msg.bounce_type or 'hard'
        summary_text = "; ".join(failure_summaries) if failure_summaries else "Validation returned non-safe status."
        saved_msg.bounce_reason = f"Blocked by Reacher pre-send validation. {summary_text}"
        saved_msg.time_bounced = timezone.now()
        details = (saved_msg.bounce_details or {}).copy()
        details['reacher'] = reacher_results
        saved_msg.bounce_details = details

        update_fields = ['tracking_id', 'raw', 'bounced', 'bounce_type', 'bounce_reason', 'time_bounced', 'bounce_details']
        if html_content:
            update_fields.append('html')
        saved_msg.save(update_fields=update_fields)
        return saved_msg

    # 2) send via the connection we passed in above
    try:
        email_msg.send(fail_silently=False)
        logger.info(f"Email sent successfully")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        raise

    # Get message bytes using the final message to maintain ID consistency
    mime_bytes = email_msg.message().as_bytes()

    # 4) save a copy in the IMAP "Sent" folder
    imap_conf = channel.config['IMAP']
    imap_username, imap_password = get_email_service_credentials(channel.config, 'IMAP')
    import imaplib, time
    try:
        if imap_conf['use_ssl']:
            imap_conn = imaplib.IMAP4_SSL(imap_conf['host'], imap_conf['port'])
        else:
            imap_conn = imaplib.IMAP4(imap_conf['host'], imap_conf['port'])
        
        imap_conn.login(imap_username, imap_password)
        timestamp = imaplib.Time2Internaldate(time.time())
        
        imap_conn.append('Sent', '\\Seen', timestamp, mime_bytes)
        logger.info("Saved copy to IMAP Sent folder")
        imap_conn.logout()
    except Exception as e:
        logger.error(f"Failed to save to IMAP Sent folder: {e}")
        raise

    # 5) delegate to save_email_message (now takes channel first)
    saved_msg = save_email_message(channel, mime_bytes, user)
    
    # Add tracking info and original content to the saved message
    saved_msg.tracking_id = tracking_id
    saved_msg.raw['original_urls'] = original_urls  # Store original URLs in raw field
    # Use the HTML with shortlinks and without tracking for DB
    if html_content:
        from fa2svg.converter import revert_to_original_fa
        html_for_db = remove_tracking(revert_to_original_fa(html_content), original_urls)
        saved_msg.html = html_for_db
    saved_msg.sent = True  # Mark as sent since we successfully sent it
    saved_msg.save(update_fields=['tracking_id', 'raw', 'html', 'sent'])
    
    logger.info(f"Message saved to database with ID: {saved_msg.id} and tracking ID: {tracking_id}")
    
    return saved_msg
