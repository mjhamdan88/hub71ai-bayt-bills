from django.db import models
from .constants import channels


class Account(models.Model):
    id = models.CharField(max_length=500, primary_key=True)
    channel = models.ForeignKey('unicom.Channel', on_delete=models.CASCADE)
    platform = models.CharField(max_length=100, choices=channels)
    is_bot = models.BooleanField(default=False)
    name = models.CharField(max_length=100, null=True, blank=True)
    blocked = models.BooleanField(default=False, help_text="Whether this account is blocked from sending messages")
    member = models.ForeignKey(
        'unicom.Member', on_delete=models.SET_NULL, null=True, blank=True, related_name='accounts',
        help_text="Associated CRM member if matched"
    )
    default_category = models.ForeignKey(
        'unicom.RequestCategory',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Default category for messages from this account"
    )
    raw = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f"{self.platform}:{self.id} ({self.name})"
