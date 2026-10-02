from django.db import models


class EmailBackfillJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    channel = models.ForeignKey(
        "unicom.Channel", on_delete=models.CASCADE, related_name="email_backfill_jobs"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    total_messages = models.PositiveIntegerField(default=0)
    processed_messages = models.PositiveIntegerField(default=0)
    imported_messages = models.PositiveIntegerField(default=0)
    skipped_messages = models.PositiveIntegerField(default=0)
    failed_messages = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    @property
    def progress_percent(self):
        if not self.total_messages:
            return 100 if self.status == self.Status.COMPLETED else 0
        return min(100, round(self.processed_messages * 100 / self.total_messages))
