import os
from django.conf import settings
from urllib.parse import urlparse

def get_public_origin():
    return getattr(settings, "DJANGO_PUBLIC_ORIGIN", os.environ.get("DJANGO_PUBLIC_ORIGIN", "http://localhost:8000"))

def get_public_domain():
    """
    Extract the domain from the public origin URL.
    Example: For http://localhost:8000 returns localhost
    """
    origin = get_public_origin()
    return urlparse(origin).hostname
