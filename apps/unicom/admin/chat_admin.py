from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings
from django_ace import AceWidget
from django import forms
from django.utils.safestring import mark_safe
from ..models import Chat
from ..views.chat_history_view import chat_history_view
from ..views.compose_view import compose_view
from .filters import LastMessageTypeFilter, LastMessageTimeFilter, MessageHistoryFilter, ArchiveStatusFilter

class ChatAdmin(admin.ModelAdmin):
    ordering = ['-last_message__timestamp']
    list_filter = (
        LastMessageTypeFilter,
        LastMessageTimeFilter,
        MessageHistoryFilter,
        ArchiveStatusFilter,
        'platform',
        'is_private',
        'channel',
    )
    list_display = ('chat_info',)
    search_fields = ('id', 'name', 'messages__text', 'messages__sender__name')
    actions = ['archive_chats', 'unarchive_chats']

    class Media:
        css = {
            'all': (
                'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css',
            )
        }

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.is_staff:
            return qs
        return qs.select_related('channel').filter(channel__created_by_id=request.user.id)

    def archive_chats(self, request, queryset):
        updated = queryset.update(is_archived=True)
        self.message_user(request, f'{updated} chat(s) have been archived.')
    archive_chats.short_description = 'Archive selected chats'

    def unarchive_chats(self, request, queryset):
        updated = queryset.update(is_archived=False)
        self.message_user(request, f'{updated} chat(s) have been unarchived.')
    unarchive_chats.short_description = 'Unarchive selected chats'

    def chat_info(self, obj):
        name = obj.name or obj.id
        last_message = obj.last_message
        last_message_text = last_message.text[:100] + '...' if last_message and last_message.text and len(last_message.text) > 100 else (last_message.text if last_message else 'No messages')
        
        # Determine message status indicators
        has_incoming = obj.first_incoming_message is not None
        has_outgoing = obj.first_outgoing_message is not None
        is_last_incoming = last_message and last_message.is_outgoing is False
        
        # Create status icons HTML
        status_icons = format_html(
            '<span class="chat-status-icons">{}{}{}</span>',
            format_html('<i class="fas fa-inbox" title="Has incoming messages"></i>') if has_incoming else '',
            format_html('<i class="fas fa-paper-plane" title="Has outgoing messages"></i>') if has_outgoing else '',
            format_html('<i class="fas fa-archive" title="Archived"></i>') if obj.is_archived else ''
        )
        
        # Create last message icon
        last_message_icon = ''
        if last_message:
            if is_last_incoming:
                last_message_icon = format_html('<i class="fas fa-reply pending-response" title="Pending response"></i>')
            else:
                last_message_icon = format_html('<i class="fas fa-check" title="Last message was outgoing"></i>')
        
        return format_html('''
            <a href="{}" class="chat-info-container{}">
                <div class="chat-header">
                    <span class="chat-name">{}</span>
                    {}
                </div>
                <div class="chat-message">
                    <span class="message-status-icon">{}</span>
                    <span class="message-text">{}</span>
                </div>
                <div class="chat-footer">
                    <span class="chat-channel">{}</span>
                    <span class="chat-time">{}</span>
                </div>
            </a>
            <style>
                .chat-info-container {{
                    display: block;
                    padding: 10px;
                    text-decoration: none;
                    color: var(--body-fg);
                    border-radius: 4px;
                    transition: background-color 0.2s;
                }}
                .chat-info-container:hover {{
                    background-color: var(--darkened-bg);
                }}
                .chat-info-container.archived {{
                    opacity: 0.7;
                }}
                .chat-header {{
                    margin-bottom: 5px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }}
                .chat-name {{
                    font-weight: bold;
                    font-size: 1.1em;
                    color: var(--link-fg);
                }}
                .chat-status-icons {{
                    display: flex;
                    gap: 8px;
                    font-size: 0.8em;
                    color: var(--body-quiet-color);
                }}
                .chat-status-icons i {{
                    opacity: 0.7;
                }}
                .chat-message {{
                    color: var(--body-fg);
                    margin-bottom: 5px;
                    font-size: 0.9em;
                    opacity: 0.9;
                    display: flex;
                    align-items: flex-start;
                    gap: 8px;
                }}
                .message-status-icon {{
                    flex-shrink: 0;
                    margin-top: 3px;
                }}
                .message-status-icon .pending-response {{
                    color: #e74c3c;
                }}
                .message-text {{
                    flex-grow: 1;
                }}
                .chat-footer {{
                    display: flex;
                    justify-content: space-between;
                    font-size: 0.8em;
                    color: var(--body-quiet-color);
                }}
                .chat-channel {{
                    background-color: var(--selected-row);
                    padding: 2px 6px;
                    border-radius: 3px;
                }}
                .chat-time {{
                    color: var(--body-quiet-color);
                }}
            </style>
        ''',
        self.url_for_chat(obj.id),
        ' archived' if obj.is_archived else '',
        name,
        status_icons,
        last_message_icon,
        last_message_text,
        obj.channel,
        last_message.timestamp.strftime('%Y-%m-%d %H:%M') if last_message else 'Never'
        )
    chat_info.short_description = 'Chats'
    chat_info.admin_order_field = '-last_message__timestamp'

    def url_for_chat(self, id):
        return f"{id}/messages/"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<path:chat_id>/messages/', self.admin_site.admin_view(chat_history_view), name='chat-detail'),
            path('compose/', self.admin_site.admin_view(compose_view), name='chat-compose'),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_add_button'] = False  # Hide the default "Add" button
        return super().changelist_view(request, extra_context=extra_context)

    def has_add_permission(self, request):
        return False  # Disable the default add form

    def get_changelist_template(self, request):
        return "admin/unicom/chat/change_list.html" 