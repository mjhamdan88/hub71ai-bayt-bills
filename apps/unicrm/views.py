from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.generic import View
from django.contrib.auth.decorators import user_passes_test

from .models import TemplateVariable


@method_decorator(user_passes_test(lambda u: u.is_superuser), name='dispatch')
class TemplateVariableListView(View):
    """
    Provides TinyMCE with the list of available template variables.
    """

    def get(self, request, *args, **kwargs):
        variables = TemplateVariable.objects.filter(is_active=True).order_by('key')
        payload = [
            {
                'key': variable.key,
                'label': variable.label,
                'description': variable.description,
                'placeholder': f"{{{{ variables.{variable.key} }}}}",
                'sample_values': variable.sample_values(limit=3),
                'path': f"variables.{variable.key}",
            }
            for variable in variables
        ]
        return JsonResponse(payload, safe=False)
