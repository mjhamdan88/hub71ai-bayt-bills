from django.contrib.admin import SimpleListFilter
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta

class ArchiveStatusFilter(SimpleListFilter):
    title = _('Archive Status')
    parameter_name = 'archive_status'
    default_value = 'unarchived'

    def lookups(self, request, model_admin):
        return (
            ('unarchived', _('Unarchived')),
            ('archived', _('Archived')),
            ('all', _('All Chats')),
        )

    def queryset(self, request, queryset):
        value = self.value() or self.default_value
        if value == 'unarchived':
            return queryset.filter(is_archived=False)
        if value == 'archived':
            return queryset.filter(is_archived=True)
        # if value == 'all':
        return queryset

    def choices(self, changelist):
        value = self.value() or self.default_value
        for lookup, title in self.lookup_choices:
            yield {
                'selected': value == str(lookup),
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }

class LastMessageTypeFilter(SimpleListFilter):
    title = _('Last Message Type')
    parameter_name = 'last_message_type'

    def lookups(self, request, model_admin):
        return (
            ('incoming', _('Needs Response')),
            ('outgoing', _('We Responded Last')),
            ('none', _('No Messages')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'incoming':
            return queryset.filter(last_message__is_outgoing=False)
        if self.value() == 'outgoing':
            return queryset.filter(last_message__is_outgoing=True)
        if self.value() == 'none':
            return queryset.filter(last_message__isnull=True)

class LastMessageTimeFilter(SimpleListFilter):
    title = _('Last Activity')
    parameter_name = 'last_activity'

    def lookups(self, request, model_admin):
        return (
            ('1h', _('Within 1 hour')),
            ('24h', _('Within 24 hours')),
            ('7d', _('Within 7 days')),
            ('30d', _('Within 30 days')),
            ('old', _('Older than 30 days')),
            ('none', _('No activity')),
        )

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == '1h':
            return queryset.filter(last_message__timestamp__gte=now - timedelta(hours=1))
        if self.value() == '24h':
            return queryset.filter(last_message__timestamp__gte=now - timedelta(days=1))
        if self.value() == '7d':
            return queryset.filter(last_message__timestamp__gte=now - timedelta(days=7))
        if self.value() == '30d':
            return queryset.filter(last_message__timestamp__gte=now - timedelta(days=30))
        if self.value() == 'old':
            return queryset.filter(last_message__timestamp__lt=now - timedelta(days=30))
        if self.value() == 'none':
            return queryset.filter(last_message__isnull=True)

class MessageHistoryFilter(SimpleListFilter):
    title = _('Message History')
    parameter_name = 'message_history'

    def lookups(self, request, model_admin):
        return (
            ('has_both', _('Has both incoming & outgoing')),
            ('only_incoming', _('Only incoming messages')),
            ('only_outgoing', _('Only outgoing messages')),
            ('empty', _('No messages')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'has_both':
            return queryset.filter(
                first_incoming_message__isnull=False,
                first_outgoing_message__isnull=False
            )
        if self.value() == 'only_incoming':
            return queryset.filter(
                first_incoming_message__isnull=False,
                first_outgoing_message__isnull=True
            )
        if self.value() == 'only_outgoing':
            return queryset.filter(
                first_incoming_message__isnull=True,
                first_outgoing_message__isnull=False
            )
        if self.value() == 'empty':
            return queryset.filter(
                first_message__isnull=True
            )

class DraftScheduleFilter(SimpleListFilter):
    title = _('Schedule Status')
    parameter_name = 'schedule_status'
    default_value = 'pending'

    def lookups(self, request, model_admin):
        return (
            ('pending', _('Pending Approval')),
            ('all', _('All')),
            ('scheduled', _('Scheduled & Approved')),
            ('past_due', _('Past Due')),
            ('draft', _('Draft')),
        )

    def queryset(self, request, queryset):
        value = self.value() or self.default_value
        now = timezone.now()

        if value == 'pending':
            return queryset.filter(status='scheduled', is_approved=False, send_at__gt=now)
        if value == 'scheduled':
            return queryset.filter(status='scheduled', is_approved=True, send_at__gt=now)
        if value == 'past_due':
            return queryset.filter(status='scheduled', send_at__lt=now)
        if value == 'draft':
            return queryset.filter(status='draft')
        if value == 'all':
            return queryset
        return queryset

    def choices(self, changelist):
        value = self.value() or self.default_value
        for lookup, title in self.lookup_choices:
            yield {
                'selected': value == str(lookup),
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            } 