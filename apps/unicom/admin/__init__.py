from django.contrib import admin
from ..models import (
    Chat, Account, AccountChat, Channel, Member, MemberGroup, RequestCategory, Request, MessageTemplate, DraftMessage, EmailInlineImage, Update, Message
)
from ..models.message_template import MessageTemplateInlineImage
from .chat_admin import ChatAdmin
from .account_admin import AccountAdmin, AccountChatAdmin
from .channel_admin import ChannelAdmin
from .member_admin import MemberAdmin, MemberGroupAdmin
from .request_admin import RequestCategoryAdmin, RequestAdmin
from .message_template_admin import MessageTemplateAdmin, MessageTemplateInlineImageAdmin
from .draft_message_admin import DraftMessageAdmin
from .email_inline_image_admin import EmailInlineImageAdmin
from .message_admin import MessageAdmin
from .filters import *

admin.site.register(Chat, ChatAdmin)
admin.site.register(Account, AccountAdmin)
admin.site.register(AccountChat, AccountChatAdmin)
admin.site.register(Channel, ChannelAdmin)
admin.site.register(Member, MemberAdmin)
admin.site.register(MemberGroup, MemberGroupAdmin)
admin.site.register(RequestCategory, RequestCategoryAdmin)
admin.site.register(Request, RequestAdmin)
admin.site.register(MessageTemplate, MessageTemplateAdmin)
admin.site.register(MessageTemplateInlineImage, MessageTemplateInlineImageAdmin)
admin.site.register(DraftMessage, DraftMessageAdmin)
admin.site.register(EmailInlineImage, EmailInlineImageAdmin)
admin.site.register(Message, MessageAdmin)
admin.site.register(Update)

# Other admin registrations will be added here as they are modularized. 