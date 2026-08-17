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
    Delivery record tracking order fulfillment and dispatch state.
    """
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name='delivery'
    )
    tracking_number = models.CharField(max_length=100, unique=True, db_index=True)
    carrier_name = models.CharField(max_length=100, default='MANUAL_DISPATCH')
    status = models.CharField(
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
        max_length=20,
        db_index=True
    )
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
        return f"Delivery {self.tracking_number} for Order {self.order.order_number} - {self.status}"