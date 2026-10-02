from django.contrib import admin
from django import forms
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from ..models import MessageTemplate
from ..models.message_template import MessageTemplateInlineImage

class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ('content_preview',)
    list_filter = ('category', 'channels')
    search_fields = ('title', 'description', 'content')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('channels',)
    
    fieldsets = (
        (None, {
            'fields': ('title', 'category')
        }),
        (_('Template Content'), {
            'fields': ('description', 'content'),
            'classes': ('tinymce-content',),
        }),
        (_('Availability'), {
            'fields': ('channels',),
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Only include the local tinymce_init.js, not the CDN script
        form.Media = type('Media', (), {
            'css': {'all': ('admin/css/forms.css',)},
            'js': (
                'unicom/js/tinymce_init.js',
            )
        })
        return form

    def render_change_form(self, request, context, *args, **kwargs):
        context['tinymce_api_key'] = settings.UNICOM_TINYMCE_API_KEY
        return super().render_change_form(request, context, *args, **kwargs)

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'content':
            kwargs['widget'] = forms.Textarea(attrs={
                'class': 'tinymce',
                'data-tinymce': 'true'
            })
        return super().formfield_for_dbfield(db_field, **kwargs)

    def content_preview(self, obj):
        if not obj.content:
            return 'No content'
        iframe_id = f"template-preview-iframe-{obj.pk}"
        # Build admin change URL for the template
        from django.urls import reverse
        change_url = reverse('admin:unicom_messagetemplate_change', args=[obj.pk])
        # Render channels as badges
        channels = obj.channels.all()
        channel_badges = format_html(''.join([
            '<span class="draft-channel">{}</span>'
            .format(channel.name) for channel in channels
        ])) if channels else 'No channels'
        return format_html('''
            <div class="draft-message-container">
                <div class="draft-header">
                    <div class="draft-title">
                        <a href="{}" class="draft-subject" style="font-weight:bold;font-size:1.1em;color:var(--link-fg);">{}</a>
                    </div>
                    <div class="draft-meta" style="margin-left:auto;">
                        {}
                    </div>
                </div>
                <div class="draft-content">
                    <iframe id="{}" style="background-color: white; width:100%;border:none;overflow:hidden;min-height:40px;" scrolling="no" frameborder="0" allowtransparency="true"></iframe>
                </div>
                <div class="draft-footer">
                    <span class="draft-category">Category: {}</span>
                    <span class="draft-created">Created: {}</span>
                </div>
            </div>
            <script type="text/javascript">
            (function() {{
                var iframe = document.getElementById('{}');
                if (!iframe) return;
                var doc = iframe.contentDocument || iframe.contentWindow.document;
                var html = '<!DOCTYPE html>' +
                    '<html><head>' +
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
                        iframe.style.height = height + 'px';
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
                    align-items: center;
                    margin-bottom: 10px;
                }}
                .draft-title {{
                    display: block;
                    text-align: left;
                    margin-right: 20px;
                }}
                .draft-subject {{
                    font-weight: bold;
                    font-size: 1.1em;
                    color: var(--link-fg);
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
                    margin-right: 5px;
                }}
                .draft-content {{
                    margin: 10px 0;
                    padding: 10px;
                    background: var(--darkened-bg);
                    border-radius: 4px;
                    max-height: 300px;
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
        change_url,
        obj.title or 'No Title',
        channel_badges,
        iframe_id,
        obj.category or 'Uncategorized',
        obj.created_at.strftime('%Y-%m-%d %H:%M'),
        iframe_id,
        mark_safe(repr(obj.content))
        )
    content_preview.short_description = 'Template Preview'

class MessageTemplateInlineImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'file', 'template', 'created_at', 'serving_link')
    readonly_fields = ('serving_link',)

    def serving_link(self, obj):
        if not obj.pk:
            return "(save to get link)"
        shortid = obj.get_short_id()
        path = self._get_reverse_path(shortid)
        url = self._get_public_url(path)
        return format_html('<a href="{}" target="_blank">{}</a>', url, url)
    serving_link.short_description = "Serving Link"

    def _get_reverse_path(self, shortid):
        from django.urls import reverse
        return reverse('template_inline_image', kwargs={'shortid': shortid})

    def _get_public_url(self, path):
        from unicom.services.get_public_origin import get_public_origin
        return f"{get_public_origin().rstrip('/')}" + path 