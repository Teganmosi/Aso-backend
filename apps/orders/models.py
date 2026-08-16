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
