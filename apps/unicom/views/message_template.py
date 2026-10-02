from django.http import JsonResponse
from django.views.generic import View
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json

from unicom.models import MessageTemplate, Channel

"""
This view is an API endpoint used to serve message templates to TinyMCE.
It allows for filtering templates by channel.
"""

@method_decorator(user_passes_test(lambda u: u.is_superuser), name='dispatch')
class MessageTemplateListView(View):
    """View to serve message templates to TinyMCE."""
    
    def get(self, request, *args, **kwargs):
        # Get channel_id from query params if provided
        channel_id = request.GET.get('channel_id')
        
        # Base queryset
        templates = MessageTemplate.objects.all()
        
        # Filter by channel if specified
        if channel_id:
            try:
                channel = Channel.objects.get(id=channel_id)
                templates = templates.filter(Q(channels=channel) | Q(channels__isnull=True))
            except Channel.DoesNotExist:
                templates = templates.filter(channels__isnull=True)
        
        # Convert to TinyMCE template format
        tinymce_templates = []
        for template in templates:
            tinymce_templates.append({
                'id': template.id,
                'title': template.title,
                'description': template.description,
                'content': template.content,
            })
        
        return JsonResponse(tinymce_templates, safe=False)

@csrf_exempt
@require_POST
@user_passes_test(lambda u: u.is_superuser)
def populate_message_template(request):
    """
    API endpoint to populate a message template using AI.
    Expects JSON: {"template_id": <id>, "html_prompt": <html>, "model": <optional_model_name>}
    Returns: {"html": <populated_html>} or {"error": ...}
    """
    try:
        data = json.loads(request.body)
        template_id = data.get("template_id")
        html_prompt = data.get("html_prompt")
        model = data.get("model", "gpt-4o")
        if not template_id or not html_prompt:
            return JsonResponse({"error": "Missing template_id or html_prompt"}, status=400)
        template = MessageTemplate.objects.get(pk=template_id)
        result_html = template.populate(html_prompt, model=model)
        return JsonResponse({"html": result_html})
    except MessageTemplate.DoesNotExist:
        return JsonResponse({"error": "Template not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500) 