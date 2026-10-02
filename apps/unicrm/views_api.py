from __future__ import annotations

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View

from unicrm.services.audience_preview import preview_audience


@method_decorator(staff_member_required, name='dispatch')
class AudiencePreviewView(View):
    def get(self, request):
        segment_id = request.GET.get('segment_id')
        mailing_list_id = request.GET.get('mailing_list_id')

        follow_up_for_id = request.GET.get('follow_up_for')
        exclude_follow_up_siblings_param = request.GET.get('exclude_follow_up_siblings')
        try:
            segment_id_int = int(segment_id) if segment_id else None
        except (TypeError, ValueError):
            segment_id_int = None
        try:
            mailing_list_id_int = int(mailing_list_id) if mailing_list_id else None
        except (TypeError, ValueError):
            mailing_list_id_int = None
        try:
            follow_up_for_id_int = int(follow_up_for_id) if follow_up_for_id else None
        except (TypeError, ValueError):
            follow_up_for_id_int = None
        if exclude_follow_up_siblings_param is not None:
            flag = exclude_follow_up_siblings_param.strip().lower()
            exclude_follow_up_siblings = flag not in {'', '0', 'false', 'off'}
        else:
            exclude_follow_up_siblings = None

        total, sample = preview_audience(
            mailing_list_id_int,
            segment_id_int,
            follow_up_for_id_int,
            exclude_follow_up_siblings=exclude_follow_up_siblings,
        )
        return JsonResponse({'count': total, 'contacts': sample})
