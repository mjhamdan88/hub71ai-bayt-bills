"""
WebChat Demo View
Simple view to demonstrate the WebChat component
"""
from django.shortcuts import render
from django.http import Http404
from django.conf import settings


def webchat_demo_view(request):
    """
    Render the WebChat demo page.
    Only available when DEBUG=True.
    No authentication required - works for both guest and authenticated users.
    """
    # Only allow access in DEBUG mode
    if not settings.DEBUG:
        raise Http404("Demo page is only available in DEBUG mode")

    return render(request, 'unicom/webchat_demo.html')
