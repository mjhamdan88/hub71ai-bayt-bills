from django.contrib import admin
from ..models import Account, AccountChat

class AccountAdmin(admin.ModelAdmin):
    list_filter = ('platform', )
    search_fields = ('name', )

class AccountChatAdmin(admin.ModelAdmin):
    list_filter = ('account__platform', )
    search_fields = ('account__name', 'chat__name') 