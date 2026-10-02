from django.db import models


class Member(models.Model):
    """
    CRM model for customers/users with specific access levels and temporary tokens.
    """
    name = models.CharField(max_length=255)
    email = models.EmailField(
        blank=True,
        null=True,
        db_index=True,
        help_text="Indexed field for member identification"
    )
    phone = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        db_index=True,
        help_text="Indexed field for member identification"
    )
    misc_tokens = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        help_text="Secure storage for temporary authentication/access tokens"
    )
    allowed_categories = models.ManyToManyField(
        'unicom.RequestCategory',
        blank=True,
        related_name='members_with_access',
        help_text="Categories this member has explicit access to"
    )
    user = models.OneToOneField(
        'auth.User',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='member'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            # Compound index for when searching both fields
            models.Index(fields=['email', 'phone'], name='member_contact_idx'),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Override save to automatically add new members to 'All Members' group."""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            # Add to 'All Members' group if it exists
            from .member_group import MemberGroup
            try:
                all_members_group = MemberGroup.objects.get(name='All Members')
                all_members_group.members.add(self)
            except MemberGroup.DoesNotExist:
                # Group doesn't exist yet, skip (e.g., during initial migration)
                pass 