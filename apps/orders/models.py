from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.common.models import UUIDModel
from apps.vendors.models import VendorProfile
from apps.products.models import ProductVariant


class OrderStatus(models.TextChoices):
    PENDING_PAYMENT = 'PENDING_PAYMENT', 'Pending Payment'
    PAID = 'PAID', 'Paid'
    VENDOR_ACCEPTED = 'VENDOR_ACCEPTED', 'Vendor Accepted'
    PREPARING = 'PREPARING', 'Preparing'
    READY_FOR_PICKUP = 'READY_FOR_PICKUP', 'Ready for Pickup'
    PICKED_UP = 'PICKED_UP', 'Picked Up'
    OUT_FOR_DELIVERY = 'OUT_FOR_DELIVERY', 'Out for Delivery'
    DELIVERED = 'DELIVERED', 'Delivered'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'
    REFUNDED = 'REFUNDED', 'Refunded'
    DISPUTED = 'DISPUTED', 'Disputed'


class Order(UUIDModel):
    """
    Master order entity created from customer cart with locked stock reservation.
    """
    order_number = models.CharField(max_length=50, unique=True, db_index=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='orders'
    )
    vendor = models.ForeignKey(
        VendorProfile,
        on_delete=models.PROTECT,
        related_name='orders'
    )
    order_status = models.CharField(
        max_length=30,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING_PAYMENT,
        db_index=True
    )
    subtotal_kobo = models.PositiveBigIntegerField()
    delivery_fee_kobo = models.PositiveBigIntegerField(default=0)
    total_amount_kobo = models.PositiveBigIntegerField()
    payment_expires_at = models.DateTimeField(db_index=True)
    vendor_accept_due_by = models.DateTimeField(null=True, blank=True, db_index=True)
    vendor_accepted_at = models.DateTimeField(null=True, blank=True)
    prepared_at = models.DateTimeField(null=True, blank=True)
    ready_for_pickup_at = models.DateTimeField(null=True, blank=True)
    shipping_address_snapshot = models.JSONField(
        help_text="Immutable JSON snapshot of shipping address at time of order creation"
    )
    cancellation_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'orders_order'
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.order_number} ({self.vendor.store_name}) - {self.order_status}"

    @property
    def subtotal_naira(self) -> float:
        return round(self.subtotal_kobo / 100.0, 2)

    @property
    def delivery_fee_naira(self) -> float:
        return round(self.delivery_fee_kobo / 100.0, 2)

    @property
    def total_amount_naira(self) -> float:
        return round(self.total_amount_kobo / 100.0, 2)

    @property
    def is_expired(self) -> bool:
        return (
            self.order_status == OrderStatus.PENDING_PAYMENT and
            self.payment_expires_at <= timezone.now()
        )


class OrderItem(UUIDModel):
    """
    Snapshotted product item line within an order.
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_items'
    )
    product_title_snapshot = models.CharField(max_length=255)
    variant_size_snapshot = models.CharField(max_length=50)
    variant_color_snapshot = models.CharField(max_length=50, null=True, blank=True)
    sku_snapshot = models.CharField(max_length=100)
    custom_measurements = models.JSONField(default=dict, blank=True, help_text="Immutable bespoke measurements snapshot")
    unit_price_kobo = models.PositiveBigIntegerField()
    quantity = models.PositiveIntegerField()
    total_price_kobo = models.PositiveBigIntegerField()

    class Meta:
        db_table = 'orders_orderitem'
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.quantity}x {self.product_title_snapshot} ({self.variant_size_snapshot}) in Order #{self.order.order_number}"

    @property
    def unit_price_naira(self) -> float:
        return round(self.unit_price_kobo / 100.0, 2)

    @property
    def total_price_naira(self) -> float:
        return round(self.total_price_kobo / 100.0, 2)


class MessageType(models.TextChoices):
    TEXT = 'TEXT', 'Text'
    ACTION_REQUEST = 'ACTION_REQUEST', 'Action Request'
    ACTION_RESOLVED = 'ACTION_RESOLVED', 'Action Resolved'
    SYSTEM_AUDIT = 'SYSTEM_AUDIT', 'System Audit'


class OrderMessage(UUIDModel):
    """
    In-app order workspace communication between customer and designer
    governed by Aso Escrow protection and anti-bypass security filters.
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='messages',
        db_index=True
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='sent_order_messages'
    )
    message_type = models.CharField(
        max_length=30,
        choices=MessageType.choices,
        default=MessageType.TEXT,
        db_index=True
    )
    content = models.TextField(help_text="Sanitized public message text displayed in chat")
    original_content = models.TextField(help_text="Unredacted original text for Trust & Safety audits")
    is_masked = models.BooleanField(default=False, db_index=True, help_text="True if anti-bypass shield intervened")
    mask_reason = models.CharField(max_length=100, null=True, blank=True)
    mask_tier = models.CharField(max_length=20, null=True, blank=True, help_text="HEURISTIC or LLM_NEMOTRON")
    
    # 1-Tap Tailor Actions
    action_type = models.CharField(max_length=50, null=True, blank=True, help_text="e.g. RECHECK_MEASUREMENT")
    action_payload = models.JSONField(null=True, blank=True, default=dict)
    
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'orders_ordermessage'
        verbose_name = 'Order Message'
        verbose_name_plural = 'Order Messages'
        ordering = ['created_at']

    def __str__(self):
        return f"Message by {self.sender.email} on Order #{self.order.order_number} ({self.message_type})"
