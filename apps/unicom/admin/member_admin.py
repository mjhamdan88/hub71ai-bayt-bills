from django.contrib import admin
from ..models import Member, MemberGroup

class MemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'group_list', 'created_at')
    list_filter = ('groups', 'created_at')
    search_fields = ('name', 'email', 'phone')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('allowed_categories',)
    
    def group_list(self, obj):
        return ", ".join([g.name for g in obj.groups.all()])
    group_list.short_description = "Groups"

class MemberGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'member_count', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('members',)

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = "Number of Members" 