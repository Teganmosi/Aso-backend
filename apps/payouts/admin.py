from django.contrib import admin
from .models import VendorBalance, LedgerEntry, PayoutRequest


@admin.register(VendorBalance)
class VendorBalanceAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'pending_balance_kobo', 'available_balance_kobo', 'reserved_balance_kobo', 'updated_at')
    search_fields = ('vendor__store_name', 'vendor__user__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'entry_type', 'amount_kobo', 'order', 'payout_request', 'created_at')
    list_filter = ('entry_type', 'created_at')
    search_fields = ('vendor__store_name', 'order__order_number', 'payout_request__reference')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(PayoutRequest)
class PayoutRequestAdmin(admin.ModelAdmin):
    list_display = ('reference', 'vendor', 'amount_kobo', 'status', 'transfer_code', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('reference', 'vendor__store_name', 'transfer_code')
    readonly_fields = ('created_at', 'updated_at')
