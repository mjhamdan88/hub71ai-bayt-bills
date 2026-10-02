from django.db import models


class MemberGroup(models.Model):
    """
    Groups for organizing members and managing category access permissions.
    """
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(
        'unicom.Member',
        related_name='groups',
        blank=True,
        help_text="Members belonging to this group"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['name'], name='membergroup_name_idx')
        ]

    def __str__(self):
        return self.name 