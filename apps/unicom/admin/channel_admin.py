from django.contrib import admin
from django.db import models
from django.http import JsonResponse, Http404
from django.urls import path, reverse
from django_ace import AceWidget
from ..models import Channel
from ..services.email.backfill import create_backfill_job

class ChannelAdmin(admin.ModelAdmin):
    change_form_template = 'admin/unicom/channel/change_form.html'
    list_filter = ('platform', )
    search_fields = ('name', )
    list_display = ('id', 'name', 'platform', 'active', 'confirmed_webhook_url', 'error')
    
    formfield_overrides = {
        models.JSONField: {'widget': AceWidget(mode='json', theme='twilight', width="100%", height="300px")},
    }

    class Media:
        js = ('unicom/js/channel_config.js',)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ['active', 'confirmed_webhook_url', 'error']
        return super().get_readonly_fields(request, obj)

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.is_staff:
            return qs
        return qs.filter(created_by_id=request.user.id)

    def get_urls(self):
        return [
            path('<path:object_id>/email-backfill/start/', self.admin_site.admin_view(self.start_backfill), name='unicom_channel_backfill_start'),
            path('<path:object_id>/email-backfill/status/', self.admin_site.admin_view(self.backfill_status), name='unicom_channel_backfill_status'),
        ] + super().get_urls()

    def _channel_for_request(self, request, object_id):
        try:
            return self.get_queryset(request).get(pk=object_id)
        except Channel.DoesNotExist as exc:
            raise Http404 from exc

    def start_backfill(self, request, object_id):
        if request.method != 'POST':
            return JsonResponse({'error': 'POST required.'}, status=405)
        channel = self._channel_for_request(request, object_id)
        try:
            job = create_backfill_job(channel)
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=400)
        return JsonResponse(self._job_payload(job), status=202)

    def backfill_status(self, request, object_id):
        channel = self._channel_for_request(request, object_id)
        job = channel.email_backfill_jobs.first()
        return JsonResponse(self._job_payload(job) if job else {'status': 'not_started'})

    @staticmethod
    def _job_payload(job):
        return {
            'id': job.pk,
            'status': job.status,
            'total': job.total_messages,
            'processed': job.processed_messages,
            'imported': job.imported_messages,
            'skipped': job.skipped_messages,
            'failed': job.failed_messages,
            'progress': job.progress_percent,
            'error': job.error,
        }

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        channel = self._channel_for_request(request, object_id)
        if channel.platform == 'Email':
            extra_context.update({
                'email_channel': True,
                'backfill_start_url': reverse('admin:unicom_channel_backfill_start', args=[object_id]),
                'backfill_status_url': reverse('admin:unicom_channel_backfill_status', args=[object_id]),
            })
        return super().change_view(request, object_id, form_url, extra_context)
