import hmac
import hashlib
from django.db import models
from django.conf import settings
from apps.common.models import TimeStampedModel, UUIDModel
from apps.orders.models import Order, OrderStatus


class PaymentProvider(UUIDModel):
    """
    Payment provider configuration (Paystack as default).
    Inherits UUIDModel for consistency with other apps.
    """
    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    secret_key = models.CharField(max_length=255)
    public_key = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'payments_paymentprovider'
        verbose_name = 'Payment Provider'
        verbose_name_plural = 'Payment Providers'

    def __str__(self):
        return f"{self.name} ({self.display_name})"


class PaymentRequest(UUIDModel):
    """
    Represents a payment initialization request to a payment provider.
    Inherits UUIDModel for consistency with other apps.
    """
    class ProviderChoices(models.TextChoices):
        PAYSTACK = 'PAYSTACK', 'Paystack'

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='payment_requests'
    )
    provider = models.CharField(max_length=20, choices=ProviderChoices.choices, default=ProviderChoices.PAYSTACK)
    reference = models.CharField(max_length=128, unique=True, db_index=True, null=True, blank=True)
    authorization_url = models.URLField(max_length=500, null=True, blank=True)
    amount_kobo = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default='NGN')
    status = models.CharField(max_length=20, default='PENDING')

    class Meta:
        db_table = 'payments_paymentrequest'
        verbose_name = 'Payment Request'
        verbose_name_plural = 'Payment Requests'

    def __str__(self):
        return f"Payment Request {self.reference} for Order {self.order.order_number}"


class PaymentWebhookLog(UUIDModel):
    """
    Immutable log of all Paystack webhook events for idempotency and auditing.
    """
    class EventChoices(models.TextChoices):
        CHARGE_SUCCESS = 'charge.success', 'Charge Success'
        CHARGE_FAILED = 'charge.failed', 'Charge Failed'
        CHARGE_REVERSED = 'charge.reversed', 'Charge Reversed'
        TRANSFER_INITIATED = 'transfer.initiated', 'Transfer Initiated'
        TRANSFER_COMPLETED = 'transfer.completed', 'Transfer Completed'
        TRANSFER_FAILED = 'transfer.failed', 'Transfer Failed'

    # Changed from unique=True on reference alone to unique_together below
    reference = models.CharField(max_length=128, db_index=True)
    event = models.CharField(max_length=30, choices=EventChoices.choices)

    payload = models.JSONField()
    signature_verified = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_webhook_logs'
    )

    class Meta:
        db_table = 'payments_paymentwebhooklog'
        verbose_name = 'Payment Webhook Log'
        verbose_name_plural = 'Payment Webhook Logs'
        # Unique together on (reference, event) to allow multiple events per reference
        # (e.g., charge.success followed by charge.reversed for the same payment)
        unique_together = ('reference', 'event')

    def __str__(self):
        return f"Webhook {self.event} for reference {self.reference}"