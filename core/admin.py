from django.contrib import admin
from .models import Bill, Budget, Payment, Message


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'merchant', 'category', 'amount', 'currency', 'period', 'due', 'paid', 'source')
    list_filter = ('currency', 'paid', 'category', 'source', 'period')
    search_fields = ('owner__username', 'owner__email', 'merchant', 'category')
    autocomplete_fields = ('owner',)
    readonly_fields = ('paid',)
    list_select_related = ('owner',)
    date_hierarchy = 'due'
    ordering = ('-period', 'merchant')
    list_per_page = 50

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'category', 'limit', 'autopay')
    list_filter = ('category', 'autopay')
    search_fields = ('owner__username', 'owner__email', 'category')
    autocomplete_fields = ('owner',)
    list_select_related = ('owner',)


class ReadOnlyHistoryAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(ReadOnlyHistoryAdmin):
    list_display = ('id', 'account', 'merchant', 'amount', 'currency', 'created', 'mode')
    list_filter = ('mode', 'created', 'bill__currency')
    search_fields = ('bill__owner__username', 'bill__owner__email', 'bill__merchant')
    list_select_related = ('bill', 'bill__owner')
    date_hierarchy = 'created'
    ordering = ('-created',)

    @admin.display(ordering='bill__owner__username')
    def account(self, obj):
        return obj.bill.owner.username

    @admin.display(ordering='bill__merchant')
    def merchant(self, obj):
        return obj.bill.merchant

    @admin.display(ordering='bill__amount')
    def amount(self, obj):
        return obj.bill.amount

    @admin.display(ordering='bill__currency')
    def currency(self, obj):
        return obj.bill.currency


@admin.register(Message)
class MessageAdmin(ReadOnlyHistoryAdmin):
    list_display = ('id', 'owner', 'role', 'preview', 'created')
    list_filter = ('role', 'created')
    search_fields = ('owner__username', 'owner__email', 'text')
    list_select_related = ('owner',)
    date_hierarchy = 'created'
    ordering = ('-created',)

    @admin.display(description='Message')
    def preview(self, obj):
        return obj.text[:120]
