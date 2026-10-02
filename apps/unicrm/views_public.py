from __future__ import annotations

from typing import Any, Dict

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from django.core import signing

from unicrm.models import Communication, Contact, MailingList, Subscription, UnsubscribeAll
from unicrm.services.unsubscribe_links import UNSUBSCRIBE_SALT


def _load_payload(token: str) -> Dict[str, Any]:
    try:
        return signing.loads(token, salt=UNSUBSCRIBE_SALT)
    except Exception:
        raise Http404("Invalid or expired token.")


def _resolve_contact(payload: Dict[str, Any]) -> Contact:
    contact_id = payload.get('contact_id')
    if not contact_id:
        raise Http404("Contact not found.")
    try:
        return Contact.objects.get(pk=contact_id)
    except Contact.DoesNotExist:
        raise Http404("Contact not found.")


def _resolve_mailing_list(payload: Dict[str, Any]) -> MailingList | None:
    mailing_list_id = payload.get('mailing_list_id')
    mailing_list_slug = payload.get('mailing_list_slug')
    if mailing_list_id:
        try:
            return MailingList.objects.get(pk=mailing_list_id)
        except MailingList.DoesNotExist:
            return None
    if mailing_list_slug:
        try:
            return MailingList.objects.get(slug=mailing_list_slug)
        except MailingList.DoesNotExist:
            return None
    return None


def _resolve_communication(payload: Dict[str, Any]) -> Communication | None:
    communication_id = payload.get('communication_id')
    if not communication_id:
        return None
    try:
        return Communication.objects.get(pk=communication_id)
    except Communication.DoesNotExist:
        return None


class UnsubscribeView(View):
    template_name = 'unicrm/unsubscribe.html'

    def get(self, request: HttpRequest) -> HttpResponse:
        token = request.GET.get('token') or ''
        payload = _load_payload(token)
        contact = _resolve_contact(payload)
        mailing_list = _resolve_mailing_list(payload)
        communication = _resolve_communication(payload)

        status = None
        # Pre-compute status for already-unsubscribed contacts
        if UnsubscribeAll.objects.filter(contact=contact).exists():
            status = 'unsubscribed_all'
        elif mailing_list:
            try:
                sub = Subscription.objects.get(contact=contact, mailing_list=mailing_list)
                if sub.unsubscribed_at:
                    status = 'unsubscribed_list'
            except Subscription.DoesNotExist:
                pass

        context = {
            'contact': contact,
            'mailing_list': mailing_list,
            'communication': communication,
            'token': token,
            'status': status,
            'show_form': status is None,
        }
        return render(request, self.template_name, context)

    def post(self, request: HttpRequest) -> HttpResponse:
        token = request.POST.get('token') or ''
        payload = _load_payload(token)
        contact = _resolve_contact(payload)
        mailing_list = _resolve_mailing_list(payload)
        communication = _resolve_communication(payload)

        action = request.POST.get('action') or ''
        feedback = (request.POST.get('feedback') or '').strip()
        now = timezone.now()

        status = None
        show_form = True
        deliveries = []
        if communication:
            deliveries = list(communication.messages.filter(contact=contact))
        touched_communications = set()

        if action == 'unsubscribe_list' and mailing_list:
            subscription, _ = Subscription.objects.get_or_create(contact=contact, mailing_list=mailing_list)
            if subscription.unsubscribed_at is None:
                subscription.unsubscribed_at = now
                if feedback and not subscription.unsubscribe_feedback:
                    subscription.unsubscribe_feedback = feedback
            subscription.save(update_fields=['unsubscribed_at', 'unsubscribe_feedback', 'updated_at'])
            status = 'unsubscribed_list'
            show_form = False

            # Mark matching deliveries as unsubscribed
            for delivery in deliveries:
                metadata = delivery.metadata or {}
                metadata['status'] = 'unsubscribed'
                delivery.metadata = metadata
                delivery.status = 'failed'
                delivery.save(update_fields=['metadata', 'status', 'updated_at'])
                touched_communications.add(delivery.communication_id)
        else:
            unsub, created = UnsubscribeAll.objects.get_or_create(
                contact=contact,
                defaults={
                    'communication': communication,
                    'feedback': feedback,
                    'unsubscribed_at': now,
                },
            )
            if not created and feedback and not unsub.feedback:
                unsub.feedback = feedback
                unsub.save(update_fields=['feedback', 'updated_at'])

            for sub in Subscription.objects.filter(contact=contact, unsubscribed_at__isnull=True):
                sub.unsubscribed_at = now
                if feedback and not sub.unsubscribe_feedback:
                    sub.unsubscribe_feedback = feedback
                sub.save(update_fields=['unsubscribed_at', 'unsubscribe_feedback', 'updated_at'])
            status = 'unsubscribed_all'
            show_form = False

            # Mark all deliveries for this contact as unsubscribed
            for delivery in contact.communications.all():
                metadata = delivery.metadata or {}
                metadata['status'] = 'unsubscribed'
                delivery.metadata = metadata
                delivery.status = 'failed'
                delivery.save(update_fields=['metadata', 'status', 'updated_at'])
                touched_communications.add(delivery.communication_id)

        # Refresh status summaries for affected communications
        from unicrm.models import Communication
        if touched_communications:
            for comm in Communication.objects.filter(pk__in=touched_communications):
                comm.refresh_status_summary()

        context = {
            'contact': contact,
            'mailing_list': mailing_list,
            'communication': communication,
            'token': token,
            'status': status,
            'feedback': feedback,
            'show_form': show_form,
        }
        return render(request, self.template_name, context)
