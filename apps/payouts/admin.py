from django.contrib import admin, messages
from .models import VendorBalance, LedgerEntry, PayoutRequest, PayoutStatus
from .services import process_payout, fail_payout


@admin.action(description='✓ Approve & send selected payouts via Paystack')
def approve_and_send_payouts(modeladmin, request, queryset):
    sent, skipped = 0, 0
    for payout in queryset.select_related('vendor', 'bank_account'):
        if payout.status != PayoutStatus.PAYOUT_RESERVED or not payout.vendor.is_verified:
            skipped += 1
            continue
        process_payout(payout)
        sent += 1
    modeladmin.message_user(request, f"{sent} payout(s) sent for transfer.")
    if skipped:
        modeladmin.message_user(
            request, f"{skipped} skipped (not awaiting approval, or designer not verified).", level=messages.WARNING
        )


@admin.action(description='✗ Reject selected payouts and return funds to designer balance')
def reject_payouts(modeladmin, request, queryset):
    count = 0
    for payout in queryset.filter(status=PayoutStatus.PAYOUT_RESERVED):
        fail_payout(payout, f"Rejected by Aso admin ({request.user.email})")
        count += 1
    modeladmin.message_user(request, f"{count} payout(s) rejected; funds returned to available balance.")


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
    actions = [approve_and_send_payouts, reject_payouts]
    search_fields = ('reference', 'vendor__store_name', 'transfer_code')
    readonly_fields = ('created_at', 'updated_at')
