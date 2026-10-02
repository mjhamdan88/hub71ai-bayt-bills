# /unicom/services/email/save_email_message.py
import re
from email import policy, message_from_bytes
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime, getaddresses
from typing import Optional
from django.utils import timezone
import logging

from django.core.files.base import ContentFile
from django.conf import settings
from django.contrib.auth.models import User
from unicom.services.email.email_tracking import remove_tracking
from django.urls import reverse
from unicom.services.get_public_origin import get_public_origin
from unicom.services.html_inline_images import html_base64_images_to_shortlinks
from unicom.services.email.replace_cid_images_with_base64 import replace_cid_images_with_base64

logger = logging.getLogger(__name__)

BOUNCE_SUBJECT_KEYWORDS = (
    'delivery status notification',
    'failure notice',
    'undeliverable',
    'delivery failure',
    'mail delivery failed',
    'returned mail',
    'returned to sender',
)


def _normalize_message_id(value: Optional[str]) -> list[str]:
    if not value:
        return []
    value = value.strip()
    if not value:
        return []
    candidates = [value]
    if value.startswith('<') and value.endswith('>'):
        candidates.append(value[1:-1])
    else:
        candidates.append(f'<{value}>')
    return list(dict.fromkeys(candidates))


def _parse_recipient(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parts = value.split(';', 1)
    candidate = parts[-1].strip()
    return candidate.lower() if candidate else None


def _collect_text_from_part(part: EmailMessage) -> str:
    try:
        return part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b''
        charset = part.get_content_charset() or 'utf-8'
        return payload.decode(charset, errors='ignore')


def _extract_bounce_info(msg: EmailMessage) -> Optional[dict]:
    subject = (msg.get('Subject') or '').lower()
    content_type = (msg.get('Content-Type') or '').lower()
    headers = {key.lower(): value for key, value in msg.items()}

    if not (
        any(keyword in subject for keyword in BOUNCE_SUBJECT_KEYWORDS)
        or 'delivery-status' in content_type
        or 'report-type=delivery-status' in content_type
        or 'x-failed-recipients' in headers
    ):
        return None

    message_id_candidates: list[str] = []
    for header in ('x-original-message-id', 'original-message-id', 'in-reply-to', 'references'):
        value = headers.get(header)
        if not value:
            continue
        if header == 'references':
            for item in value.split():
                message_id_candidates.extend(_normalize_message_id(item))
        else:
            message_id_candidates.extend(_normalize_message_id(value))

    recipients: set[str] = set()
    status_code = ''
    diagnostic_code = ''
    action = ''
    text_snippets: list[str] = []
    embedded_ids: list[str] = []

    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == 'message/delivery-status':
            payload = part.get_payload()
            blocks = payload if isinstance(payload, list) else [payload]
            for block in blocks:
                if not isinstance(block, EmailMessage):
                    continue
                final_recipient = _parse_recipient(block.get('Final-Recipient') or block.get('Original-Recipient'))
                if final_recipient:
                    recipients.add(final_recipient)
                if not status_code and block.get('Status'):
                    status_code = block.get('Status').strip()
                if not diagnostic_code and block.get('Diagnostic-Code'):
                    diagnostic_code = block.get('Diagnostic-Code').strip()
                if not action and block.get('Action'):
                    action = block.get('Action').strip()
        elif ctype == 'message/rfc822':
            payload = part.get_payload()
            embedded_messages = payload if isinstance(payload, list) else [payload]
            for embedded in embedded_messages:
                if isinstance(embedded, EmailMessage):
                    embedded_ids.extend(_normalize_message_id(embedded.get('Message-ID')))
        elif ctype == 'text/plain':
            text_snippets.append(_collect_text_from_part(part))
        elif ctype == 'text/rfc822-headers':
            text_snippets.append(_collect_text_from_part(part))

    if embedded_ids:
        message_id_candidates.extend(embedded_ids)

    suppressed_addresses = {
        addr.lower()
        for _, addr in getaddresses(
            (msg.get_all('To', []) or []) + (msg.get_all('Cc', []) or []) + (msg.get_all('Bcc', []) or [])
        )
    }

    if not diagnostic_code:
        for snippet in text_snippets:
            match = re.search(r'Diagnostic-Code:\s*(.+)', snippet, flags=re.IGNORECASE)
            if match:
                diagnostic_code = match.group(1).strip()
                break

    if not status_code:
        for snippet in text_snippets:
            match = re.search(r'Status:\s*([245]\.\d+\.\d+)', snippet, flags=re.IGNORECASE)
            if match:
                status_code = match.group(1).strip()
                break

    fallback_status = status_code
    fallback_diag = diagnostic_code

    normalized_recipients = {email for email in recipients if email not in suppressed_addresses}

    for snippet in text_snippets:
        for match in re.findall(r'<([^>]+@[^>]+)>', snippet):
            email = match.strip().lower()
            if email and email not in suppressed_addresses:
                normalized_recipients.add(email)
        for match in re.findall(r'([\w\.-]+@[\w\.-]+\.\w+)', snippet):
            email = match.lower()
            if email and email not in suppressed_addresses:
                normalized_recipients.add(email)
        if not fallback_status:
            status_match = re.search(r'([245]\.\d+\.\d+)', snippet)
            if status_match:
                fallback_status = status_match.group(1).strip()
        if not fallback_diag:
            diag_match = re.search(r'(\d{3}\s+\d\.\d\.\d.+)', snippet)
            if diag_match:
                fallback_diag = diag_match.group(1).strip()
        if not fallback_diag:
            # fall back to first non-empty line mentioning "said:"
            said_match = re.search(r'said:\s*(.+)', snippet, flags=re.IGNORECASE)
            if said_match:
                fallback_diag = said_match.group(1).strip()

        if 'message-id' in snippet.lower():
            for msg_id in re.findall(r'Message-ID:\s*<([^>]+)>', snippet, flags=re.IGNORECASE):
                message_id_candidates.extend(_normalize_message_id(msg_id))

    message_id_candidates = list(dict.fromkeys(message_id_candidates))
    normalized_recipients = {
        email
        for email in normalized_recipients
        if email not in {cid.strip('<>') for cid in message_id_candidates}
    }

    if not normalized_recipients and not message_id_candidates:
        return None

    status_code = fallback_status or status_code
    diagnostic_code = fallback_diag or diagnostic_code

    bounce_type = ''
    if status_code and status_code.startswith('5'):
        bounce_type = 'hard'
    elif status_code and status_code.startswith('4'):
        bounce_type = 'soft'

    diagnostic_summary = diagnostic_code or (text_snippets[0].strip() if text_snippets else '')

    return {
        'message_ids': list(dict.fromkeys(message_id_candidates)),
        'recipients': sorted(normalized_recipients),
        'status': status_code,
        'diagnostic': diagnostic_summary,
        'bounce_type': bounce_type,
        'action': action.lower() if action else '',
        'subject': msg.get('Subject'),
        'body_preview': (text_snippets[0].strip() if text_snippets else ''),
    }


def _find_message_for_bounce(bounce_info: dict):
    from unicom.models import Message as MessageModel

    candidates = bounce_info.get('message_ids') or []
    checked: set[str] = set()

    for candidate in candidates:
        for variant in _normalize_message_id(candidate):
            if variant in checked:
                continue
            checked.add(variant)
            message = MessageModel.objects.filter(id=variant).first()
            if message:
                return message

    recipients = bounce_info.get('recipients') or []
    for email in recipients:
        if not email:
            continue
        message = MessageModel.objects.filter(to__contains=[email]).order_by('-timestamp').first()
        if message:
            return message

    return None


def _apply_bounce_to_message(message, bounce_info: dict) -> bool:
    from unicom.models import Message as MessageModel

    if not isinstance(message, MessageModel):
        return False

    updated_fields: list[str] = []

    bounce_type = bounce_info.get('bounce_type') or ''
    if bounce_type and message.bounce_type != bounce_type:
        message.bounce_type = bounce_type
        updated_fields.append('bounce_type')

    diagnostic = bounce_info.get('diagnostic') or ''
    body_preview = bounce_info.get('body_preview') or ''
    reason_parts = [part for part in (diagnostic, body_preview) if part]
    reason_text = reason_parts[0] if reason_parts else 'Email bounced'
    if message.bounce_reason != reason_text:
        message.bounce_reason = reason_text
        updated_fields.append('bounce_reason')

    if not message.bounced:
        message.bounced = True
        updated_fields.append('bounced')

    timestamp = timezone.now()
    if message.time_bounced != timestamp:
        message.time_bounced = timestamp
        updated_fields.append('time_bounced')

    details = (message.bounce_details or {}).copy()
    details.update({
        'status': bounce_info.get('status'),
        'diagnostic_code': bounce_info.get('diagnostic'),
        'action': bounce_info.get('action'),
        'recipients': bounce_info.get('recipients'),
        'subject': bounce_info.get('subject'),
    })
    if details != (message.bounce_details or {}):
        message.bounce_details = details
        updated_fields.append('bounce_details')

    if message.delivered:
        message.delivered = False
        updated_fields.append('delivered')
    if message.sent:
        message.sent = False
        updated_fields.append('sent')

    if not updated_fields:
        return False

    message.save(update_fields=updated_fields)
    return True


def _is_email_authenticated(msg, from_email: str) -> bool:
    """
    Professional email authentication using battle-tested libraries.
    Uses authheaders library for comprehensive SPF/DKIM/DMARC validation.
    """
    # TODO: Temporarily skip authheaders due to 'NoneType' split() crashes
    return _basic_email_check(msg, from_email)
    try:
        from authheaders import authenticate_message
        import io

        # Defensive check: ensure critical headers are not None
        critical_headers = ['From', 'Message-ID', 'Date']
        for header in critical_headers:
            if msg.get(header) is None:
                logger.warning(f"Critical header {header} is None, skipping authheaders")
                return _basic_email_check(msg, from_email)

        # Convert email message back to bytes for authheaders library
        msg_bytes = msg.as_bytes()
        msg_fp = io.BytesIO(msg_bytes)

        # Use authheaders library to perform comprehensive authentication
        auth_result = authenticate_message(
            msg_fp,
            'unicom',  # Our auth service identifier
            spf=True,   # Enable SPF checks
            dkim=True,  # Enable DKIM checks
            dmarc=True, # Enable DMARC checks
            dnsfunc=None  # Use default DNS resolution
        )

        # Parse the Authentication-Results header generated by authheaders
        auth_header = str(auth_result)
        logger.info(f"Authentication result for {from_email}: {auth_header}")

        # Check for authentication failures
        if any(check in auth_header.lower() for check in ['spf=fail', 'spf=soft-fail', 'spf=softfail']):
            logger.warning(f"SPF failed for {from_email}")
            return False

        if 'dkim=fail' in auth_header.lower():
            logger.warning(f"DKIM failed for {from_email}")
            return False

        if 'dmarc=fail' in auth_header.lower():
            logger.warning(f"DMARC failed for {from_email}")
            return False

        # Require at least SPF or DKIM to pass for security
        has_spf_pass = 'spf=pass' in auth_header.lower()
        has_dkim_pass = 'dkim=pass' in auth_header.lower()
        has_dmarc_pass = 'dmarc=pass' in auth_header.lower()

        if has_spf_pass or has_dkim_pass or has_dmarc_pass:
            logger.info(f"Email authentication passed for {from_email}")
            return True

        # If no authentication passes, be strict and reject for security
        logger.warning(f"No authentication checks passed for {from_email}")
        return False

    except ImportError:
        logger.error("authheaders library not installed - falling back to basic checks. Install with 'pip install authheaders>=0.15.0'")
        return _basic_email_check(msg, from_email)
    except Exception as e:
        import traceback
        logger.error(f"Email authentication error for {from_email}: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        logger.error(f"Email headers causing the issue: {dict(msg.items())}")
        return _basic_email_check(msg, from_email)


def _normalize_domain(value: str | None) -> str:
    if not value:
        return ''
    candidate = value.strip()
    if '@' in candidate:
        candidate = candidate.split('@', 1)[1]
    return candidate.strip().lower().rstrip('.')


def _domains_align(candidate: str | None, reference: str | None) -> bool:
    if not candidate or not reference:
        return False
    candidate = candidate.lower()
    reference = reference.lower()
    return candidate == reference or candidate.endswith('.' + reference)


def _parse_authentication_results(headers: list[str]) -> dict[str, list[dict]]:
    results: dict[str, list[dict]] = {'spf': [], 'dkim': [], 'dmarc': []}
    for header in headers:
        for segment in header.split(';'):
            part = segment.strip()
            if not part:
                continue
            if part.lower().startswith('spf='):
                result = part.split('=', 1)[1].split()[0].lower()
                domain_match = re.search(r'smtp\.mail=([^;\s]+)', part, flags=re.IGNORECASE)
                domain = _normalize_domain(domain_match.group(1) if domain_match else '')
                results['spf'].append({'result': result, 'domain': domain})
            elif part.lower().startswith('dkim='):
                result = part.split('=', 1)[1].split()[0].lower()
                dmatch = re.search(r'header\.i=([^;\s]+)', part, flags=re.IGNORECASE)
                domain = _normalize_domain(dmatch.group(1) if dmatch else '')
                results['dkim'].append({'result': result, 'domain': domain})
            elif part.lower().startswith('dmarc='):
                result = part.split('=', 1)[1].split()[0].lower()
                dmatch = re.search(r'header\.from=([^;\s]+)', part, flags=re.IGNORECASE)
                domain = _normalize_domain(dmatch.group(1) if dmatch else '')
                results['dmarc'].append({'result': result, 'domain': domain})
    return results


def _basic_email_check(msg, from_email: str) -> bool:
    """Fallback authentication check if authheaders library fails"""
    auth_headers = msg.get_all('Authentication-Results', [])
    if not auth_headers:
        logger.warning(f"No authentication information available for {from_email} - rejecting for security")
        return False

    parsed_results = _parse_authentication_results(auth_headers)
    from_domain = _normalize_domain(parseaddr(msg.get('From', ''))[1])

    # DMARC takes precedence when present
    for entry in parsed_results.get('dmarc', []):
        domain = entry.get('domain')
        result = entry.get('result')
        if result == 'pass' and _domains_align(domain, from_domain):
            logger.info(f"DMARC passed for {from_email} ({domain})")
            return True
        if result in {'fail', 'reject'} and _domains_align(domain, from_domain):
            logger.warning(f"DMARC failed for {from_email}: {auth_headers}")
            return False

    # SPF alignment
    for entry in parsed_results.get('spf', []):
        if entry.get('result') == 'pass' and _domains_align(entry.get('domain'), from_domain):
            logger.info(f"SPF aligned pass for {from_email} via {entry.get('domain')}")
            return True

    # DKIM alignment
    for entry in parsed_results.get('dkim', []):
        if entry.get('result') == 'pass' and _domains_align(entry.get('domain'), from_domain):
            logger.info(f"DKIM aligned pass for {from_email} via {entry.get('domain')}")
            return True

    logger.warning(f"No aligned SPF/DKIM/DMARC pass for {from_email}: {auth_headers}")
    return False


def save_email_message(channel, raw_message_bytes: bytes, user: User = None, uid: int = None, historical=False):
    """
    Save an email into Message, creating Account, Chat, AccountChat as needed.
    `raw_message_bytes` should be the full RFC-5322 bytes you get from IMAPClient.fetch(uid, ['BODY.PEEK[]'])
    """
    from unicom.models import Message, Chat, Account, AccountChat, Channel

    platform = 'Email'
    msg = message_from_bytes(raw_message_bytes, policy=policy.default)
    from_name, from_email = parseaddr(msg.get('From', ''))
    config = channel.config or {}
    bot_email = (config.get('EMAIL_ADDRESS') or '').lower()
    is_outgoing = bool(bot_email) and from_email.lower() == bot_email

    hdr_id = msg.get('Message-ID')
    if hdr_id:
        existing_msg = Message.objects.filter(id=hdr_id).first()
        if existing_msg:
            return existing_msg

    email_verified = True
    bounce_info = _extract_bounce_info(msg)

    if not is_outgoing:
        if bounce_info:
            original_message = _find_message_for_bounce(bounce_info)
            if original_message:
                updated = _apply_bounce_to_message(original_message, bounce_info)
                if updated:
                    logger.info(
                        "Marked message %s as bounced based on notification %s.",
                        original_message.id,
                        msg.get('Message-ID'),
                    )
            else:
                logger.warning(
                    "Bounce notification received but no matching message found. Candidates=%s recipients=%s",
                    bounce_info.get('message_ids'),
                    bounce_info.get('recipients'),
                )
        else:
            if not _is_email_authenticated(msg, from_email):
                logger.warning(f"Unauthenticated email from {from_email}")
                email_verified = False

    account = Account.objects.filter(platform=platform, id=from_email).first()
    if account and account.blocked:
        return None

    hdr_in_reply = msg.get('In-Reply-To')
    hdr_references = (msg.get('References') or '').split()
    hdr_subject = msg.get('Subject', '')
    subject_ellipsis = '...'
    max_subject_len = 100
    if hdr_subject and len(hdr_subject) > max_subject_len:
        truncated_subject = hdr_subject[: max_subject_len - len(subject_ellipsis)] + subject_ellipsis
    else:
        truncated_subject = hdr_subject or ''
    date_hdr = msg.get('Date')

    logger.debug(
        "Processing email - Message-ID: %s, In-Reply-To: %s, References: %s",
        hdr_id,
        hdr_in_reply,
        hdr_references,
    )

    try:
        raw_ts = parsedate_to_datetime(date_hdr)
        if raw_ts is not None:
            if raw_ts.tzinfo is None:
                raw_ts = timezone.make_aware(raw_ts, timezone.utc)
            timestamp = raw_ts
        else:
            timestamp = timezone.now()
    except Exception:
        timestamp = timezone.now()

    sender_name, sender_email = parseaddr(msg.get('From'))
    sender_name = sender_name or sender_email

    raw_to = msg.get_all('To', [])
    raw_cc = msg.get_all('Cc', [])
    raw_bcc = msg.get_all('Bcc', [])

    to_list = [email for _, email in getaddresses(raw_to)]
    cc_list = [email for _, email in getaddresses(raw_cc)]
    bcc_list = [email for _, email in getaddresses(raw_bcc)]

    parent_msg = None
    chat_obj = None

    if hdr_in_reply:
        for variant in _normalize_message_id(hdr_in_reply):
            parent_msg = Message.objects.filter(platform=platform, id=variant).first()
            if parent_msg:
                chat_obj = parent_msg.chat
                logger.debug("Found parent message %s in chat %s via In-Reply-To", parent_msg.id, chat_obj.id)
                break

    if not parent_msg and hdr_references:
        for ref in reversed(hdr_references):
            for variant in _normalize_message_id(ref):
                parent_msg = Message.objects.filter(platform=platform, id=variant).first()
                if parent_msg:
                    chat_obj = parent_msg.chat
                    logger.debug("Found parent message %s in chat %s via References", parent_msg.id, chat_obj.id)
                    break
            if parent_msg:
                break

    if not chat_obj:
        try:
            channel.refresh_from_db()
        except Channel.DoesNotExist:
            logger.error("Channel %s no longer exists, cannot create chat", channel.id)
            return None

        chat_obj, created = Chat.objects.get_or_create(
            platform=platform,
            id=hdr_id,
            defaults={'channel': channel, 'is_private': True, 'name': truncated_subject},
        )
        if created:
            logger.debug("Created new chat %s for message %s", chat_obj.id, hdr_id)

    account_obj, _ = Account.objects.get_or_create(
        platform=platform,
        id=sender_email,
        defaults={'channel': channel, 'name': sender_name, 'is_bot': is_outgoing, 'raw': dict(msg.items())},
    )
    AccountChat.objects.get_or_create(account=account_obj, chat=chat_obj)

    text_parts: list[str] = []
    html_parts: list[str] = []
    for part in msg.walk():
        if part.get_content_disposition() == 'attachment':
            continue
        ctype = part.get_content_type()
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or 'utf-8'
        content = payload.decode(charset, errors='replace')
        if ctype == 'text/plain':
            text_parts.append(content)
        elif ctype == 'text/html':
            html_parts.append(content)

    body_text = "\n".join(text_parts).strip()
    body_html = "\n".join(html_parts).strip() or None

    if body_html:
        patched_html = replace_cid_images_with_base64(raw_message_bytes)
        if patched_html:
            body_html = patched_html

    if body_html and chat_obj and hdr_references:
        from unicom.services.email.quote_filter import filter_redundant_quoted_content
        body_html = filter_redundant_quoted_content(body_html, chat_obj, hdr_references)

    if is_outgoing and body_html:
        original_urls: list[str] = []
        if parent_msg and parent_msg.raw.get('original_urls'):
            original_urls = parent_msg.raw['original_urls']
        body_html = remove_tracking(body_html, original_urls)

    if body_html and not body_text:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(body_html, 'html.parser')
        body_text = soup.get_text(separator='\n', strip=True)

    inline_image_pks: list[int] = []
    if body_html:
        body_html, inline_image_pks = html_base64_images_to_shortlinks(body_html)

    raw_headers = dict(msg.items())
    if historical:
        # Historical imports provide reply context, but must not enter the
        # new-message request/automation pipeline.
        raw_headers['skip_request_creation'] = True
        raw_headers['historical_import'] = True

    msg_obj, created = Message.objects.get_or_create(
        platform=platform,
        chat=chat_obj,
        id=hdr_id,
        defaults={
            'sender': account_obj,
            'sender_name': sender_name,
            'is_outgoing': is_outgoing,
            'user': user,
            'text': body_text,
            'html': body_html,
            'subject': hdr_subject,
            'timestamp': timestamp,
            'reply_to_message': parent_msg,
            'raw': raw_headers,
            'to': to_list,
            'cc': cc_list,
            'bcc': bcc_list,
            'media_type': 'html',
            'channel': channel,
            'imap_uid': uid,
            'email_sender_authenticated': email_verified,
        },
    )

    if inline_image_pks:
        from unicom.models import EmailInlineImage
        EmailInlineImage.objects.filter(pk__in=inline_image_pks).update(email_message=msg_obj)

    if not created:
        logger.debug("Message %s already exists in chat %s", msg_obj.id, chat_obj.id)
        return msg_obj

    logger.debug("Created new message %s in chat %s", msg_obj.id, chat_obj.id)

    attachments = [
        part
        for part in msg.iter_attachments()
        if part.get_content_disposition() == 'attachment' and not part.get('Content-ID')
    ]
    if attachments:
        media_part = attachments[0]
        data = media_part.get_payload(decode=True)
        if data:
            fname = media_part.get_filename() or 'attachment'
            cf = ContentFile(data)
            msg_obj.media.save(fname, cf, save=True)
            ctype = media_part.get_content_type()
            if ctype.startswith('image/'):
                msg_obj.media_type = 'image'
            elif ctype.startswith('audio/'):
                msg_obj.media_type = 'audio'
            else:
                msg_obj.media_type = 'file'
            msg_obj.save(update_fields=['media', 'media_type'])

    return msg_obj
