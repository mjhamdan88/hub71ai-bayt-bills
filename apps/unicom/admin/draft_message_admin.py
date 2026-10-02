from django.contrib import admin
from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.conf import settings
from ..models import DraftMessage
from .filters import DraftScheduleFilter

class DraftMessageAdmin(admin.ModelAdmin):
    list_display = ('message_preview',)
    list_filter = (
        DraftScheduleFilter,
        'status',
        'is_approved',
        'channel',
        'created_by',
    )
    search_fields = ('text', 'html', 'subject', 'to', 'cc', 'bcc', 'chat_id')
    readonly_fields = ('created_at', 'updated_at', 'sent_at', 'error_message', 'sent_message')
    actions = ['approve_drafts', 'unapprove_drafts']

    fieldsets = (
        (None, {
            'fields': ('channel',)
        }),
        (_('Message Content'), {
            'fields': ('text', 'html'),
            'classes': ('tinymce-content',),
        }),
        (_('Email Specific'), {
            'fields': ('to', 'cc', 'bcc', 'subject'),
            'classes': ('collapse',),
        }),
        (_('Chat Specific'), {
            'fields': ('chat_id',),
            'classes': ('collapse',),
        }),
        (_('Scheduling & Approval'), {
            'fields': ('send_at', 'is_approved', 'status'),
        }),
        (_('Metadata'), {
            'fields': ('created_by', 'created_at', 'updated_at', 'sent_at', 'sent_message', 'error_message'),
            'classes': ('collapse',),
        }),
    )

    class Media:
        css = {
            'all': (
                'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css',
                'unicom/css/draft_message_mobile.css',
            )
        }

    def save_model(self, request, obj, form, change):
        if not change:  # If this is a new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Add TinyMCE for HTML content
        form.Media = type('Media', (), {
            'css': {'all': ('admin/css/forms.css',)},
            'js': (
                'unicom/js/tinymce_init.js',
            )
        })
        return form
    
    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'html':
            kwargs['widget'] = forms.Textarea(attrs={
                'class': 'tinymce',
                'data-tinymce': 'true'
            })
        return super().formfield_for_dbfield(db_field, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.is_staff:
            return qs
        return qs.select_related('channel').filter(channel__created_by_id=request.user.id)

    def approve_drafts(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated} draft(s) have been approved.')
    approve_drafts.short_description = 'Approve selected drafts'

    def unapprove_drafts(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f'{updated} draft(s) have been unapproved.')
    unapprove_drafts.short_description = 'Unapprove selected drafts'

    def message_preview(self, obj):
        # Determine message type and status indicators
        is_email = obj.channel.platform == 'Email'
        is_pending = obj.status == 'scheduled' and not obj.is_approved
        is_past_due = obj.status == 'scheduled' and obj.send_at and obj.send_at < timezone.now()
        
        # Create status icons
        status_icons = format_html(
            '<span class="draft-status-icons">{}{}{}{}</span>',
            format_html('<i class="fas fa-clock text-warning" title="Pending Approval"></i>') if is_pending else '',
            format_html('<i class="fas fa-exclamation-circle text-danger" title="Past Due"></i>') if is_past_due else '',
            format_html('<i class="fas fa-check-circle text-success" title="Approved"></i>') if obj.is_approved else '',
            format_html('<i class="fas fa-envelope" title="Email"></i>') if is_email else format_html('<i class="fas fa-comment" title="Chat"></i>')
        )

        # Prepare content preview
        if is_email and obj.html:
            # Use an iframe for email preview with auto-resize
            iframe_id = f"email-preview-iframe-{obj.pk}"
            content_preview = format_html(
                '''
                <iframe id="{}" style="background-color: white; width:100%;border:none;overflow:hidden;min-height:40px;" scrolling="no" frameborder="0" allowtransparency="true"></iframe>
                <script type="text/javascript">
                (function() {{
                    var iframe = document.getElementById('{}');
                    if (!iframe) return;
                    var doc = iframe.contentDocument || iframe.contentWindow.document;
                    var html = '<!DOCTYPE html>' +
                        '<html><head>' +
                        '<style>body {{ zoom: 0.50; -moz-transform: scale(0.50); -moz-transform-origin: 0 0; }}</style>' +
                        '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css">' +
                        '</head><body>' + {} + '</body></html>';
                    doc.open();
                    doc.write(html);
                    doc.close();
                    function resizeIframe() {{
                        setTimeout(function() {{
                            if (!iframe.contentWindow.document.body) return;
                            var body = iframe.contentWindow.document.body;
                            var html = iframe.contentWindow.document.documentElement;
                            var height = Math.max(
                                body.scrollHeight,
                                body.offsetHeight,
                                html.clientHeight,
                                html.scrollHeight,
                                html.offsetHeight
                            );
                            iframe.style.height = (height * 0.5) + 'px';
                        }}, 50);
                    }}
                    // Resize on load and after images load
                    iframe.onload = resizeIframe;
                    doc.addEventListener('DOMContentLoaded', resizeIframe);
                    var imgs = doc.images;
                    for (var i = 0; i < imgs.length; i++) {{
                        imgs[i].addEventListener('load', resizeIframe);
                    }}
                    // Fallback resize after a short delay
                    setTimeout(resizeIframe, 500);
                }})();
                </script>
                ''',
                iframe_id,
                iframe_id,
                mark_safe(repr(obj.html))
            )
        else:
            content_preview = obj.text if obj.text else 'No content'

        # Format recipients for email
        recipients = ''
        if is_email:
            to_list = ', '.join(obj.to) if obj.to else ''
            cc_list = f' (cc: {", ".join(obj.cc)})' if obj.cc else ''
            recipients = f'{to_list}{cc_list}' if to_list or cc_list else 'No recipients'

        return format_html('''
            <div style="background-color: unset;" class="draft-message-container">
                <div class="draft-header">
                    <div class="draft-title">
                        <span class="draft-subject">{}</span>
                        {}
                    </div>
                    <div class="draft-meta">
                        <span class="draft-channel">{}</span>
                        <span class="draft-time" title="Send At">{}</span>
                    </div>
                </div>
                {}
                <div class="draft-content">
                    {}
                </div>
                <div class="draft-footer">
                    <span class="draft-creator">By: {}</span>
                    <span class="draft-created">Created: {}</span>
                </div>
            </div>
            <style>
                .draft-message-container {{
                    padding: 15px;
                    border-radius: 4px;
                    background: var(--body-bg);
                    margin: 5px 0;
                }}
                .draft-header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: flex-start;
                    margin-bottom: 10px;
                }}
                .draft-title {{
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }}
                .draft-subject {{
                    font-weight: bold;
                    font-size: 1.1em;
                    color: var(--link-fg);
                }}
                .draft-status-icons {{
                    display: flex;
                    gap: 8px;
                }}
                .draft-status-icons i {{
                    font-size: 1.1em;
                }}
                .text-warning {{
                    color: #f39c12;
                }}
                .text-danger {{
                    color: #e74c3c;
                }}
                .text-success {{
                    color: #2ecc71;
                }}
                .draft-meta {{
                    display: flex;
                    gap: 15px;
                    align-items: center;
                }}
                .draft-channel {{
                    background-color: var(--selected-row);
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-size: 0.9em;
                }}
                .draft-time {{
                    color: var(--body-quiet-color);
                    font-size: 0.9em;
                }}
                .draft-recipients {{
                    font-size: 0.9em;
                    color: var(--body-quiet-color);
                    margin: 5px 0;
                }}
                .draft-content {{
                    margin: 0;
                    padding: 0;
                    background: none;
                    border-radius: 0;
                    overflow-y: auto;
                }}
                .draft-footer {{
                    display: flex;
                    justify-content: space-between;
                    font-size: 0.8em;
                    color: var(--body-quiet-color);
                    margin-top: 10px;
                }}
            </style>
        ''',
        obj.subject or 'No Subject',
        status_icons,
        obj.channel,
        obj.send_at.strftime('%Y-%m-%d %H:%M') if obj.send_at else 'No schedule',
        format_html('<div class="draft-recipients">{}</div>', recipients) if recipients else '',
        content_preview,
        (obj.created_by.get_full_name() or obj.created_by.username) if obj.created_by else 'Unknown',
        obj.created_at.strftime('%Y-%m-%d %H:%M')
        )
    message_preview.short_description = 'Draft Messages' 