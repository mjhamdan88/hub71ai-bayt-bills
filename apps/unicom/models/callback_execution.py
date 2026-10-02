from django.db import models


class CallbackExecution(models.Model):
    """
    Stores callback button data and metadata.
    Links button clicks to the original message and intended account.
    Optionally links to a ToolCall if the button was created from a tool response.
    """
    original_message = models.ForeignKey('unicom.Message', on_delete=models.CASCADE,
                                         related_name='button_callbacks',
                                         help_text="The message containing the buttons")
    callback_data = models.JSONField(help_text="Button callback data (any JSON-serializable type)")
    intended_account = models.ForeignKey('unicom.Account', on_delete=models.CASCADE,
                                         help_text="The account this button is intended for")
    tool_call = models.ForeignKey('unicom.ToolCall', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='button_callbacks',
                                  help_text="Optional: The ToolCall that created this button (if from a tool)")
    expires_at = models.DateTimeField(null=True, blank=True,
                                      help_text="Optional expiration time for this callback")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'unicom_callback_execution'
        verbose_name = 'Callback Execution'
        verbose_name_plural = 'Callback Executions'

    def is_expired(self):
        """Check if this callback has expired"""
        if not self.expires_at:
            return False
        from django.utils import timezone
        return timezone.now() > self.expires_at

    def __str__(self):
        data_preview = str(self.callback_data)[:50]
        return f"Callback {self.id}: {data_preview} for {self.intended_account.name}"