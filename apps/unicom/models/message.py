from __future__ import annotations
from typing import TYPE_CHECKING
from django.db import models
from django.contrib.auth.models import User
from unicom.models.constants import channels
from django.contrib.postgres.fields import ArrayField
from django.core.validators import validate_email
import uuid
import json
import re
import os
from bs4 import BeautifulSoup
import base64
from .fields import DedupFileField, only_delete_file_if_unused
from unicom.services.get_public_origin import get_public_origin
from openai import OpenAI
from openai import OpenAIError
from django.conf import settings
from pydub import AudioSegment
import io

if TYPE_CHECKING:
    from unicom.models import Channel


MAX_LLM_TOOL_RESPONSE_CHARS = 32_000
MAX_LLM_GITHUB_TOOL_RESPONSE_CHARS = 16_000


def _bounded_tool_response_content(tool_response_data):
    """Prevent one persisted tool result from multiplying context on every turn."""
    content = str(tool_response_data.get('result', '') or '')
    tool_name = str(tool_response_data.get('tool_name') or '')
    limit = (
        MAX_LLM_GITHUB_TOOL_RESPONSE_CHARS
        if tool_name in {'dashboard_read_github_file', 'dashboard_list_github_directory'}
        else MAX_LLM_TOOL_RESPONSE_CHARS
    )
    if len(content) <= limit:
        return content
    guidance = (
        "Use dashboard_list_github_directory and dashboard_read_github_file with "
        "offset/max_chars to retrieve only the needed range."
        if tool_name.startswith('dashboard_') and 'github' in tool_name
        else "Call the source tool again with narrower pagination or filters."
    )
    return json.dumps({
        "status": "OMITTED_FROM_HISTORY",
        "tool_name": tool_name,
        "original_chars": len(content),
        "message": "This oversized historical tool result was omitted from model context.",
        "navigation": guidance,
    })

def get_openai_client():
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key:
        raise OpenAIError(
            "OPENAI_API_KEY is required only for LLM features such as Message.reply_using_llm()."
        )
    return OpenAI(api_key=api_key)


class Message(models.Model):
    TYPE_CHOICES = [
        ('text', 'Text'),
        ('html', 'HTML'),
        ('image', 'Image'),
        ('audio', 'Audio'),
        ('tool_call', 'Tool Call'),
        ('tool_response', 'Tool Response'),
    ]
    EMAIL_BOUNCE_TYPE_CHOICES = [
        ('hard', 'Hard bounce'),
        ('soft', 'Soft bounce'),
    ]
    id = models.CharField(max_length=500, primary_key=True)
    provider_message_id = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        db_index=True,
        help_text="Raw provider message id (e.g., Telegram message_id)"
    )
    channel = models.ForeignKey('unicom.Channel', on_delete=models.CASCADE)
    platform = models.CharField(max_length=100, choices=channels)
    sender = models.ForeignKey('unicom.Account', on_delete=models.RESTRICT)
    user = models.ForeignKey(User, on_delete=models.RESTRICT, null=True, blank=True)
    chat = models.ForeignKey('unicom.Chat', on_delete=models.CASCADE, related_name='messages')
    is_outgoing = models.BooleanField(null=True, default=None, help_text="True for outgoing messages, False for incoming, None for internal")
    sender_name = models.CharField(max_length=100)
    email_sender_authenticated = models.BooleanField(
        default=True,
        help_text="Email-only: True when sender identity passed SPF/DKIM/DMARC (always True for other platforms).",
    )
    subject = models.CharField(max_length=512, blank=True, null=True, help_text="Subject of the message (only for email messages)")
    text = models.TextField()
    html = models.TextField(
        blank=True, null=True,
        help_text="Full HTML body (only for email messages)"
    )
    to  = ArrayField(
        base_field=models.EmailField(validators=[validate_email]),
        blank=True,
        default=list,
        help_text="List of To: addresses",
    )
    cc  = ArrayField(
        base_field=models.EmailField(validators=[validate_email]),
        blank=True,
        default=list,
        help_text="List of Cc: addresses",
    )
    bcc = ArrayField(
        base_field=models.EmailField(validators=[validate_email]),
        blank=True,
        default=list,
        help_text="List of Bcc: addresses",
    )
    media = models.FileField(upload_to='media/', blank=True, null=True)
    reply_to_message = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    response_to_tool_call = models.ForeignKey(
        'unicom.ToolCall', on_delete=models.SET_NULL, null=True, blank=True, 
        related_name='response_messages',
        help_text="The ToolCall that this message is responding to (for assistant messages from tool responses)"
    )
    timestamp = models.DateTimeField()
    time_sent = models.DateTimeField(null=True, blank=True)
    time_delivered = models.DateTimeField(null=True, blank=True)
    time_seen = models.DateTimeField(null=True, blank=True)
    sent = models.BooleanField(default=False)
    delivered = models.BooleanField(default=False)
    seen = models.BooleanField(default=False)
    raw = models.JSONField()
    media_type = models.CharField(
        max_length=15,
        choices=TYPE_CHOICES,
        default='text'
    )
    # Email tracking fields
    tracking_id = models.UUIDField(default=uuid.uuid4, null=True, blank=True, help_text="Unique ID for tracking email opens and clicks")
    open_count = models.PositiveIntegerField(default=0, help_text="Number of times the email open pixel was fetched")
    time_opened = models.DateTimeField(null=True, blank=True, help_text="When the email was first opened")
    opened = models.BooleanField(default=False, help_text="Whether the email has been opened")
    time_link_clicked = models.DateTimeField(null=True, blank=True, help_text="When a link in the email was first clicked")
    link_clicked = models.BooleanField(default=False, help_text="Whether any link in the email has been clicked")
    clicked_links = ArrayField(
        base_field=models.URLField(),
        blank=True,
        null=True,
        default=list,
        help_text="List of links that have been clicked"
    )
    bounced = models.BooleanField(default=False, help_text="Whether the email was reported as bounced by the provider")
    bounce_type = models.CharField(
        max_length=20,
        choices=EMAIL_BOUNCE_TYPE_CHOICES,
        blank=True,
        help_text="Classification of the bounce when available"
    )
    time_bounced = models.DateTimeField(null=True, blank=True, help_text="When the bounce notification was received")
    bounce_reason = models.TextField(blank=True, help_text="Provider-supplied reason for the bounce")
    bounce_details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw provider payload for the bounce event"
    )
    imap_uid = models.BigIntegerField(null=True, blank=True, db_index=True, help_text="IMAP UID for marking as seen")

    def edit_original_message(self, msg_dict: dict) -> bool:
        """
        Edit the original message (for callback messages that want to update the button message).
        For callback messages, this edits the message that contained the buttons.

        Args:
            msg_dict: Dictionary with new content (text, reply_markup, etc.)

        Returns:
            bool: True if edit was successful
        """
        if self.platform == 'Telegram':
            from unicom.services.telegram.edit_telegram_message import edit_telegram_message

            # For callback messages, edit the original message
            target_message = self.reply_to_message if self.reply_to_message else self

            return edit_telegram_message(self.channel, target_message, msg_dict)

        # For other platforms, fall back to sending a new message
        self.reply_with(msg_dict)
        return True

    def reply_with(self, msg_dict:dict) -> Message:
        """
        Reply to this message with a dictionary containing the response.
        The dictionary can contain 'text', 'html', 'file_path', etc.
        
        For tool response messages, this will send the reply to the original user message
        while maintaining the chain by setting reply_to_message to this tool response.
        """
        # Handle tool response messages - send to original user but maintain chain
        if self.media_type == 'tool_response':
            # Get the request using reverse lookup
            request = self.request_set.first()  # tool response message -> request
            if request:
                initial_request = request.initial_request or request
                target_message = initial_request.message
                
                # Get the ToolCall that this response came from
                tool_call = request.tool_calls.first()
                
                # Send reply to original user message
                reply_msg = target_message.reply_with(msg_dict)
                
                # Set the reply chain and tool call reference
                reply_msg.reply_to_message = self
                if tool_call:
                    reply_msg.response_to_tool_call = tool_call
                reply_msg.save(update_fields=['reply_to_message', 'response_to_tool_call'])
                
                return reply_msg
        
        # Normal case - reply to this message directly
        from unicom.services.crossplatform.reply_to_message import reply_to_message
        return reply_to_message(self.channel, self, msg_dict)

    @property
    def original_content_with_base64_icons(self):
        """
        Returns the HTML content with inline images as base64 and Font Awesome icons converted to base64 PNG images.
        This is the most portable format as it doesn't require any external dependencies.
        """
        from fa2svg.converter import to_inline_png_img
        html = self.html_with_base64_images if self.platform == 'Email' else self.text
        return to_inline_png_img(html) if self.platform == 'Email' else html

    @property
    def original_content_with_svg_icons(self):
        """
        Returns the HTML content with inline images as base64 and Font Awesome icons converted to inline SVG.
        This preserves vector graphics quality but may increase the HTML size.
        """
        from fa2svg.converter import revert_to_original_fa
        html = self.html_with_base64_images if self.platform == 'Email' else self.text
        return revert_to_original_fa(html) if self.platform == 'Email' else html

    @property
    def original_content_with_cdn_icons(self):
        """
        Returns the HTML content with inline images as base64 and Font Awesome icons using CDN.
        This is the lightest option but requires internet connection to load icons.
        """
        html = self.html_with_base64_images if self.platform == 'Email' else self.text
        if self.platform == 'Email' and html:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            # Add Font Awesome CDN if not already present
            head = soup.find('head')
            if not head:
                head = soup.new_tag('head')
                soup.insert(0, head)
            if not soup.find('link', {'href': lambda x: x and 'font-awesome' in x}):
                fa_link = soup.new_tag('link', rel='stylesheet', 
                    href='https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css')
                head.append(fa_link)
            return str(soup)
        return html

    @property
    def html_with_base64_images(self):
        """
        Returns the HTML content with all inline image shortlinks replaced by their original base64 data, if available.
        """
        if not self.html:
            return self.html
        soup = BeautifulSoup(self.html, 'html.parser')
        # Map shortlink src to base64 for all inline images
        images = {img.get_short_id(): img for img in self.inline_images.all()}
        for img_tag in soup.find_all('img'):
            src = img_tag.get('src', '')
            # Extract short id from src (e.g., /i/abc123 or full URL)
            m = re.search(r'/i/([A-Za-z0-9]+)', src)
            if m:
                short_id = m.group(1)
                image_obj = images.get(short_id)
                if image_obj:
                    # Read file and encode as base64
                    data = image_obj.file.read()
                    image_obj.file.seek(0)
                    mime = 'image/png'  # Default
                    if hasattr(image_obj.file, 'file') and hasattr(image_obj.file.file, 'content_type'):
                        mime = image_obj.file.file.content_type
                    elif image_obj.file.name:
                        import mimetypes
                        mime = mimetypes.guess_type(image_obj.file.name)[0] or 'image/png'
                    b64 = base64.b64encode(data).decode('ascii')
                    img_tag['src'] = f'data:{mime};base64,{b64}'
        return str(soup)

    def debug_thread_chain(self, depth=10):
        """Debug method to see the thread chain"""
        chain = []
        cur = self
        for i in range(depth):
            if not cur:
                break
            chain.append({
                'id': cur.id,
                'text': cur.text[:50] + '...' if len(cur.text) > 50 else cur.text,
                'media_type': cur.media_type,
                'is_outgoing': cur.is_outgoing,
                'reply_to_message_id': cur.reply_to_message_id if cur.reply_to_message else None
            })
            cur = cur.reply_to_message
        return chain

    def as_llm_chat(self, depth=129, mode="chat", system_instruction=None, multimodal=True):
        """
        Returns a list of dicts for LLM chat APIs (OpenAI, Gemini, etc), each with 'role' and 'content'.
        - depth: max number of messages to include
        - mode: 'chat' (previous N in chat) or 'thread' (follow reply_to_message chain)
        - system_instruction: if provided, prepends a system message
        - multimodal: if True, includes media (image/audio) as content or URLs
        """
        def msg_to_dict(msg):
            # Determine role
            if msg.is_outgoing is True:
                role = "assistant"
            elif msg.is_outgoing is False:
                role = "user"
            else:
                role = "system"
            # Determine content
            content = None
            if msg.media and multimodal and msg.media_type == "image":
                # Prepare data URL for image
                b64 = None
                mime = None
                try:
                    msg.media.open('rb')
                    data = msg.media.read()
                    msg.media.seek(0)
                    import mimetypes, os
                    mime = mimetypes.guess_type(msg.media.name)[0] or 'image/png'
                    b64 = base64.b64encode(data).decode('ascii')
                except Exception:
                    b64 = None
                    mime = 'image/png'
                data_url = f"data:{mime};base64,{b64}" if b64 else None
                content_list = []
                if data_url:
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": data_url}
                    })
                # If there is text/caption, add as separate dict
                if msg.text:
                    content_list.append({
                        "type": "text",
                        "text": msg.text
                    })
                content = content_list
            elif msg.media_type == "audio":
                content_list = []
                audio_processed = False
                
                # First check if we have an audio_id in raw field
                if msg.is_outgoing and msg.raw and msg.raw.get('audio_id'):
                    audio_id = msg.raw['audio_id']
                    # For assistant messages, we include the audio_id as text since OpenAI doesn't accept audio references
                    # in assistant messages
                    content = msg.text or ""
                    if content == "**Voice Message**":
                        content = ""  # Don't include the default voice message text
                # If no audio_id and we have media file, process it as before
                elif msg.media and multimodal:
                    # Convert audio to mp3 using pydub before base64 encoding
                    try:
                        msg.media.open('rb')
                        data = msg.media.read()
                        msg.media.seek(0)
                        import os
                        orig_ext = os.path.splitext(msg.media.name)[1][1:] or 'wav'
                        
                        # Handle oga extension for pydub
                        format_ext = orig_ext
                        if format_ext == 'oga':
                            format_ext = 'ogg'

                        audio = AudioSegment.from_file(io.BytesIO(data), format=format_ext)
                        mp3_io = io.BytesIO()
                        audio.export(mp3_io, format='mp3')
                        mp3_data = mp3_io.getvalue()
                        b64 = base64.b64encode(mp3_data).decode('ascii')
                        content_list = []
                        if msg.text and msg.text != "**Voice Message**":
                            content_list.append({
                                "type": "text",
                                "text": msg.text
                            })
                        content_list.append({
                            "type": "input_audio",
                            "input_audio": {"data": b64, "format": "mp3"}
                        })
                        content = content_list
                        audio_processed = True
                    except Exception as e:
                        # Re-enable for debugging if needed
                        # print(f"DEBUG: Could not process audio file for message {msg.id}. Error: {e}")
                        content = msg.text or ""  # Fallback to text
                else:
                    content = msg.text or ""
            elif msg.media_type == "html" and msg.html:
                content = msg.html
            elif msg.media_type == "tool_call":
                # Tool call messages - format for LLM API
                tool_call_data = msg.raw.get('tool_call', {})
                # Convert arguments to JSON string if it's a dict
                arguments = tool_call_data.get('arguments', {})
                if isinstance(arguments, dict):
                    import json
                    arguments = json.dumps(arguments)
                d = {
                    "role": "assistant",  # Tool calls are always from assistant
                    "content": None,      # Tool calls should have null content
                    "tool_calls": [{
                        "id": tool_call_data.get('id', f"call_{msg.id}"),
                        "type": "function",
                        "function": {
                            "name": tool_call_data.get('name', ''),
                            "arguments": arguments
                        }
                    }]
                }
                return d
            elif msg.media_type == "tool_response":
                # Tool response messages - format for LLM API
                tool_response_data = msg.raw.get('tool_response', {})
                d = {
                    "role": "tool",
                    "tool_call_id": tool_response_data.get('call_id', ''),
                    "content": _bounded_tool_response_content(tool_response_data)
                }
                return d
            else:
                content = msg.text or ""
            d = {"role": role, "content": content}
            return d

        messages = []
        if mode == "chat":
            qs = self.chat.messages.order_by("timestamp")
            idx = list(qs.values_list("id", flat=True)).index(self.id)
            start = max(0, idx - depth + 1)
            selected = list(qs[start:idx+1])
            
            # Handle user interruption for tool response messages in chat mode
            if self.media_type == "tool_response" and not selected_roots:
                # Find any user message that came chronologically after any tool call in our range
                tool_call_timestamps = [m.timestamp for m in selected if m.media_type == "tool_call"]
                if tool_call_timestamps:
                    latest_tool_call_time = max(tool_call_timestamps)
                    # Look for user messages after the latest tool call but before this tool response
                    user_interrupt = self.chat.messages.filter(
                        is_outgoing=False,
                        timestamp__gt=latest_tool_call_time,
                        timestamp__lt=self.timestamp
                    ).exclude(
                        media_type__in=['tool_call', 'tool_response']
                    ).order_by('-timestamp').first()
                    
                    if user_interrupt:
                        # Found user interrupt - get conversation from that user message
                        return user_interrupt.as_llm_chat(depth=depth, mode=mode,
                                                        system_instruction=system_instruction,
                                                        multimodal=multimodal)
            
            for m in selected:
                messages.append(msg_to_dict(m))
        elif mode == "thread":
            chain = []
            cur = self
            for _ in range(depth):
                if not cur:
                    break
                chain.append(cur)
                cur = cur.reply_to_message
            # Sort chronologically to preserve call/response order
            chain = sorted(chain, key=lambda m: m.timestamp)

            # A reply chain selects genuine conversation branches, but tool calls
            # from one LLM response are stored as sibling branches. Rebuild the
            # execution belonging to each selected top-level request from the
            # Request/ToolCall graph so later user turns retain every sibling.
            selected_roots = {}
            for chain_message in chain:
                if chain_message.is_outgoing is False and chain_message.media_type not in {
                    'tool_call', 'tool_response',
                }:
                    root_request = chain_message.request_set.filter(
                        parent_request__isnull=True,
                    ).order_by('created_at').first()
                    if root_request:
                        selected_roots[chain_message.pk] = root_request

            active_root_message_id = None
            if self.response_to_tool_call_id:
                active_request = (
                    self.response_to_tool_call.request.initial_request
                    or self.response_to_tool_call.request
                )
                active_root_message_id = active_request.message_id
            else:
                endpoint_request = self.request_set.filter(
                    parent_request__isnull=True,
                ).order_by('created_at').first()
                if endpoint_request:
                    active_root_message_id = endpoint_request.message_id

            def request_execution(request, include_late_interrupted=False):
                projected = []
                children = list(type(request).objects.filter(
                    parent_request_id=request.pk,
                ).select_related('message').order_by('created_at'))
                children_by_message = {child.message_id: child for child in children}
                followed_children = set()
                calls = list(
                    request.tool_calls.model.objects.filter(request_id=request.pk)
                    .select_related('tool_call_message')
                    .prefetch_related('response_messages').order_by('created_at')
                )
                for call in calls:
                    responses = [
                        response for response in call.response_messages.all()
                        if response.timestamp <= self.timestamp
                    ]
                    if responses:
                        # The first response participates in the original batch.
                        projected.extend([call.tool_call_message, responses[0]])
                    elif call.status == 'INTERRUPTED' and (
                        call.created_at <= self.timestamp or include_late_interrupted
                    ):
                        projected.append(call.tool_call_message)
                        projected.append({
                            'role': 'tool',
                            'tool_call_id': call.call_id,
                            'content': '{"status": "ERROR", "error": "Interrupted by a newer user message."}',
                        })
                    else:
                        continue

                    for response_index, response in enumerate(responses):
                        if response_index:
                            # ACTIVE tools may answer repeatedly. Repeat the call
                            # declaration so each recurring event remains a valid pair.
                            projected.extend([call.tool_call_message, response])
                        child = children_by_message.get(response.pk)
                        if child:
                            followed_children.add(child.pk)
                            projected.extend(request_execution(child, include_late_interrupted))

                # A batch continuation is attached to its final sibling response;
                # recurse after the complete batch if it was not visited above.
                for child in children:
                    if child.pk not in followed_children and child.message.timestamp <= self.timestamp:
                        projected.extend(request_execution(child, include_late_interrupted))
                return projected

            if selected_roots:
                rebuilt_chain = []
                for chain_message in chain:
                    if chain_message.media_type in {'tool_call', 'tool_response'}:
                        continue
                    rebuilt_chain.append(chain_message)
                    root_request = selected_roots.get(chain_message.pk)
                    if root_request:
                        rebuilt_chain.extend(request_execution(
                            root_request,
                            include_late_interrupted=(
                                chain_message.pk != active_root_message_id
                            ),
                        ))
                chain = rebuilt_chain

            # Handle user interruption for tool response messages in thread mode
            if self.media_type == "tool_response" and not selected_roots:
                # Find any user message that came chronologically after any tool call in our chain
                # AND that replies to one of the messages in our chain
                tool_call_timestamps = [m.timestamp for m in chain if m.media_type == "tool_call"]
                if tool_call_timestamps:
                    latest_tool_call_time = max(tool_call_timestamps)
                    chain_message_ids = [m.id for m in chain]
                    
                    # Look for user messages after (tool call time - grace period), before this tool response,
                    # that reply to any message in our chain
                    from django.utils import timezone
                    grace_start = latest_tool_call_time - timezone.timedelta(minutes=5)
                    user_interrupt = self.chat.messages.filter(
                        is_outgoing=False,
                        timestamp__gt=grace_start,
                        timestamp__lt=self.timestamp,
                        reply_to_message_id__in=chain_message_ids
                    ).exclude(
                        media_type__in=['tool_call', 'tool_response']
                    ).order_by('-timestamp').first()

                    # Fallback: any user message in that window, even without reply_to
                    if not user_interrupt:
                        user_interrupt = self.chat.messages.filter(
                            is_outgoing=False,
                            timestamp__gt=grace_start,
                            timestamp__lt=self.timestamp
                        ).exclude(
                            media_type__in=['tool_call', 'tool_response']
                        ).order_by('-timestamp').first()
                    
                    if user_interrupt:
                        if user_interrupt not in chain:
                            chain.append(user_interrupt)
                        chain = sorted(chain, key=lambda m: m.timestamp)

            # Parallel tool calls are stored as sibling reply branches. A batch
            # continuation is attached to the final response, so its ordinary
            # ancestry contains only that one sibling. Project every resolved
            # sibling into the continuation as adjacent call/response pairs.
            if self.media_type == "tool_response" and not selected_roots:
                continuation_request = self.request_set.filter(
                    parent_request__isnull=False,
                    metadata__created_from="tool_response",
                    metadata__batch_continuation=True,
                ).select_related("parent_request").first()
                if continuation_request:
                    batch_calls = list(
                        continuation_request.parent_request.tool_calls
                        .select_related("tool_call_message")
                        .prefetch_related("response_messages")
                        .order_by("created_at")
                    )
                    if len(batch_calls) > 1:
                        batch_messages = []
                        complete_batch = True
                        for batch_call in batch_calls:
                            response = next((
                                item for item in batch_call.response_messages.all()
                                if item.media_type == "tool_response"
                                and item.timestamp <= self.timestamp
                            ), None)
                            if response is None:
                                complete_batch = False
                                break
                            batch_messages.extend([batch_call.tool_call_message, response])
                        if complete_batch:
                            batch_ids = {item.pk for item in batch_messages}
                            chain = [item for item in chain if item.pk not in batch_ids]
                            chain.extend(batch_messages)

            # Ensure tool_call and tool_response are adjacent
            if self.media_type == "tool_response":
                try:
                    call_id = self.raw.get('tool_response', {}).get('call_id')
                    if call_id:
                        tc_idx = next((i for i, m in enumerate(chain)
                                       if m.media_type == "tool_call"
                                       and m.raw.get('tool_call', {}).get('id') == call_id), None)
                        tr_idx = next((i for i, m in enumerate(chain)
                                       if m.media_type == "tool_response"
                                       and m.raw.get('tool_response', {}).get('call_id') == call_id), None)
                        if tc_idx is not None and tr_idx is not None and tr_idx != tc_idx + 1:
                            # Move tool_response directly after tool_call
                            tr = chain.pop(tr_idx)
                            chain.insert(tc_idx + 1, tr)
                except Exception:
                    pass

            for m in chain:
                messages.append(m if isinstance(m, dict) else msg_to_dict(m))
        else:
            raise ValueError(f"Unknown mode: {mode}")
        if system_instruction:
            messages = [{"role": "system", "content": system_instruction}] + messages
        return messages
    
    def log_tool_interaction(self, tool_call=None, tool_response=None, user=None):
        """
        Save tool call and/or response as replies to this message
        
        Args:
            tool_call: Dict with tool call data (e.g., {"name": "search", "arguments": {...}, "id": "call_123"})
            tool_response: Dict with response data (e.g., {"call_id": "call_123", "result": {...}})
            user: User making the call (optional)
        
        Returns:
            Tuple of (tool_call_message, tool_response_message) or single message if only one provided
        """
        from unicom.services.llm.tool_calls import save_tool_call, save_tool_response
        
        if not tool_call and not tool_response:
            raise ValueError("At least one of tool_call or tool_response must be provided")
        
        messages = []
        
        if tool_call:
            tool_name = tool_call.get('name')
            tool_args = tool_call.get('arguments', {})
            call_id = tool_call.get('id')
            
            if not tool_name:
                raise ValueError("tool_call must include 'name' field")
            
            tool_call_msg = save_tool_call(
                self.chat, tool_name, tool_args, user, call_id, reply_to_message=self
            )
            messages.append(tool_call_msg)
        
        if tool_response:
            call_id = tool_response.get('call_id')
            result = tool_response.get('result')
            
            if not call_id:
                raise ValueError("tool_response must include 'call_id' field")
            
            # If we have both tool_call and tool_response, get tool_name from call
            # Otherwise, we need to find the original tool call to get the name
            if tool_call:
                tool_name = tool_call.get('name')
            else:
                # Look up the original tool call message to get the tool name
                try:
                    original_call = self.chat.messages.filter(
                        media_type='tool_call',
                        raw__tool_call__id=call_id
                    ).first()
                    if original_call:
                        tool_name = original_call.raw['tool_call']['name']
                    else:
                        raise ValueError(f"Could not find original tool call with id: {call_id}")
                except Exception:
                    raise ValueError(f"Could not find original tool call with id: {call_id}")
            
            # If we saved a tool_call above, reply to that, otherwise reply to self
            reply_to = messages[0] if messages else self
            
            tool_response_msg = save_tool_response(
                self.chat, call_id, result, tool_name, user, reply_to_message=reply_to
            )
            messages.append(tool_response_msg)
        
        return tuple(messages) if len(messages) > 1 else messages[0]

    def reply_using_llm(
        self,
        model: str,
        depth=129,
        mode="chat",
        system_instruction=None,
        multimodal=True,
        user=None,
        voice="alloy",
        api_mode="chat_completions",
        openai_client=None,
        stream=False,
        stream_event_sink=None,
        **kwargs,
    ):
        """
        Wrapper: Calls as_llm_chat, OpenAI ChatCompletion API, and reply_with.
        - model: OpenAI model string
        - depth, mode, system_instruction, multimodal: passed to as_llm_chat
        - user: Django user for reply_with
        - voice: voice name for audio response (default 'alloy')
        - kwargs: extra params for OpenAI API
        Returns: The Message object created by reply_with
        """
        if api_mode not in {"chat_completions", "responses"}:
            raise ValueError("api_mode must be 'chat_completions' or 'responses'")

        # Prepare messages for LLM
        messages = self.as_llm_chat(depth=depth, mode=mode, system_instruction=system_instruction, multimodal=multimodal)
        client = openai_client or get_openai_client()

        if api_mode == "responses":
            from unicom.services.llm.responses import create_response

            result = create_response(
                client=client,
                model=model,
                messages=messages,
                stream=stream,
                event_sink=stream_event_sink,
                **kwargs,
            )
            if result.tool_calls:
                raise ValueError(
                    "Message.reply_using_llm() does not execute tools; use "
                    "Bot.reply_using_llm() for Responses function calls."
                )
            reply_dict = {'html': result.text} if self.platform == 'Email' else {
                'type': 'text',
                'text': result.text,
            }
            return self.reply_with(reply_dict)

        # Determine if we need to request audio response
        openai_kwargs = dict(kwargs)
        if multimodal and self.media_type == "audio":
            openai_kwargs["modalities"] = ["text", "audio"]
            openai_kwargs["audio"] = {"voice": voice, "format": "opus"}
        # Call OpenAI ChatCompletion API
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            **openai_kwargs
        )
        # Get the LLM's reply (assume first choice)
        llm_msg = response.choices[0].message
        # Prepare reply dict
        reply_dict = None
        # If the LLM returns a list of content blocks (OpenAI-style)
        content = getattr(llm_msg, 'content', None)
        if isinstance(content, list):
            # Check for audio or image blocks
            for block in content:
                if block.get("type") == "input_audio":
                    audio_data = block["input_audio"]["data"]
                    ext = block["input_audio"].get("format", "wav")
                    audio_file_name = f"media/{uuid.uuid4()}.{ext}"
                    with open(audio_file_name, "wb") as f:
                        f.write(base64.b64decode(audio_data))
                    reply_dict = {
                        "type": "audio",
                        "file_path": audio_file_name,
                        "text": ""
                    }
                elif block.get("type") == "image_url":
                    url = block["image_url"]["url"]
                    m = re.match(r"data:(.*?);base64,(.*)", url)
                    if m:
                        mime, b64data = m.groups()
                        ext = mime.split("/")[-1]
                        image_file_name = f"media/{uuid.uuid4()}.{ext}"
                        with open(image_file_name, "wb") as f:
                            f.write(base64.b64decode(b64data))
                        reply_dict = {
                            "type": "image",
                            "file_path": image_file_name,
                            "text": ""
                        }
                elif block.get("type") == "text":
                    if reply_dict is None:
                        reply_dict = {"type": "text", "text": block["text"]}
                    else:
                        reply_dict["text"] = block["text"]
        # Handle OpenAI SDK audio id structure with base64 data and transcript
        elif hasattr(llm_msg, 'audio') and llm_msg.audio and hasattr(llm_msg.audio, 'data'):
            audio_data = llm_msg.audio.data
            transcript = getattr(llm_msg.audio, 'transcript', '')
            audio_id = getattr(llm_msg.audio, 'id', None)
            audio_file_name = f"media/{uuid.uuid4()}.ogg"
            wav_bytes = base64.b64decode(audio_data)
            with open(audio_file_name, "wb") as f:
                f.write(wav_bytes)
            reply_dict = {"type": "audio", "file_path": audio_file_name, "audio_id": audio_id}
            if transcript:
                reply_dict["text"] = transcript
        elif self.platform == 'Email':
            reply_dict = {'html': llm_msg.content}
        else:
            reply_dict = {'type': 'text', 'text': llm_msg.content}
        # Reply using reply_with
        return self.reply_with(reply_dict)

    class Meta:
        ordering = ['-timestamp']
        constraints = [
            models.UniqueConstraint(
                fields=['channel', 'imap_uid'],
                name='unicom_message_channel_imap_uid_unique',
            ),
        ]

    def __str__(self) -> str:
        return f"{self.platform}:{self.chat.name}->{self.sender_name}: {self.text}"


class EmailInlineImage(models.Model):
    file = DedupFileField(upload_to='email_inline_images/', hash_field='hash')
    email_message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='inline_images', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    content_id = models.CharField(max_length=255, blank=True, null=True, help_text='Content-ID for cid: references in HTML')
    hash = models.CharField(max_length=64, blank=True, null=True, db_index=True, help_text='SHA256 hash of file for deduplication')

    def delete(self, *args, **kwargs):
        only_delete_file_if_unused(self, 'file', 'hash')
        super().delete(*args, **kwargs)

    def get_short_id(self):
        # Use base62 encoding of PK for short URLs
        import string
        chars = string.digits + string.ascii_letters
        n = self.pk
        s = ''
        if n == 0:
            return chars[0]
        while n > 0:
            n, r = divmod(n, 62)
            s = chars[r] + s
        return s
