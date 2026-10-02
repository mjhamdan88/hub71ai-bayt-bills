from django.contrib import admin
from django.utils.html import format_html
from django_ace import AceWidget

# Import related models for unfiltered M2M querysets
from ..models import (
    Request,
    RequestCategory,
    Channel,
    Member,
    MemberGroup,
)

class RequestCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'sequence', 'is_active', 'is_public')
    list_filter = ('is_active', 'is_public', 'parent')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('allowed_channels', 'authorized_members', 'authorized_groups')
    
    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'processing_function':
            kwargs['widget'] = AceWidget(
                mode='python',
                theme='twilight',
                width="100%",
                height="300px"
            )
        return super().formfield_for_dbfield(db_field, **kwargs)
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Prevent a category from being its own parent
        if obj:
            form.base_fields['parent'].queryset = RequestCategory.objects.exclude(pk=obj.pk)
        
        # Ensure all choices are visible in M2M fields regardless of Channel/Member admin permissions
        if 'allowed_channels' in form.base_fields:
            form.base_fields['allowed_channels'].queryset = Channel.objects.all()
        if 'authorized_members' in form.base_fields:
            form.base_fields['authorized_members'].queryset = Member.objects.all()
        if 'authorized_groups' in form.base_fields:
            form.base_fields['authorized_groups'].queryset = MemberGroup.objects.all()
        
        # Set template code as initial value for new categories
        if not obj and 'processing_function' in form.base_fields:
            form.base_fields['processing_function'].initial = obj.get_template_code() if obj else RequestCategory().get_template_code()
        
        return form

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """Ensure all related objects are visible regardless of the requesting user's permissions.

        This allows any user who can add/change a RequestCategory to freely select values
        for the allowed_channels, authorized_members and authorized_groups fields, even
        if they lack explicit view permissions on those related models.
        """
        if db_field.name == 'allowed_channels':
            kwargs['queryset'] = Channel.objects.all()
        elif db_field.name == 'authorized_members':
            kwargs['queryset'] = Member.objects.all()
        elif db_field.name == 'authorized_groups':
            kwargs['queryset'] = MemberGroup.objects.all()

        return super().formfield_for_manytomany(db_field, request, **kwargs)

    class Media:
        css = {
            'all': ('admin/css/forms.css',)
        }
        js = ('admin/js/core.js',)

class RequestAdmin(admin.ModelAdmin):
    list_display = (
        '__str__', 'status', 'retry_count', 'failure_kind',
        'member_link', 'category', 'channel', 'created_at',
    )
    list_display_links = ('__str__',)
    list_filter = (
        'status',
        'failure_kind',
        'channel',
        'category',
        ('member', admin.RelatedOnlyFieldListFilter),
        ('created_at', admin.DateFieldListFilter),
    )
    search_fields = (
        'display_text',
        'message__text',
        'email',
        'phone',
        'member__name',
        'member__email',
        'member__phone',
        'metadata',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
        'pending_at',
        'identifying_at',
        'categorizing_at',
        'queued_at',
        'processing_at',
        'completed_at',
        'failed_at',
        'last_attempt_at',
        'last_retried_at',
        'next_retry_at',
        'retry_exhausted_at',
        'retry_count',
        'failure_kind',
        'error',
    )
    raw_id_fields = ('message', 'account', 'member', 'category')
    date_hierarchy = 'created_at'

    def member_link(self, obj):
        if obj.member:
            url = f"/admin/unicom/member/{obj.member.id}/change/"
            return format_html('<a href="{}">{}</a>', url, obj.member.name)
        return "-"
    member_link.short_description = "Member"

    fieldsets = (
        ('Message', {
            'fields': ('message', 'display_text')
        }),
        ('Basic Information', {
            'fields': ('status', 'error', 'account', 'channel', 'member')
        }),
        ('Automatic retries', {
            'fields': (
                'retry_count', 'failure_kind', 'last_attempt_at',
                'last_retried_at', 'next_retry_at', 'retry_exhausted_at',
            ),
        }),
        ('Contact Information', {
            'fields': ('email', 'phone')
        }),
        ('Categorization', {
            'fields': ('category',)
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at',
                'pending_at',
                'identifying_at',
                'categorizing_at',
                'queued_at',
                'processing_at',
                'completed_at',
                'failed_at',
            ),
            'classes': ('collapse',)
        }),
    )
