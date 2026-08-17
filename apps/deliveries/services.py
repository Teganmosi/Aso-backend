import uuid
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.deliveries.models import Delivery, DeliveryStatus


def generate_tracking_number() -> str:
    """
    Generate a unique tracking number for a delivery.
    Format: ASO-DEL-YYYYMMDD-XXXXXX
    """
    from apps.deliveries.models import Delivery
    date_str = timezone.now().strftime('%Y%m%d')

    while True:
        random_hex = uuid.uuid4().hex[:6].upper()
        tracking_number = f"ASO-DEL-{date_str}-{random_hex}"
        if not Delivery.objects.filter(tracking_number=tracking_number).exists():
            return tracking_number


def create_delivery_for_order(order, carrier_name: str = 'MANUAL_DISPATCH', dispatch_notes: str = None) -> Delivery:
    """
    Generates tracking number and creates Delivery record for the given order.
    """
    from apps.orders.models import Order

    tracking_number = generate_tracking_number()

    delivery = Delivery.objects.create(
        order=order,
        tracking_number=tracking_number,
        carrier_name=carrier_name,
        dispatch_notes=dispatch_notes,
    )

    return delivery


def update_delivery_status(delivery: Delivery, new_status: str, notes: str = None) -> Delivery:
    """
    Updates delivery status and synchronizes order.order_status in lockstep.
    Status mapping:
        PICKED_UP       -> Order.status = PICKED_UP
        IN_TRANSIT      -> Order.status = OUT_FOR_DELIVERY
        DELIVERED       -> Order.status = DELIVERED and delivered_at is set
    """
    from apps.orders.models import OrderStatus

    status_mapping = {
        DeliveryStatus.PICKED_UP: OrderStatus.PICKED_UP,
        DeliveryStatus.IN_TRANSIT: OrderStatus.OUT_FOR_DELIVERY,
        DeliveryStatus.DELIVERED: OrderStatus.DELIVERED,
    }

    if new_status not in dict(DeliveryStatus.choices).keys():
        raise ValidationError({"detail": f"Invalid delivery status: {new_status}"})

    with transaction.atomic():
        delivery = Delivery.objects.select_for_update().get(id=delivery.id)

        # Set timing based on status
        now = timezone.now()
        if new_status == DeliveryStatus.PICKED_UP:
            delivery.picked_up_at = now
        elif new_status == DeliveryStatus.IN_TRANSIT:
            delivery.dispatched_at = now
        elif new_status == DeliveryStatus.DELIVERED:
            delivery.delivered_at = now

        delivery.status = new_status
        if notes is not None:
            delivery.dispatch_notes = notes
        delivery.save(update_fields=['status', 'picked_up_at', 'dispatched_at', 'delivered_at', 'dispatch_notes', 'updated_at'])

        # Synchronize order status in lockstep
        order = delivery.order
        if new_status in status_mapping:
            order.order_status = status_mapping[new_status]
            order.save(update_fields=['order_status', 'updated_at'])

    return delivery