import requests
from typing import List, Union
from urllib.parse import urljoin
from django.conf import settings
import re
from unibot.services.tool_exceptions import ToolHandlerError, ToolHandlerWarning


def validate_emails(emails: Union[List[str], str]) -> str:
    """Validates a list of email addresses using Reacher service"""
    
    # Handle both string and array inputs
    if isinstance(emails, str):
        # Split comma-separated string into list
        email_list = [email.strip() for email in re.split(r'[,;\s]+', emails) if email.strip()]
    else:
        email_list = emails
    
    # Get Reacher base URL
    base_url = getattr(settings, 'REACHER_HOSTNAME', None) or \
               getattr(settings, 'REACHER_HOST', None) or \
               getattr(settings, 'REACHER_BASE_URL', None)
    
    if not base_url:
        raise ToolHandlerError("No Reacher API service is configured. Please set REACHER_HOSTNAME, REACHER_HOST, or REACHER_BASE_URL in your settings.")
    
    base_url = base_url.strip()
    if not base_url.startswith(('http://', 'https://')):
        base_url = f'http://{base_url}'
    base_url = base_url.rstrip('/')
    
    endpoint = urljoin(f'{base_url}/', 'v0/check_email')
    results = []
    
    for email in email_list:
        if not email or not email.strip():
            continue
            
        email = email.strip()
        
        try:
            response = requests.post(endpoint, json={'to_email': email}, timeout=120)
            response.raise_for_status()
            data = response.json()
            
            status = str(data.get('is_reachable', 'unknown')).lower()
            
            # Format result
            if status == 'safe':
                results.append(f"✅ {email}: Safe to send")
            elif status == 'risky':
                results.append(f"⚠️ {email}: Risky (may bounce)")
            elif status == 'invalid':
                results.append(f"❌ {email}: Invalid email address")
            else:
                results.append(f"❓ {email}: Unknown status ({status})")
                
        except requests.RequestException as e:
            raise ToolHandlerError(f"Reacher API error: Failed to validate emails. Service may be down or unreachable. Error: {str(e)}")
        except ValueError:
            raise ToolHandlerError("Reacher API error: Service returned invalid response format.")
    
    if not results:
        raise ToolHandlerWarning("No valid email addresses provided for validation.")
    
    return {
        "summary": "Email Validation Results",
        "details": results,
    }


tool_definition = {
    "name": "validate_emails",
    "description": "Validates email addresses using Reacher service to check if they are safe to send to",
    "parameters": {
        "emails": {
            "type": "string",
            "description": "Comma-separated list of email addresses to validate (e.g., 'user1@example.com, user2@example.com')"
        }
    },
    "run": validate_emails
}
