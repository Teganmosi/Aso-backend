from django.contrib import admin, messages
from django.utils.html import format_html
from apps.common.admin_display import badge, naira
from .models import VendorBalance, LedgerEntry, LedgerEntryType, PayoutRequest, PayoutStatus
from .services import process_payout, fail_payout


@admin.action(description='✓ Approve & send selected payouts (check the bank details first)')
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
    list_display = ('vendor', 'on_hold', 'available', 'being_paid_out', 'updated_at')
    search_fields = ('vendor__store_name', 'vendor__user__email')
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('vendor',)

    @admin.display(description='On hold (until delivery)', ordering='pending_balance_kobo')
    def on_hold(self, obj):
        return naira(obj.pending_balance_kobo)

    @admin.display(description='Available to withdraw', ordering='available_balance_kobo')
    def available(self, obj):
        return naira(obj.available_balance_kobo)

    @admin.display(description='Withdrawal in progress', ordering='reserved_balance_kobo')
    def being_paid_out(self, obj):
        return naira(obj.reserved_balance_kobo)


# Ledger amounts are stored positive; the entry type says which way the money moved.
_LEDGER_SIGN = {
    LedgerEntryType.EARNING_PENDING: ('+', 'Order paid (on hold)'),
    LedgerEntryType.EARNING_RELEASE_TO_AVAILABLE: ('', 'Released to available'),
    LedgerEntryType.PAYOUT_RESERVE: ('−', 'Withdrawal requested'),
    LedgerEntryType.PAYOUT_SUCCESS: ('', 'Sent to bank'),
    LedgerEntryType.PAYOUT_FAILED: ('+', 'Withdrawal failed, returned'),
    LedgerEntryType.REFUND: ('−', 'Order cancelled, earning removed'),
}


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'vendor', 'what_happened', 'amount', 'order', 'payout_request')
    list_filter = ('entry_type', 'created_at')
    search_fields = ('vendor__store_name', 'order__order_number', 'payout_request__reference')
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('vendor', 'order', 'payout_request')
    date_hierarchy = 'created_at'

    @admin.display(description='What happened', ordering='entry_type')
    def what_happened(self, obj):
        return _LEDGER_SIGN.get(obj.entry_type, ('', obj.get_entry_type_display()))[1]

    @admin.display(description='Amount', ordering='amount_kobo')
    def amount(self, obj):
        sign = _LEDGER_SIGN.get(obj.entry_type, ('', ''))[0]
        return f'{sign}{naira(abs(obj.amount_kobo))}'


@admin.register(PayoutRequest)
class PayoutRequestAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'vendor', 'amount', 'pay_to', 'designer_verified', 'status_badge', 'reference')
    list_filter = ('status', 'created_at')
    actions = [approve_and_send_payouts, reject_payouts]
    search_fields = ('reference', 'vendor__store_name', 'transfer_code', 'bank_account__account_number')
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('vendor', 'bank_account')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    @admin.display(description='Amount', ordering='amount_kobo')
    def amount(self, obj):
        return naira(obj.amount_kobo)

    @admin.display(description='Pay to (check before approving)')
    def pay_to(self, obj):
        bank = obj.bank_account
        if not bank:
            return '—'
        return format_html('{}<br><small>{} · {} · code {}</small>',
                           bank.account_name, bank.bank_name, bank.account_number, bank.bank_code or '—')

    @admin.display(description='Identity verified', boolean=True)
    def designer_verified(self, obj):
        return obj.vendor.is_verified

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        return badge(obj.status, obj.get_status_display())
