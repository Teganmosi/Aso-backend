from django.db import models
from apps.common.models import UUIDModel
from apps.vendors.models import VendorProfile, BankAccount
from apps.orders.models import Order


class LedgerEntryType(models.TextChoices):
    EARNING_PENDING = 'EARNING_PENDING', 'Pending Earning'
    EARNING_RELEASE_TO_AVAILABLE = 'EARNING_RELEASE_TO_AVAILABLE', 'Earning Released to Available'
    PAYOUT_RESERVE = 'PAYOUT_RESERVE', 'Payout Reserved'
    PAYOUT_SUCCESS = 'PAYOUT_SUCCESS', 'Payout Successful'
    PAYOUT_FAILED = 'PAYOUT_FAILED', 'Payout Failed'
    REFUND = 'REFUND', 'Refunded / Cancelled'


class PayoutStatus(models.TextChoices):
    AVAILABLE = 'AVAILABLE', 'Available'
    PAYOUT_RESERVED = 'PAYOUT_RESERVED', 'Payout Reserved'
    PROCESSING = 'PROCESSING', 'Processing'
    SUCCESSFUL = 'SUCCESSFUL', 'Successful'
    FAILED = 'FAILED', 'Failed'


class VendorBalance(UUIDModel):
    """
    Materialized view of a vendor's balance components.
    Updated atomically via transactions on LedgerEntry creation.
    """
    vendor = models.OneToOneField(VendorProfile, on_delete=models.CASCADE, related_name='payout_balance')
    pending_balance_kobo = models.PositiveBigIntegerField(default=0)
    available_balance_kobo = models.PositiveBigIntegerField(default=0)
    reserved_balance_kobo = models.PositiveBigIntegerField(default=0)

    class Meta:
        db_table = 'payouts_vendorbalance'
        verbose_name = 'Vendor Balance'
        verbose_name_plural = 'Vendor Balances'

    def __str__(self):
        return f"{self.vendor.store_name} - Pending: {self.pending_balance_kobo}, Available: {self.available_balance_kobo}"


class LedgerEntry(UUIDModel):
    """
    Immutable single-entry financial ledger of all credit/debit movements.
    Acts as the source of truth for all vendor balances.
    """
    vendor = models.ForeignKey(VendorProfile, on_delete=models.PROTECT, related_name='ledger_entries')
    amount_kobo = models.BigIntegerField()
    entry_type = models.CharField(max_length=50, choices=LedgerEntryType.choices)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='ledger_entries')
    payout_request = models.ForeignKey('PayoutRequest', on_delete=models.SET_NULL, null=True, blank=True, related_name='ledger_entries')

    class Meta:
        db_table = 'payouts_ledgerentry'
        verbose_name = 'Ledger Entry'
        verbose_name_plural = 'Ledger Entries'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.vendor.store_name} - {self.entry_type}: {self.amount_kobo} Kobo"


class PayoutRequest(UUIDModel):
    """
    Vendor withdrawal/payout request state machine.
    """
    vendor = models.ForeignKey(VendorProfile, on_delete=models.PROTECT, related_name='payout_requests')
    amount_kobo = models.PositiveBigIntegerField()
    status = models.CharField(max_length=50, choices=PayoutStatus.choices, default=PayoutStatus.PAYOUT_RESERVED)
    reference = models.CharField(max_length=100, unique=True, db_index=True)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name='payout_requests')
    transfer_code = models.CharField(max_length=100, null=True, blank=True)
    failure_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'payouts_payoutrequest'
        verbose_name = 'Payout Request'
        verbose_name_plural = 'Payout Requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"Payout #{self.reference} for {self.vendor.store_name} - {self.status}"
