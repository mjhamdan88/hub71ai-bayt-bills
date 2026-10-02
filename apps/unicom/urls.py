from django.urls import path
from unicom.views.telegram_webhook import telegram_webhook
from unicom.views.whatsapp_webhook import whatsapp_webhook
from unicom.views.email_tracking import tracking_pixel, link_click
from .views.message_template import MessageTemplateListView, populate_message_template
from unicom.views.inline_image import serve_inline_image
from unicom.views.inline_image import serve_template_inline_image
from unicom.views.chat_history_view import message_as_llm_chat
from unicom.views.webchat_views import (
    send_webchat_message_api,
    get_webchat_messages_api,
    list_webchat_chats_api,
    update_webchat_chat_api,
    delete_webchat_chat_api,
    handle_webchat_button_click,
)
from unicom.views.webchat_demo_view import webchat_demo_view

urlpatterns = [
    path('telegram/<int:bot_id>', telegram_webhook),
    path('whatsapp', whatsapp_webhook),
    path('e/p/<uuid:tracking_id>/', tracking_pixel, name='e_px'),
    path('e/l/<uuid:tracking_id>/<int:link_index>/', link_click, name='e_lc'),
    path('api/message-templates/', MessageTemplateListView.as_view(), name='message_templates'),
    path('api/message-templates/populate/', populate_message_template, name='populate_message_template'),
    path('api/message/<str:message_id>/as_llm_chat/', message_as_llm_chat, name='message_as_llm_chat'),
    path('i/<str:shortid>/', serve_inline_image, name='inline_image'),
    path('t/<str:shortid>/', serve_template_inline_image, name='template_inline_image'),
    # WebChat API endpoints
    path('webchat/send/', send_webchat_message_api, name='webchat_send'),
    path('webchat/messages/', get_webchat_messages_api, name='webchat_messages'),
    path('webchat/chats/', list_webchat_chats_api, name='webchat_chats'),
    path('webchat/chat/<str:chat_id>/', update_webchat_chat_api, name='webchat_update_chat'),
    path('webchat/chat/<str:chat_id>/delete/', delete_webchat_chat_api, name='webchat_delete_chat'),
    path('webchat/button-click/', handle_webchat_button_click, name='webchat_button_click'),
    # WebChat demo page
    path('webchat/demo/', webchat_demo_view, name='webchat_demo'),
]
