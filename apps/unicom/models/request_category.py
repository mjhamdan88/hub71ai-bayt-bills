from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
import os


class RequestCategory(models.Model):
    """
    Categories for requests with processing functions and hierarchical structure.
    """
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='subcategories'
    )
    sequence = models.IntegerField(
        help_text="Order in which category processing functions are executed"
    )
    processing_function = models.TextField(
        help_text=(
            "Python function that determines if a request matches this category.\n"
            "Must be named 'process' and take a single 'request' argument.\n"
            "Must return True if the request matches, False otherwise.\n"
            "Example: def process(request) -> bool:\n"
            "    return 'help' in request.message.text.lower()"
        ),
        null=True,
        blank=True
    )
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(
        default=False,
        help_text="If True, all members have access. If False, only authorized members or groups."
    )
    allowed_channels = models.ManyToManyField(
        'unicom.Channel',
        blank=True,
        related_name='available_categories',
        help_text="Channels where this category can be used. If empty, allowed in all channels."
    )
    authorized_members = models.ManyToManyField(
        'unicom.Member',
        blank=True,
        related_name='directly_accessible_categories',
        help_text="Individual members with explicit access to this category"
    )
    authorized_groups = models.ManyToManyField(
        'unicom.MemberGroup',
        blank=True,
        related_name='accessible_categories',
        help_text="Member groups with access to this category"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['sequence', 'parent']]
        ordering = ['parent_id', 'sequence']
        verbose_name_plural = "Request categories"
        indexes = [
            models.Index(fields=['is_public', 'is_active'], name='category_access_idx')
        ]

    def __str__(self):
        return f"{self.name} ({self.sequence})"

    def clean(self):
        # Ensure sequence is unique within the same parent level
        if RequestCategory.objects.filter(
            parent=self.parent,
            sequence=self.sequence
        ).exclude(id=self.id).exists():
            raise ValidationError(
                'Sequence must be unique for categories with the same parent'
            )

    @property
    def template_path(self):
        """Get the path to the category processor template file."""
        return os.path.join(settings.BASE_DIR, 'unicom', 'templates', 'code_templates', 'category_processor.py')

    def get_template_code(self):
        """Get the template code for the category processor."""
        try:
            with open(self.template_path, 'r') as f:
                return f.read()
        except Exception:
            return "def process(request) -> bool:\n    return False"

    def process_request(self, request):
        """
        Execute the category's processing function on a request.
        Returns True if the category matches the request, False otherwise.
        """
        try:
            if not self.processing_function:
                return False

            # Create a function object from the processing_function code
            local_vars = {'request': request}
            exec(self.processing_function, {}, local_vars)
            
            # Get the process function and call it
            process_func = local_vars.get('process')
            if not process_func:
                return False
                
            return bool(process_func(request))
            
        except Exception as e:
            print(f"Error processing category {self.name}: {e}")
            return False 