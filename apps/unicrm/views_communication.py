from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST

from unicrm.forms import CommunicationComposeForm
from unicrm.models import Communication, CommunicationMessage, Segment, MailingList
from unicrm.services.audience import audience_queryset
from unicom.models import Channel


def staff_required():
    return user_passes_test(lambda u: u.is_staff, login_url='admin:login')


@method_decorator(staff_required(), name='dispatch')
class CommunicationListView(View):
    template_name = 'unicrm/communications/list.html'

    def get(self, request, *args, **kwargs):
        communications = (
            Communication.objects
            .select_related('segment', 'channel', 'initiated_by')
            .order_by('-created_at')
        )
        for communication in communications:
            communication.refresh_status_summary(commit=False)
        return render(request, self.template_name, {'communications': communications})


@method_decorator(staff_required(), name='dispatch')
class CommunicationComposeView(View):
    template_name = 'unicrm/communications/compose.html'

    def get_form(self, request, data=None):
        return CommunicationComposeForm(
            data,
            segment_queryset=Segment.objects.order_by('name'),
            mailing_list_queryset=MailingList.objects.order_by('name'),
            channel_queryset=Channel.objects.filter(active=True, platform='Email').order_by('name'),
        )

    def get(self, request, *args, **kwargs):
        form = self.get_form(request)
        return render(request, self.template_name, self._context(request, form))

    def post(self, request, *args, **kwargs):
        form = self.get_form(request, request.POST)
        if form.is_valid():
            scheduled_at = form.cleaned_schedule_utc or timezone.now()

            communication = Communication.objects.create(
                segment=form.cleaned_data['segment'],
                mailing_list=form.cleaned_data.get('mailing_list') or None,
                channel=form.cleaned_data['channel'],
                initiated_by=request.user if request.user.is_authenticated else None,
                scheduled_for=scheduled_at,
                status='scheduled',
                subject_template=form.cleaned_data['subject_template'] or '',
                content=form.cleaned_data['content'],
                auto_enroll_new_contacts=form.cleaned_data['auto_enroll_new_contacts'],
                follow_up_for=form.cleaned_data.get('follow_up_for') or None,
                skip_antispam_guards=form.cleaned_data.get('skip_antispam_guards') or False,
                exclude_follow_up_siblings=form.cleaned_data.get('exclude_follow_up_siblings', True),
            )

            eligible_contacts = None
            try:
                from unicrm.services.audience import audience_size_and_sample
                eligible_contacts, _ = audience_size_and_sample(
                    communication.segment,
                    communication.mailing_list,
                    communication=communication,
                    apply_guards=False,
                )
            except Exception:
                eligible_contacts = None

            local_dt = form.cleaned_schedule_local
            if local_dt:
                display_time = local_dt.strftime("%Y-%m-%d %H:%M %Z")
                base_message = f'Communication scheduled for {display_time}.'
            else:
                base_message = 'Communication queued to send immediately.'

            if eligible_contacts is not None:
                contact_suffix = 'contact' if eligible_contacts == 1 else 'contacts'
                base_message += f' Deliveries will be generated at send time for {eligible_contacts} {contact_suffix}.'
            else:
                base_message += ' Deliveries will be generated at send time.'

            messages.success(request, base_message)
            return redirect(reverse('admin:unicrm_communication_deliveries', args=[communication.pk]))
        return render(request, self.template_name, self._context(request, form))

    def _context(self, request, form):
        segments = list(form.fields['segment'].queryset)
        segment_counts = {}
        for segment in segments:
            try:
                segment_counts[segment.pk] = segment.apply().count()
            except Exception:
                segment_counts[segment.pk] = 0
        channels = form.fields['channel'].queryset
        mailing_lists = form.fields['mailing_list'].queryset
        previous_communications = Communication.objects.order_by('-created_at')[:200]
        selected_channel = ''
        if 'channel' in form.fields:
            selected_channel = form['channel'].value()
            if not selected_channel:
                initial_channel = form.fields['channel'].initial or form.initial.get('channel')
                if initial_channel:
                    selected_channel = str(initial_channel)
        return {
            'form': form,
            'segments': segments,
            'segment_counts': segment_counts,
            'mailing_lists': mailing_lists,
            'channels': channels,
            'selected_channel': selected_channel,
            'tinymce_api_key': getattr(settings, 'UNICOM_TINYMCE_API_KEY', None),
            'previous_communications': previous_communications,
        }


@staff_member_required
@require_POST
def retry_delivery(request, delivery_id: int):
    """
    Secure endpoint for staff to retry failed deliveries.
    """
    delivery = get_object_or_404(
        CommunicationMessage.objects.select_related('communication', 'contact'),
        pk=delivery_id,
    )
    metadata = delivery.metadata or {}
    meta_status = (metadata.get('status') or '').lower()
    status = (delivery.status or '').lower()
    message = getattr(delivery, 'message', None)
    contact = getattr(delivery, 'contact', None)
    message_bounced = bool(message and getattr(message, 'bounced', False))
    contact_bounced = bool(contact and getattr(contact, 'email_bounced', False))
    allowed_statuses = {'failed', 'bounced'}
    if (
        status not in allowed_statuses
        and meta_status not in allowed_statuses
        and not message_bounced
        and not contact_bounced
    ):
        return JsonResponse(
            {'ok': False, 'error': 'Only failed or bounced deliveries can be retried.'},
            status=400,
        )

    was_bounced = (
        status == 'bounced'
        or meta_status == 'bounced'
        or message_bounced
        or contact_bounced
    )
    metadata.pop('errors', None)
    metadata['status'] = 'scheduled'
    delivery.metadata = metadata
    delivery.status = 'scheduled'
    delivery.scheduled_at = timezone.now()
    delivery.save(update_fields=['metadata', 'status', 'scheduled_at', 'updated_at'])

    if was_bounced:
        message = getattr(delivery, 'message', None)
        if message:
            message.bounced = False
            message.bounce_type = ''
            message.bounce_reason = ''
            message.time_bounced = None
            message.bounce_details = {}
            message.save(update_fields=['bounced', 'bounce_type', 'bounce_reason', 'time_bounced', 'bounce_details'])

        contact = getattr(delivery, 'contact', None)
        if contact and (
            contact.email_bounced
            or contact.email_bounced_at
            or contact.email_bounce_type
        ):
            contact.email_bounced = False
            contact.email_bounced_at = None
            contact.email_bounce_type = ''
            contact.save(update_fields=['email_bounced', 'email_bounced_at', 'email_bounce_type', 'updated_at'])

    return JsonResponse(
        {
            'ok': True,
            'delivery_id': delivery.pk,
            'scheduled_at': delivery.scheduled_at.isoformat(),
        }
    )
