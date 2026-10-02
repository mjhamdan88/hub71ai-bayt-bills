from __future__ import annotations
from typing import TYPE_CHECKING
from django.db import models
from .constants import channels
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

if TYPE_CHECKING:
    from unicom.models import Message


class Chat(models.Model):
    id = models.CharField(max_length=500, primary_key=True)
    channel = models.ForeignKey('unicom.Channel', on_delete=models.CASCADE)
    platform = models.CharField(max_length=100, choices=channels)
    is_private = models.BooleanField(default=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    is_archived = models.BooleanField(default=False, help_text="Archived chats are hidden from the main list view")
    metadata = models.JSONField(default=dict, blank=True, help_text="Custom properties for filtering (e.g., project_id, department_id)")
    
    # Message cache fields
    first_message = models.ForeignKey('unicom.Message', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    first_outgoing_message = models.ForeignKey('unicom.Message', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    first_incoming_message = models.ForeignKey('unicom.Message', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    last_message = models.ForeignKey('unicom.Message', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    last_outgoing_message = models.ForeignKey('unicom.Message', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    last_incoming_message = models.ForeignKey('unicom.Message', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    # accounts = models.ManyToManyField('unicom.Account', related_name="chats")

    def send_message(self, msg_dict: dict, user:User=None) -> Message:
        """
        Send a message to this chat using the channel's platform.
        The msg_dict must include at least the text or media to send.
        
        If reply_to_message_id is provided in msg_dict, it will reply to that specific message.
        For email channels without a specific reply_to_message_id, this will find the last incoming 
        message and reply to it, ensuring proper email threading.
        """
        if not self.channel.active:
            raise ValueError("Channel must be active to send messages.")
        
        try:
            # If replying to a specific message
            if reply_to_id := msg_dict.pop('reply_to_message_id', None):
                from unicom.models import Message
                reply_to_message = Message.objects.get(id=reply_to_id, chat=self)
                return reply_to_message.reply_with(msg_dict)
            
            # Default behavior for email - reply to last incoming message
            elif self.platform == 'Email':
                last_incoming = self.messages.filter(
                    is_outgoing=False
                ).order_by('-timestamp').first()
                
                if not last_incoming:
                    raise ValidationError("No incoming messages found in this email chat to reply to")
                
                return last_incoming.reply_with(msg_dict)
            
            # For other platforms without specific reply
            else:
                from unicom.services.crossplatform.send_message import send_message
                return send_message(self.channel, {**msg_dict, "chat_id": self.id}, user)
                
        except Exception as e:
            raise ValueError(f"Failed to send message: {str(e)}")

    def log_tool_interaction(self, tool_call=None, tool_response=None, reply_to=None, user=None):
        """
        Save tool call and/or response in this chat
        
        Args:
            tool_call: Dict with tool call data (e.g., {"name": "search", "arguments": {...}, "id": "call_123"})
            tool_response: Dict with response data (e.g., {"call_id": "call_123", "result": {...}})
            reply_to: Message to reply to (optional)
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
                self, tool_name, tool_args, user, call_id, reply_to_message=reply_to
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
                    original_call = self.messages.filter(
                        media_type='tool_call',
                        raw__tool_call__id=call_id
                    ).first()
                    if original_call:
                        tool_name = original_call.raw['tool_call']['name']
                    else:
                        raise ValueError(f"Could not find original tool call with id: {call_id}")
                except Exception:
                    raise ValueError(f"Could not find original tool call with id: {call_id}")
            
            # If we saved a tool_call above, reply to that, otherwise use provided reply_to
            reply_to_msg = messages[0] if messages else reply_to
            
            tool_response_msg = save_tool_response(
                self, call_id, result, tool_name, user, reply_to_message=reply_to_msg
            )
            messages.append(tool_response_msg)
        
        return tuple(messages) if len(messages) > 1 else messages[0]

    def __str__(self) -> str:
        return f"{self.platform}:{self.id} ({self.name})"