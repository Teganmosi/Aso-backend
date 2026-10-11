import uuid
from django.db import models
from apps.common.models import UUIDModel
from apps.orders.models import Order


class DeliveryStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PICKED_UP = 'PICKED_UP', 'Picked Up'
    IN_TRANSIT = 'IN_TRANSIT', 'In Transit'
    DELIVERED = 'DELIVERED', 'Delivered'
    FAILED_DELIVERY = 'FAILED_DELIVERY', 'Failed Delivery'


class Delivery(UUIDModel):
    """
    Delivery record tracking order fulfillment and dispatch state via Dellyman Logistics.
    """
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name='delivery'
    )
    tracking_number = models.CharField(max_length=100, unique=True, db_index=True)
    carrier_name = models.CharField(max_length=100, default='DELLYMAN')
    status = models.CharField(
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
        max_length=20,
        db_index=True
    )
    
    # Dellyman Specific Fulfillment Identifiers
    dellyman_order_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    dellyman_order_code = models.CharField(max_length=100, null=True, blank=True)
    dellyman_tracking_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    package_label_base64 = models.TextField(null=True, blank=True, help_text="Base64 encoded PDF shipping waybill")
    shipping_cost_kobo = models.PositiveBigIntegerField(default=0)
    rider_name = models.CharField(max_length=150, null=True, blank=True)
    rider_phone = models.CharField(max_length=50, null=True, blank=True)
    delivery_timeline = models.CharField(max_length=50, default='sameDay')
    dellyman_raw_response = models.JSONField(null=True, blank=True, default=dict)

    dispatch_notes = models.TextField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'deliveries_delivery'
        verbose_name = 'Delivery'
        verbose_name_plural = 'Deliveries'
        ordering = ['-dispatched_at']

    def __str__(self):
        tracking = self.dellyman_tracking_id or self.tracking_number
        return f"Delivery {tracking} for Order #{self.order.order_number} - {self.status}"

    @property
    def shipping_cost_naira(self) -> float:
        return round(self.shipping_cost_kobo / 100.0, 2)

    @property
    def has_waybill(self) -> bool:
        return bool(self.package_label_base64)
