from django.contrib import admin
from .models import Bot, Tool, EncryptedCredential, CredentialFieldDefinition, CredentialSetupSession
from django import forms
from django_ace import AceWidget
from reversion.admin import VersionAdmin
from django.utils.html import format_html
from django.urls import reverse

# Register your models here.

class BotAdminForm(forms.ModelForm):
    class Meta:
        model = Bot
        fields = '__all__'
        widgets = {
            'code': AceWidget(mode='python', theme='twilight', width='600px', height='300px'),
        }

class BotAdmin(VersionAdmin):
    form = BotAdminForm

    def get_changeform_initial_data(self, request):
        return {'code': Bot.get_default_code()}

class ToolAdminForm(forms.ModelForm):
    class Meta:
        model = Tool
        fields = '__all__'
        widgets = {
            'code': AceWidget(mode='python', theme='twilight', width='600px', height='300px'),
        }

class ToolAdmin(VersionAdmin):
    form = ToolAdminForm

    def get_changeform_initial_data(self, request):
        return {'code': Tool.get_default_code()}

class EncryptedCredentialForm(forms.ModelForm):
    value_input = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        help_text='Enter the value to be stored securely'
    )

    class Meta:
        model = EncryptedCredential
        fields = ('account', 'key', 'value_input')

class EncryptedCredentialAdmin(VersionAdmin):
    form = EncryptedCredentialForm
    list_display = ('account', 'key', 'created_at', 'updated_at')
    list_filter = ('account',)
    search_fields = ('account__name', 'key')
    readonly_fields = ('created_at', 'updated_at')
    
    def save_model(self, request, obj, form, change):
        if not change:  # Only for new objects
            value = form.cleaned_data.get('value_input')
            if value:
                obj._value = value
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        # Prevent editing existing credentials - require deletion and recreation
        return obj is None

class CredentialFieldDefinitionAdmin(VersionAdmin):
    list_display = ('key', 'label', 'field_type', 'required', 'order')
    list_filter = ('field_type', 'required')
    search_fields = ('key', 'label')
    ordering = ('order', 'key')
    fieldsets = (
        (None, {
            'fields': ('key', 'label', 'field_type', 'required', 'order')
        }),
        ('Validation', {
            'fields': ('min_length', 'max_length', 'regex_pattern'),
            'classes': ('collapse',)
        }),
        ('Display', {
            'fields': ('help_text', 'placeholder'),
            'classes': ('collapse',)
        }),
    )

class CredentialSetupSessionAdmin(VersionAdmin):
    list_display = ('id', 'account', 'created_at', 'expires_at', 'is_expired', 'is_completed', 'setup_link')
    list_filter = ('created_at', 'expires_at', 'completed_at')
    readonly_fields = ('id', 'created_at', 'completed_at', 'attempts', 'setup_link')
    search_fields = ('account__name', 'id')
    filter_horizontal = ('field_definitions',)

    def setup_link(self, obj):
        if obj.can_attempt:
            url = reverse('unibot:credential_setup', kwargs={'session_id': obj.id})
            return format_html('<a href="{}" target="_blank">Setup Link</a>', url)
        return "Not available"
    setup_link.short_description = "Setup Link"

    def has_change_permission(self, request, obj=None):
        # Prevent editing completed or expired sessions
        if obj and (obj.is_completed or obj.is_expired):
            return False
        return super().has_change_permission(request, obj)

admin.site.register(Bot, BotAdmin)
admin.site.register(Tool, ToolAdmin)
admin.site.register(EncryptedCredential, EncryptedCredentialAdmin)
admin.site.register(CredentialFieldDefinition, CredentialFieldDefinitionAdmin)
admin.site.register(CredentialSetupSession, CredentialSetupSessionAdmin)
