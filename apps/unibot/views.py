from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, Http404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from .models import CredentialSetupSession, EncryptedCredential
from django.utils import timezone
import json

# Create your views here.

@csrf_protect
@require_http_methods(["GET", "POST"])
def credential_setup(request, session_id):
    """Handle the credential setup form"""
    session = get_object_or_404(CredentialSetupSession, id=session_id)
    
    if not session.can_attempt:
        if session.is_expired:
            return render(request, 'unibot/credential_setup_error.html', {
                'error': 'This setup link has expired.',
                'show_contact': True
            })
        elif session.is_completed:
            return render(request, 'unibot/credential_setup_error.html', {
                'error': 'This setup has already been completed.',
                'show_contact': False
            })
        else:
            return render(request, 'unibot/credential_setup_error.html', {
                'error': 'Maximum attempts reached.',
                'show_contact': True
            })

    if request.method == 'POST':
        session.increment_attempts()
        
        # Validate all fields
        errors = {}
        values = {}
        for field_def in session.field_definitions.all():
            value = request.POST.get(f'field_{field_def.key}', '').strip()
            is_valid, error = field_def.validate_value(value)
            if not is_valid:
                errors[field_def.key] = error
            else:
                values[field_def.key] = value

        if errors:
            return render(request, 'unibot/credential_setup_form.html', {
                'session': session,
                'errors': errors,
                'values': values  # Preserve valid values
            })

        # All values are valid, save them
        for key, value in values.items():
            credential, created = EncryptedCredential.objects.get_or_create(
                account=session.account,
                key=key,
            )
            if created or credential.decrypted_value != value:
                credential._value = value
                credential.save()

        session.mark_completed()
        return render(request, 'unibot/credential_setup_success.html')

    return render(request, 'unibot/credential_setup_form.html', {
        'session': session
    })
