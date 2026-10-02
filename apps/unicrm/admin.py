import json

from django import forms
from django.conf import settings
from django.contrib import admin
from django.db.models import BooleanField, Case, CharField, Count, F, Q, Value, When
from django.forms.models import BaseInlineFormSet
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import formats, timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _, ngettext
from django_ace import AceWidget

import logging

from . import models

logger = logging.getLogger(__name__)

MAILING_LIST_STATUS_META = [
    ('valid', _('valid'), '#16a34a'),
    ('accept_all', _('accept-all'), '#0ea5e9'),
    ('risky', _('risky'), '#f59e0b'),
    ('unknown', _('unknown'), '#94a3b8'),
    ('not_verified', _('not verified'), '#6b7280'),
    ('invalid', _('invalid'), '#b91c1c'),
    ('blocked', _('blocked'), '#111827'),
    ('unsubscribed', _('unsubscribed'), '#f97316'),
    ('no_email', _('no email'), '#d1d5db'),
]

MAILING_LIST_STATUS_LABELS = {key: str(label) for key, label, _ in MAILING_LIST_STATUS_META}


def _map_verification_bucket(status: str) -> str:
    normalized = (status or '').strip().lower()
    if normalized == 'valid':
        return 'valid'
    if normalized == 'accept_all':
        return 'accept_all'
    if normalized == 'risky':
        return 'risky'
    if normalized == 'unknown':
        return 'unknown'
    if normalized in {'invalid', 'not_found', 'duplicate_email', 'bounced', 'failed'}:
        return 'invalid'
    if normalized:
        return 'not_verified'
    return 'not_verified'


class LimitedSubscriptionFormSet(BaseInlineFormSet):
    limit = None

    def get_queryset(self):
        qs = super().get_queryset()
        limit = getattr(self, 'limit', None)
        if limit:
            return qs[:limit]
        return qs


class SubscriptionPreviewInline(admin.TabularInline):
    model = models.Subscription
    extra = 0
    can_delete = False
    show_change_link = False
    fields = (
        'contact_link',
        'contact_email',
        'company_name',
        'subscriber_status',
        'contact_bounced',
        'contact_blacklisted',
        'gp_status_display',
        'subscribed_at',
        'unsubscribed_at',
        'unsubscribe_feedback',
    )
    readonly_fields = fields
    verbose_name_plural = _('Recent subscribers (latest 100)')
    formset = LimitedSubscriptionFormSet

    SUBSCRIBER_LIMIT = 100

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.limit = self.SUBSCRIBER_LIMIT
        return formset

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        try:
            unsub_all_flag = Case(
                When(contact__unsubscribe_all_entries__isnull=False, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
            qs = (
                qs.select_related('contact', 'contact__company')
                .annotate(
                    _has_unsubscribe_all=unsub_all_flag,
                    gp_status=F('contact__gp_email_status'),
                )
                .order_by('-subscribed_at')
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception('Failed to load subscriber preview inline.')
            qs = qs.select_related('contact', 'contact__company').order_by('-subscribed_at')
        return qs

    def contact_link(self, obj):
        if not obj.contact_id:
            return '—'
        url = reverse('admin:unicrm_contact_change', args=[obj.contact_id])
        return format_html('<a href="{}">{}</a>', url, obj.contact)

    contact_link.short_description = _('Contact')

    def contact_email(self, obj):
        return obj.contact.email or '—'

    contact_email.short_description = _('Email')

    def company_name(self, obj):
        return obj.contact.company or '—'

    company_name.short_description = _('Company')

    def subscriber_status(self, obj):
        email = (obj.contact.email or '').strip()
        if getattr(obj, '_has_unsubscribe_all', False):
            bucket = 'blocked'
        elif obj.unsubscribed_at:
            bucket = 'unsubscribed'
        elif not email:
            bucket = 'no_email'
        else:
            bucket = _map_verification_bucket(getattr(obj, 'gp_status', ''))
        label = MAILING_LIST_STATUS_LABELS.get(bucket, MAILING_LIST_STATUS_LABELS.get('not_verified'))
        return label or '—'

    subscriber_status.short_description = _('Status')

    def contact_bounced(self, obj):
        return bool(getattr(obj.contact, 'email_bounced', False))

    contact_bounced.short_description = _('Bounced')
    contact_bounced.boolean = True

    def contact_blacklisted(self, obj):
        flag = getattr(obj, '_has_unsubscribe_all', None)
        if flag is None:
            flag = obj.contact.unsubscribe_all_entries.exists()
        return bool(flag)

    contact_blacklisted.short_description = _('Blacklisted')
    contact_blacklisted.boolean = True

    def gp_status_display(self, obj):
        status = (obj.contact.gp_email_status or '').strip()
        if not status:
            return '—'
        return status.replace('_', ' ').title()

    gp_status_display.short_description = _('GetProspect status')


class TemplateVariableForm(forms.ModelForm):
    class Meta:
        model = models.TemplateVariable
        fields = '__all__'
        widgets = {
            'code': AceWidget(
                mode='python',
                theme='github',
                width='100%',
                height='260px',
                fontsize='12px',
                showprintmargin=False,
            ),
        }


class SegmentForm(forms.ModelForm):
    class Meta:
        model = models.Segment
        fields = '__all__'
        widgets = {
            'code': AceWidget(
                mode='python',
                theme='github',
                width='100%',
                height='260px',
                fontsize='12px',
                showprintmargin=False,
            ),
        }


@admin.register(models.Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'domain', 'website', 'created_at')
    search_fields = ('name', 'domain')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(models.Contact)
class ContactAdmin(admin.ModelAdmin):
    change_list_template = "admin/unicrm/contact/change_list.html"
    list_display = ('email', 'first_name', 'last_name', 'company', 'owner', 'insight_id', 'communication_history_preview', 'created_at')
    search_fields = ('email', 'first_name', 'last_name', 'insight_id')
    list_filter = ('company',)
    readonly_fields = ('created_at', 'updated_at', 'communication_history_pretty')
    autocomplete_fields = ('company', 'owner')

    def communication_history_pretty(self, obj):
        content = obj.formatted_communication_history() or ''
        # Escape HTML and preserve newlines
        return format_html('<pre style="white-space:pre-wrap; margin:0;">{}</pre>', content)

    communication_history_pretty.short_description = _('Communication history')

    def communication_history_preview(self, obj):
        content = obj.formatted_communication_history() or ''
        first_line = content.split('\n', 1)[0]
        return first_line[:80] + ('…' if len(first_line) > 80 else '')

    communication_history_preview.short_description = _('History')

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['lead_search_url'] = reverse('unicrm:lead-search')
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(models.MailingList)
class MailingListAdmin(admin.ModelAdmin):
    list_display = ('mailing_list_card',)
    search_fields = ('name', 'public_name', 'slug')
    readonly_fields = ('subscriber_summary', 'created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('name', 'public_name', 'slug', 'description', 'subscriber_summary')}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    inlines = (SubscriptionPreviewInline,)

    STATUS_META = MAILING_LIST_STATUS_META

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _total_subscribers=Count('subscriptions', distinct=True),
        )

    def mailing_list_card(self, obj):
        created = formats.date_format(timezone.localtime(obj.created_at), 'SHORT_DATETIME_FORMAT')
        chart = self._render_status_card(obj, compact=True)
        if chart:
            chart_section = chart
        else:
            chart_section = format_html(
                '<div class="mailinglist-card__chart-empty">{}</div>',
                _('No emails recorded for this mailing list yet.'),
            )
        tree_section = self._render_communication_tree(
            obj,
            include_title=False,
            compact=True,
            allow_empty=False,
        )
        chart_label = _('Subscribers')
        tree_html = ''
        if tree_section:
            tree_html = format_html(
                '<div class="mailinglist-card__tree">'
                '<div class="mailinglist-card__tree-heading">{}</div>'
                '{}'
                '</div>',
                _('Communication Funnel'),
                tree_section,
            )
        return format_html(
            '<div class="mailinglist-card">'
            '<div class="mailinglist-card__details">'
            '<div class="mailinglist-card__title">{}</div>'
            '<div class="mailinglist-card__public">{}</div>'
            '<div class="mailinglist-card__meta"><span><strong>Slug:</strong> {}</span>'
            '<span><strong>{}:</strong> {}</span></div>'
            '</div>'
            '<div class="mailinglist-card__visuals">'
            '<div class="mailinglist-card__chart"><span class="mailinglist-card__chart-label">{}</span>{}</div>'
            '{}'
            '</div>'
            '</div>',
            obj.name,
            obj.public_name or _('No public name'),
            obj.slug,
            _('Created'),
            created,
            chart_label,
            chart_section,
            tree_html,
        )

    mailing_list_card.short_description = _('Mailing list')
    mailing_list_card.admin_order_field = 'name'

    def subscriber_summary(self, obj):
        if not obj or not obj.pk:
            return _('Save the mailing list to view subscriber metrics.')
        try:
            chart = self._render_status_card(obj)
            if not chart:
                return _('No emails recorded for this mailing list yet.')
            return format_html('<div class="module">{}</div>', chart)
        except Exception:  # pragma: no cover - defensive
            logger.exception('Failed to render subscriber summary for mailing list %s.', getattr(obj, 'pk', None))
            return format_html('<div class="module errornote">{}</div>', _('Unable to render subscriber summary.'))

    subscriber_summary.short_description = _('Subscriber insights')

    def _status_segments(self, obj):
        counts = self._verification_counts(obj)
        segments = []
        for key, label, color in self.STATUS_META:
            segments.append({
                'key': key,
                'label': str(label),
                'count': counts.get(key, 0),
                'color': color,
                'textColor': '#ffffff',
            })
        return segments

    def _render_status_card(self, obj, compact=False):
        try:
            segments = self._status_segments(obj)
            total = sum(segment['count'] for segment in segments)
            data_json = json.dumps(segments, default=str)
            classes = ['comm-status-card']
            if compact:
                classes.append('comm-status-card--compact')
            if not total:
                aria_label = _('No subscribers yet')
            else:
                aria_label = _('Mailing list subscriber breakdown')
            return format_html(
                '<div class="{classes}" data-chart="{data}" data-total="{total}" data-empty-label="{empty}">'
                '<div class="comm-status-card__chart">'
                '<div class="comm-status-card__pie" role="img" aria-label="{aria}"></div>'
                '<ul class="comm-status-card__legend"></ul>'
                '</div>'
                '</div>',
                classes=' '.join(classes),
                data=data_json,
                total=total,
                empty=_('No subscribers yet'),
                aria=aria_label,
            ) if segments else ''
        except Exception:  # pragma: no cover - defensive
            logger.exception('Failed to render mailing list status chart for %s.', getattr(obj, 'pk', None))
            return ''

    def _get_communication_admin(self):
        if not hasattr(self, '_communication_admin_instance'):
            self._communication_admin_instance = CommunicationAdmin(models.Communication, self.admin_site)
        return self._communication_admin_instance

    def _communication_chart_segments(self, communication):
        base_url = reverse('admin:unicrm_communication_deliveries', args=[communication.pk])
        summary = {'communication_id': communication.pk}
        return self._get_communication_admin()._chart_segments(summary, base_url)

    def _verification_counts(self, obj):
        counts = {key: 0 for key, *_ in self.STATUS_META}
        annotated = (
            obj.subscriptions
            .select_related('contact')
            .annotate(
                has_block=Case(
                    When(contact__unsubscribe_all_entries__isnull=False, then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField(),
                ),
                gp_status=F('contact__gp_email_status'),
            )
            .values('has_block', 'gp_status', 'unsubscribed_at', 'contact__email')
        )

        for entry in annotated:
            email = (entry.get('contact__email') or '').strip()
            if entry.get('has_block'):
                bucket = 'blocked'
            elif entry.get('unsubscribed_at'):
                bucket = 'unsubscribed'
            elif not email:
                bucket = 'no_email'
            else:
                bucket = _map_verification_bucket(entry.get('gp_status') or '')
            counts[bucket] = counts.get(bucket, 0) + 1
        return counts

    def _render_communication_tree(self, obj, include_title=True, compact=False, allow_empty=True):
        nodes = self._build_communication_tree_nodes(obj, compact=compact)
        if nodes:
            body = format_html(
                '<div class="mailinglist-communications-tree__nodes">{}</div>',
                mark_safe(''.join(nodes)),
            )
        else:
            if not allow_empty:
                return ''
            body = format_html(
                '<p class="mailinglist-communications-tree__empty">{}</p>',
                _('No communications linked to this mailing list yet.'),
            )
        title_html = format_html(
            '<div class="mailinglist-communications-tree__title">{}</div>',
            _('Communication tree'),
        ) if include_title else ''
        classes = ['mailinglist-communications-tree']
        if compact:
            classes.append('mailinglist-communications-tree--compact')
        return format_html(
            '<div class="{}">{}{}</div>',
            ' '.join(classes),
            title_html,
            body,
        )

    def _render_communication_circle(self, communication):
        segments = self._communication_chart_segments(communication)
        total = sum(segment['count'] for segment in segments)
        data = json.dumps(segments, default=str)
        aria_label = _('Communication %(title)s: %(total)s updates') % {
            'title': communication.display_title,
            'total': total,
        }
        circle = format_html(
            '<div class="comm-status-card comm-status-card--mini" data-chart="{data}" data-total="{total}" data-empty-label="{empty}">'
            '<span class="comm-status-card--mini__total">{total_val}</span>'
            '<div class="comm-status-card__chart">'
            '<div class="comm-status-card__pie" role="img" aria-label="{aria}"></div>'
            '</div>'
            '<ul class="comm-status-card__legend comm-status-card__legend--hidden"></ul>'
            '</div>',
            data=data,
            total=total,
            empty=_('No deliveries yet'),
            aria=aria_label,
            total_val=total or 0,
        )
        tooltip = format_html('{} — {}', communication.display_title, communication.segment.name if communication.segment else _('No segment'))
        return format_html(
            '<a href="{}" class="mailinglist-communications-tree__node-link" title="{}">{}</a>',
            reverse('admin:unicrm_communication_change', args=[communication.pk]),
            tooltip,
            circle,
        )

    def _build_communication_tree_nodes(self, obj, compact=False):
        communications = list(
            models.Communication.objects.filter(mailing_list=obj).order_by('created_at')
        )
        if not communications:
            return []
        roots = [comm for comm in communications if comm.follow_up_for_id is None]
        if not roots:
            roots = communications
        rendered = []
        visited = set()
        for root in roots:
            if root.pk in visited:
                continue
            rendered.append(self._render_communication_node(root, visited, compact=compact))
        return rendered

    def _render_communication_node(self, communication, visited, compact=False):
        visited.add(communication.pk)
        children = []
        for follow_up in communication.followups.order_by('created_at'):
            if follow_up.pk in visited:
                continue
            children.append(self._render_communication_node(follow_up, visited, compact=compact))
        children_markup = ''
        if children:
            children_markup = format_html(
                '<div class="mailinglist-communications-tree__children">{}</div>',
                mark_safe(''.join(children)),
            )
        circle = self._render_communication_circle(communication)
        classes = ['mailinglist-communications-tree__node']
        if children_markup:
            classes.append('mailinglist-communications-tree__node--has-children')
        return format_html(
            '<div class="{}">{circle}{children}</div>',
            ' '.join(classes),
            circle=circle,
            children=children_markup,
        )

    class Media:
        css = {'all': ('unicrm/css/communication_status_chart.css',)}
        js = ('unicrm/js/communication_status_chart.js',)


@admin.register(models.Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('contact', 'mailing_list', 'subscribed_at', 'unsubscribed_at')
    list_filter = ('mailing_list',)
    search_fields = ('contact__email', 'contact__first_name', 'contact__last_name')
    autocomplete_fields = ('contact', 'mailing_list')
    readonly_fields = ('created_at', 'updated_at', 'subscribed_at')


@admin.register(models.UnsubscribeAll)
class UnsubscribeAllAdmin(admin.ModelAdmin):
    list_display = ('contact', 'communication', 'message', 'unsubscribed_at')
    search_fields = ('contact__email', 'contact__first_name', 'contact__last_name')
    list_filter = ('unsubscribed_at',)
    autocomplete_fields = ('contact', 'communication', 'message')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(models.Segment)
class SegmentAdmin(admin.ModelAdmin):
    form = SegmentForm
    list_display = ('name', 'contact_count', 'updated_at')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at', 'contact_count', 'contact_sample')

    fieldsets = (
        (None, {'fields': ('name', 'description')}),
        (_('Filter code'), {'fields': ('code',)}),
        (_('Preview'), {'fields': ('contact_count', 'contact_sample')}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )

    def contact_count(self, obj):
        if not obj.pk:
            return _('Save to preview contacts')
        try:
            return obj.apply().count()
        except Exception as exc:  # pragma: no cover - defensive
            return format_html('<span style="color:red;">Error: {}</span>', exc)

    contact_count.short_description = _('Matching contacts')

    def contact_sample(self, obj):
        if not obj.pk:
            return _('Save to preview contacts')
        try:
            contacts = obj.apply().select_related('company')[:10]
            if not contacts:
                return _('No contacts match this segment yet.')
            
            rows = []
            for contact in contacts:
                company_info = f" ({contact.company.name})" if contact.company else ""
                rows.append((f"{contact}{company_info}", contact.email))
            
            return format_html(
                '<div style="max-height: 300px; overflow-y: auto;"><ul style="margin:0; padding-left: 20px;">{}</ul></div>',
                format_html_join('', '<li><strong>{}</strong> &lt;{}&gt;</li>', rows)
            )
        except Exception as exc:
            return format_html('<span style="color:red;">Error: {}</span>', exc)

    contact_sample.short_description = _('Sample contacts')


@admin.register(models.TemplateVariable)
class TemplateVariableAdmin(admin.ModelAdmin):
    form = TemplateVariableForm
    list_display = ('key', 'label', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('key', 'label')
    readonly_fields = ('created_at', 'updated_at', 'sample_preview')

    fieldsets = (
        (None, {'fields': ('key', 'label', 'description', 'is_active')}),
        (_('Code'), {'fields': ('code',)}),
        (_('Preview'), {'fields': ('sample_preview',)}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )

    def sample_preview(self, obj):
        if not obj.pk:
            return _('Save to preview sample output')
        values = obj.sample_values(limit=3)
        return format_html(
            '<ul style="margin:0;">{}</ul>',
            format_html_join('', '<li>{}</li>', ((value,) for value in values))
        )

    sample_preview.short_description = _('Sample output')


class CommunicationAdminForm(forms.ModelForm):
    class Meta:
        model = models.Communication
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        # Extract user from kwargs if passed
        self._user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter channel field to only show email channels
        from unicom.models import Channel
        email_channels = Channel.objects.filter(platform='Email', active=True)
        self.fields['channel'].queryset = email_channels
        
        # If only one email channel exists, select it by default
        if not self.instance.pk and email_channels.count() == 1:
            self.fields['channel'].initial = email_channels.first()
        
        # Set default status to 'scheduled' for new objects
        if not self.instance.pk:
            self.fields['status'].initial = 'scheduled'

    def clean(self):
        cleaned = super().clean()
        segment = cleaned.get('segment')
        follow_up_for = cleaned.get('follow_up_for')

        if segment and getattr(segment, 'for_followup', False) and not follow_up_for:
            self.add_error('follow_up_for', _('This segment references a previous communication; please choose one.'))

        if follow_up_for and follow_up_for == self.instance:
            self.add_error('follow_up_for', _('Communication cannot follow up on itself.'))

        if follow_up_for and not cleaned.get('auto_enroll_new_contacts'):
            cleaned['auto_enroll_new_contacts'] = True

        return cleaned

    def save(self, commit=True):
        # Auto-set initiated_by to current user if not already set
        if not self.instance.initiated_by and self._user:
            self.instance.initiated_by = self._user
        return super().save(commit)


@admin.register(models.Communication)
class CommunicationAdmin(admin.ModelAdmin):
    form = CommunicationAdminForm
    change_form_template = 'admin/unicrm/communication/change_form.html'
    list_display = ('communication_card',)
    list_display_links = None
    list_filter = ('status', 'channel', 'auto_enroll_new_contacts')
    search_fields = ('subject_template', 'segment__name', 'content')
    autocomplete_fields = ('segment',)
    readonly_fields = ('created_at', 'updated_at', 'status_summary_pretty', 'initiated_by')

    fieldsets = (
        (None, {'fields': ('segment', 'mailing_list', 'follow_up_for', 'exclude_follow_up_siblings', 'channel')}),
        (_('Content'), {'fields': ('subject_template', 'content')}),
        (_('Scheduling'), {'fields': ('scheduled_for', 'status', 'auto_enroll_new_contacts', 'skip_antispam_guards')}),
        (_('Status summary'), {'fields': ('status_summary_pretty',)}),
        (_('Metadata'), {'fields': ('initiated_by',)}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )

    def add_view(self, request, form_url='', extra_context=None):
        return redirect('unicrm:communications-compose')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('segment', 'channel')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:communication_id>/deliveries/',
                self.admin_site.admin_view(self.deliveries_view),
                name='unicrm_communication_deliveries',
            ),
        ]
        return custom_urls + urls

    def deliveries_view(self, request, communication_id, *args, **kwargs):
        communication = get_object_or_404(
            models.Communication.objects.select_related('segment', 'channel', 'initiated_by'),
            pk=communication_id,
        )
        communication.refresh_status_summary(commit=False)

        base_queryset = (
            communication.messages
            .select_related('contact', 'message')
            .order_by('contact__email')
        )

        search_query = request.GET.get('q', '').strip()
        if search_query:
            base_queryset = base_queryset.filter(
                Q(contact__email__icontains=search_query)
                | Q(contact__first_name__icontains=search_query)
                | Q(contact__last_name__icontains=search_query)
            )

        status_meta = self._status_meta()
        active_statuses = {
            value for value in request.GET.getlist('status') if value in status_meta
        }

        deliveries_raw = list(base_queryset)
        status_counts = {key: 0 for key in status_meta}

        for delivery in deliveries_raw:
            status_key = self._delivery_bucket(delivery)
            status_counts[status_key] = status_counts.get(status_key, 0) + 1

        deliveries_data = []
        for delivery in deliveries_raw:
            status_key = self._delivery_bucket(delivery)
            if active_statuses and status_key not in active_statuses:
                continue

            metadata = delivery.metadata or {}
            payload = metadata.get('payload') or {}
            meta = status_meta[status_key]
            replies = metadata.get('replies') or []
            message = delivery.message
            chat_id = getattr(message, 'chat_id', None) if message else None
            if not chat_id:
                chat_id = metadata.get('chat_id')
            chat_url = ''
            if chat_id:
                chat_url = f"/admin/unicom/chat/{chat_id}/messages/"
            deliveries_data.append({
                'delivery': delivery,
                'metadata_status': metadata.get('status'),
                'metadata_pretty': json.dumps(metadata, indent=2, sort_keys=True, default=str),
                'payload': payload,
                'errors': metadata.get('errors') or [],
                'send_at': metadata.get('send_at'),
                'scheduled_at': delivery.scheduled_at,
                'status_key': status_key,
                'status_label': meta['label'],
                'status_color': meta['color'],
                'status_text_color': meta['text_color'],
                'has_reply': delivery.has_received_reply,
                'replied_at': delivery.replied_at,
                'reply_count': len(replies),
                'chat_id': chat_id,
                'chat_url': chat_url,
                'reply_ids': replies,
            })

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'communication': communication,
            'deliveries': deliveries_data,
            'status_options': [
                {
                    'key': key,
                    'label': status_meta[key]['label'],
                    'color': status_meta[key]['color'],
                    'count': status_counts.get(key, 0),
                    'active': key in active_statuses,
                }
                for key, *_ in self.STATUS_META
            ],
            'search_query': search_query,
            'applied_filters': sorted(active_statuses),
            'overall_count': communication.messages.count(),
            'total_count': len(deliveries_raw),
            'filtered_count': len(deliveries_data),
            'media': self.media,
        }
        return TemplateResponse(
            request,
            'admin/unicrm/communication/deliveries.html',
            context,
        )

    STATUS_META = [
        ('scheduled', _('Scheduled'), '#94a3b8', '#111827'),
        ('sent', _('Sent'), '#2563eb', '#ffffff'),
        ('opened', _('Opened'), '#d97706', '#ffffff'),
        ('clicked', _('Clicked'), '#f97316', '#ffffff'),
        ('replied', _('Replied'), '#16a34a', '#ffffff'),
        ('unsubscribed', _('Unsubscribed'), '#111827', '#f8fafc'),
        ('bounced', _('Bounced'), '#7f1d1d', '#ffffff'),
        ('failed', _('Failed'), '#b91c1c', '#ffffff'),
    ]

    def _status_meta(self) -> dict[str, dict[str, str]]:
        return {
            key: {
                'label': str(label),
                'color': color,
                'text_color': text_color,
            }
            for key, label, color, text_color in self.STATUS_META
        }

    def communication_card(self, obj):
        obj.refresh_status_summary(commit=False)
        summary = obj.status_summary or {}
        summary['communication_id'] = obj.pk  # Pass ID for _chart_segments
        base_url = reverse('admin:unicrm_communication_deliveries', args=[obj.pk])
        data = self._chart_segments(summary, base_url)
        data_json = json.dumps(data, default=str)
        total = int(summary.get('total', 0) or 0)
        change_url = reverse('admin:unicrm_communication_change', args=[obj.pk])

        title_text = str(obj)
        status_label = obj.get_status_display()
        status_badge = format_html(
            '<span class="comm-status-card__status comm-status-card__status--{status}">{label}</span>',
            status=obj.status,
            label=status_label,
        )

        segment_name = obj.segment.name if obj.segment else _('No segment')
        channel_name = str(obj.channel) if obj.channel else _('No channel')
        if obj.segment:
            audience_size = getattr(obj.segment, '_communication_contact_count', None)
            if audience_size is None:
                try:
                    audience_size = obj.segment.apply().count()
                except Exception:  # pragma: no cover - defensive
                    audience_size = 0
                setattr(obj.segment, '_communication_contact_count', audience_size)
        else:
            audience_size = 0
        count_label = ngettext('%(count)s contact', '%(count)s contacts', audience_size) % {'count': audience_size}
        audience_line = format_html(
            '{}: {} · {} ({})',
            _('Audience'),
            segment_name,
            channel_name,
            count_label,
        )

        if obj.scheduled_for:
            scheduled_dt = timezone.localtime(obj.scheduled_for)
            scheduled_value = formats.date_format(scheduled_dt, 'DATETIME_FORMAT')
        else:
            scheduled_value = _('Not scheduled')
        scheduled_line = format_html('{}: {}', _('Scheduled for'), scheduled_value)

        return format_html(
            '<div class="comm-status-card" data-chart="{}" data-total="{}" data-empty-label="{}">'
            '<div class="comm-status-card__header">'
            '<a href="{}" class="comm-status-card__title">{}</a>'
            '</div>'
            '<div class="comm-status-card__chart">'
            '<div class="comm-status-card__pie" role="img" aria-label="{}"></div>'
            '<ul class="comm-status-card__legend"></ul>'
            '</div>'
            '<div class="comm-status-card__footer">'
            '<span class="comm-status-card__meta-item">{}</span>'
            '<span class="comm-status-card__meta-item">{}</span>'
            '{}'
            '</div>'
            '</div>',
            data_json,
            total,
            _('No deliveries yet'),
            change_url,
            title_text,
            _('Delivery breakdown'),
            audience_line,
            scheduled_line,
            status_badge,
        )

    communication_card.short_description = _('Communication')
    communication_card.admin_order_field = 'created_at'

    def _chart_segments(self, summary: dict, base_url: str) -> list[dict]:
        # Use same bucketing logic as deliveries page for consistency
        communication_id = summary.get('communication_id') or getattr(self, '_current_obj_id', None)
        if communication_id:
            communication = self.model.objects.get(pk=communication_id)
        else:
            # Fallback: find communication from URL or context
            import re
            match = re.search(r'/(\d+)/', base_url)
            if match:
                communication = self.model.objects.get(pk=int(match.group(1)))
            else:
                # Last resort: use old math (shouldn't happen)
                return self._chart_segments_old_math(summary, base_url)
        
        deliveries = communication.messages.select_related('message')
        bucket_counts = {'scheduled': 0, 'sent': 0, 'opened': 0, 'clicked': 0, 'replied': 0, 'bounced': 0, 'failed': 0}

        for delivery in deliveries:
            bucket = self._delivery_bucket(delivery)
            bucket_counts.setdefault(bucket, 0)
            bucket_counts[bucket] += 1

        segments: list[dict] = []
        for key, label, color, text_color in self.STATUS_META:
            count = bucket_counts.get(key, 0)
            segments.append({
                'key': key,
                'label': str(label),
                'count': count,
                'url': f'{base_url}?status={key}',
                'color': color,
                'textColor': text_color,
            })
        return segments

    def _delivery_bucket(self, delivery: models.CommunicationMessage) -> str:
        metadata = delivery.metadata or {}
        meta_status = (metadata.get('status') or '').lower()
        if meta_status == 'unsubscribed':
            return 'unsubscribed'
        if delivery.has_received_reply:
            return 'replied'

        status = (delivery.status or '').lower() or meta_status
        if not status:
            status = 'sent' if delivery.message_id else 'scheduled'

        if status == 'bounced':
            return 'bounced'
        if status == 'failed':
            return 'failed'
        if status == 'skipped':
            return 'failed'

        message = delivery.message
        if message:
            if getattr(message, 'bounced', False):
                return 'bounced'
            if getattr(message, 'link_clicked', False) or getattr(message, 'clicked_links', None):
                if getattr(message, 'clicked_links', []):
                    return 'clicked'
            if getattr(message, 'opened', False) or getattr(message, 'seen', False):
                return 'opened'
            if getattr(message, 'sent', False):
                return 'sent'

        if status == 'sent':
            return 'sent'

        return 'scheduled'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'channel':
            from unicom.models import Channel
            kwargs['queryset'] = Channel.objects.filter(platform='Email', active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
        form_class = super().get_form(request, obj, **kwargs)
        
        # Create a wrapper that passes the user to the form
        class FormWithUser(form_class):
            def __init__(self, *args, **kwargs):
                kwargs['user'] = request.user
                super().__init__(*args, **kwargs)
        
        FormWithUser.Media = type('Media', (), {
            'css': {'all': ('admin/css/forms.css',)},
            'js': (
                'unicom/js/tinymce_init.js',
            )
        })
        return FormWithUser

    def get_changeform_initial_data(self, request):
        # Set initiated_by to current user for new objects
        return {'initiated_by': request.user}

    def save_model(self, request, obj, form, change):
        # Ensure initiated_by is set to current user if not already set
        if not change and not obj.initiated_by:
            obj.initiated_by = request.user
        super().save_model(request, obj, form, change)

    def render_change_form(self, request, context, *args, **kwargs):
        context['tinymce_api_key'] = getattr(settings, 'UNICOM_TINYMCE_API_KEY', None)
        obj = context.get('original')
        if obj and obj.pk:
            context['deliveries_view_url'] = reverse('admin:unicrm_communication_deliveries', args=[obj.pk])
        return super().render_change_form(request, context, *args, **kwargs)

    def audience_info(self, obj):
        channel = obj.channel if obj.channel else _('No channel')
        return format_html(
            '<strong>{}</strong><br><small>{}</small>',
            obj.segment.name if obj.segment else _('No segment'),
            channel,
        )

    audience_info.short_description = _('Audience')
    audience_info.admin_order_field = 'segment__name'

    class Media:
        css = {'all': ('unicrm/css/communication_status_chart.css',)}
        js = ('unicrm/js/communication_status_chart.js',)

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'content':
            kwargs['widget'] = forms.Textarea(attrs={'class': 'tinymce', 'data-tinymce': 'true'})
        return super().formfield_for_dbfield(db_field, **kwargs)

    def display_title(self, obj):
        return obj.display_title

    display_title.short_description = _('Title')

    def status_summary_pretty(self, obj):
        obj.refresh_status_summary(commit=False)
        summary = json.dumps(obj.status_summary or {}, indent=2, default=str)
        return format_html('<pre style="white-space:pre-wrap;">{}</pre>', summary)

    status_summary_pretty.short_description = _('Aggregated status')


@admin.register(models.CommunicationMessage)
class CommunicationMessageAdmin(admin.ModelAdmin):
    list_display = ('communication', 'contact', 'message', 'derived_status', 'created_at')
    search_fields = ('communication__subject_template', 'communication__content', 'contact__email', 'message__id')
    autocomplete_fields = ('communication', 'contact', 'message')
    readonly_fields = ('created_at', 'updated_at', 'derived_status')

    def derived_status(self, obj):
        return obj.message_status()

    derived_status.short_description = _('Message status')
