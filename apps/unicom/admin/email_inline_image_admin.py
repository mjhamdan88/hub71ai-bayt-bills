from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from ..models import EmailInlineImage
from unicom.services.get_public_origin import get_public_origin

class EmailInlineImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'file', 'email_message', 'created_at', 'serving_link')
    readonly_fields = ('serving_link',)

    def serving_link(self, obj):
        if not obj.pk:
            return "(save to get link)"
        shortid = obj.get_short_id()
        path = reverse('inline_image', kwargs={'shortid': shortid})
        url = f"{get_public_origin().rstrip('/')}" + path
        return format_html('<a href="{}" target="_blank">{}</a>', url, url)
    serving_link.short_description = "Serving Link" 