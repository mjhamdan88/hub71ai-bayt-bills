import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application

django_asgi_application = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from unicom.consumers import WebChatConsumer

websocket_urlpatterns = [
    path("ws/unicom/webchat/<str:chat_id>/", WebChatConsumer.as_asgi()),
]

application = ProtocolTypeRouter({
    "http": django_asgi_application,
    "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})
