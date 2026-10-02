from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
import uuid


def _request_was_superseded(request):
    initial_request = request.initial_request or request
    return initial_request.message.chat.messages.filter(
        is_outgoing=False,
        timestamp__gt=initial_request.message.timestamp,
    ).exclude(media_type__in=['tool_call', 'tool_response']).exists()


class ToolCall(models.Model):
    """Task queue model for tracking tool calls awaiting responses"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('ERROR', 'Error'),
        ('INTERRUPTED', 'Interrupted'),
        ('ACTIVE', 'Active'),  # For periodic/ongoing tool calls
    ]
    RESULT_STATUS_CHOICES = [
        ('SUCCESS', 'Success'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    call_id = models.CharField(max_length=100, unique=True, db_index=True)
    tool_name = models.CharField(max_length=100, db_index=True)
    arguments = models.JSONField()
    progress_updates_for_user = models.TextField(
        null=True,
        blank=True,
        help_text="LLM-provided one-line description of what/why this call is doing"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    result_status = models.CharField(
        max_length=20,
        choices=RESULT_STATUS_CHOICES,
        default='SUCCESS',
        help_text="Outcome reported by the tool (independent of processing status)"
    )
    error = models.TextField(
        null=True,
        blank=True,
        help_text="Error message if processing fails"
    )
    
    # Reference to the request that created this tool call
    request = models.ForeignKey('unicom.Request', on_delete=models.CASCADE, related_name='tool_calls')
    
    # Reference to the tool call message (for proper reply chain)
    tool_call_message = models.ForeignKey(
        'unicom.Message', 
        on_delete=models.CASCADE, 
        related_name='tool_call_record',
        help_text="The tool_call message that this ToolCall object represents"
    )
    
    # Reference to the initial user message that triggered this tool call
    initial_user_message = models.ForeignKey(
        'unicom.Message',
        on_delete=models.CASCADE,
        related_name='triggered_tool_calls',
        help_text="The original user message that this tool call is responding to"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['tool_name', 'status']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.tool_name}:{self.call_id} ({self.status})"
    
    def clean(self):
        """Validate that tool_call_message is actually a tool call message"""
        if self.tool_call_message and self.tool_call_message.media_type != 'tool_call':
            raise ValidationError("tool_call_message must have media_type='tool_call'")
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def start_processing(self):
        """Mark tool call as in progress"""
        self.status = 'IN_PROGRESS'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at'])
    
    def mark_active(self):
        """Mark tool call as active for periodic responses"""
        self.status = 'ACTIVE'
        self.save(update_fields=['status'])
    
    def mark_error(self, error_message=None):
        """Mark tool call as failed"""
        self.status = 'ERROR'
        self.result_status = 'ERROR'
        self.completed_at = timezone.now()
        if error_message:
            self.error = error_message
        self.save(update_fields=['status', 'completed_at', 'error', 'result_status'])
    
    def interrupt(self):
        """Terminalize this call without creating an LLM continuation."""
        with transaction.atomic():
            tool_call = type(self).objects.select_for_update().get(pk=self.pk)
            if tool_call.status in {'COMPLETED', 'ERROR', 'INTERRUPTED'}:
                return tool_call.response_messages.order_by('timestamp').first()
            response = tool_call.tool_call_message.log_tool_interaction(
                tool_response={
                    "call_id": tool_call.call_id,
                    "result": {
                        "status": "ERROR",
                        "error": "Interrupted by a newer user message.",
                    },
                    "status": "ERROR",
                }
            )
            response.response_to_tool_call = tool_call
            response.save(update_fields=['response_to_tool_call'])
            tool_call.status = 'INTERRUPTED'
            tool_call.result_status = 'ERROR'
            tool_call.error = 'Interrupted by a newer user message.'
            tool_call.completed_at = timezone.now()
            tool_call.save(update_fields=[
                'status', 'result_status', 'error', 'completed_at',
            ])
            self.status = tool_call.status
            self.result_status = tool_call.result_status
            self.error = tool_call.error
            self.completed_at = tool_call.completed_at
            return response

    @classmethod
    def interrupt_unresolved(cls, queryset):
        """Interrupt each unresolved call, returning the terminal responses."""
        responses = []
        for call in queryset.filter(
            status__in=['PENDING', 'IN_PROGRESS', 'ACTIVE'],
        ).order_by('created_at'):
            response = call.interrupt()
            if response is not None:
                responses.append(response)
        return responses

    def respond(self, result, status: str = 'SUCCESS'):
        """
        Submit response to this tool call.
        
        Args:
            result: The result from the tool execution (any JSON-serializable object)
            status: Optional result status to record (SUCCESS/WARNING/ERROR)
        
        Returns:
            Tuple of (tool_response_message, child_request_or_None)
            
        Behavior:
        - For PENDING status: Marks as COMPLETED, creates child request if final
        - For IN_PROGRESS status: Marks as COMPLETED, creates child request if final
        - For ACTIVE status: Keeps the call active; its first response joins the
          batch barrier and later responses may create recurring continuations
        - For other statuses: Raises ValueError
        """
        # Normalize and validate result status
        normalized_status = (status or 'SUCCESS').upper()
        valid_statuses = {choice[0] for choice in self.RESULT_STATUS_CHOICES}
        if normalized_status not in valid_statuses:
            normalized_status = 'SUCCESS'

        def format_payload(res, stat):
            if isinstance(res, dict):
                merged = dict(res)
                merged["status"] = stat
                return merged
            return {"status": stat, "result": res}

        payload = format_payload(result, normalized_status)

        with transaction.atomic():
            # Serialize every response in a batch through its parent request. This
            # makes the "all siblings resolved" check and continuation claim atomic.
            request = self.request.__class__.objects.select_for_update().get(pk=self.request_id)
            tool_call = type(self).objects.select_for_update().get(pk=self.pk)
            if tool_call.status == 'INTERRUPTED':
                return None, None
            if _request_was_superseded(request):
                type(self).interrupt_unresolved(request.tool_calls.all())
                return None, None
            if tool_call.status not in ['PENDING', 'IN_PROGRESS', 'ACTIVE']:
                raise ValueError(f"Cannot respond to tool call with status: {tool_call.status}")

            had_previous_response = tool_call.response_messages.exists()
            tool_response_msg = tool_call.tool_call_message.log_tool_interaction(
                tool_response={
                    "call_id": tool_call.call_id,
                    "result": payload,
                    "status": normalized_status
                }
            )
            tool_response_msg.response_to_tool_call = tool_call
            tool_response_msg.save(update_fields=['response_to_tool_call'])

            # Only mark as completed if not ACTIVE (ACTIVE stays active for reusable buttons)
            if tool_call.status != 'ACTIVE':
                tool_call.status = 'COMPLETED'
                tool_call.completed_at = timezone.now()
                tool_call.result_status = normalized_status
                tool_call.save(update_fields=['status', 'completed_at', 'result_status'])
            else:
                # Keep ACTIVE but still record the latest result_status
                tool_call.result_status = normalized_status
                tool_call.save(update_fields=['result_status'])

            siblings = request.tool_calls.all()
            all_siblings_responded = not siblings.filter(response_messages__isnull=True).exists()
            initial_continuation_exists = request.child_requests.filter(
                metadata__created_from='tool_response',
            ).exists()
            recurring_followup = tool_call.status == 'ACTIVE' and had_previous_response

            if all_siblings_responded and (recurring_followup or not initial_continuation_exists):
                # This is the final response - create child request
                # Use initial_request to get the root request for field propagation
                initial_req = request.initial_request or request
                
                child_request = self.request.__class__.objects.create(
                    message=tool_response_msg,
                    # Propagate fields from initial request
                    account=initial_req.account,
                    channel=initial_req.channel,
                    member=initial_req.member,
                    email=initial_req.email,
                    phone=initial_req.phone,
                    category=initial_req.category,  # Propagate category from initial request
                    # Set hierarchy fields
                    parent_request=request,
                    initial_request=initial_req,
                    display_text=f"Tool response: {str(result)[:100]}...",
                    status='PENDING',
                    metadata={
                        'created_from': 'tool_response',
                        'batch_continuation': not recurring_followup,
                        'parent_request_id': str(request.id),
                        'initial_request_id': str(initial_req.id),
                        'final_tool_call_id': tool_call.call_id,
                        'tool_name': tool_call.tool_name,
                    }
                )
                
                # Process child request through normal pipeline
                child_request.identify_member()
                child_request.categorize()
                
                return tool_response_msg, child_request
        
        return tool_response_msg, None
