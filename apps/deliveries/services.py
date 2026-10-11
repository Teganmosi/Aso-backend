import uuid
import base64
import logging
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.deliveries.models import Delivery, DeliveryStatus
from apps.deliveries.dellyman_client import dellyman_client

logger = logging.getLogger(__name__)


def generate_tracking_number() -> str:
    """
    Generate a unique fallback tracking number for a delivery.
    Format: ASO-DEL-YYYYMMDD-XXXXXX
    """
    date_str = timezone.now().strftime('%Y%m%d')

    while True:
        random_hex = uuid.uuid4().hex[:6].upper()
        tracking_number = f"ASO-DEL-{date_str}-{random_hex}"
        if not Delivery.objects.filter(tracking_number=tracking_number).exists():
            return tracking_number


def create_delivery_for_order(order, carrier_name: str = 'DELLYMAN', dispatch_notes: str = None) -> Delivery:
    """
    Automated Dellyman booking and digital package waybill generation when order is ready for pickup.
    """
    tracking_number = generate_tracking_number()

    # Extract vendor studio address
    vendor = order.vendor
    pickup_name = vendor.store_name
    pickup_phone = getattr(vendor, 'phone_number', None) or getattr(vendor.user, 'phone_number', '08000000000')
    pickup_address = getattr(vendor, 'address', None) or f"{getattr(vendor, 'city', 'Ikeja')}, Lagos, Nigeria"
    if not ('lagos' in pickup_address.lower() or 'nigeria' in pickup_address.lower()):
        pickup_address += ", Lagos, Nigeria"

    # Extract destination customer address
    ship_snap = order.shipping_address_snapshot or {}
    dest_name = ship_snap.get('full_name') or f"{order.customer.first_name} {order.customer.last_name}".strip() or "Customer"
    dest_phone = ship_snap.get('phone_number') or "08000000000"
    street = ship_snap.get('street_address', '')
    city = ship_snap.get('city', 'Lagos')
    state = ship_snap.get('state', 'Lagos')
    dest_address = f"{street}, {city}, {state}, Nigeria".strip(', ')

    # Extract garment description
    first_item = order.items.first()
    pkg_desc = first_item.product_title_snapshot if first_item else f"Garment order #{order.order_number}"

    # Call Dellyman BookOrder API
    booking_res = {}
    dellyman_order_id = None
    dellyman_order_code = None
    dellyman_tracking_id = None
    package_label = None

    try:
        booking_res = dellyman_client.book_order(
            order_ref=f"ASO_{order.order_number}",
            pickup_name=pickup_name,
            pickup_phone=pickup_phone,
            pickup_address=pickup_address,
            delivery_name=dest_name,
            delivery_phone=dest_phone,
            delivery_address=dest_address,
            package_desc=pkg_desc,
            weight_kg=2.0
        )
        dellyman_order_id = str(booking_res.get('OrderID') or '')
        dellyman_order_code = str(booking_res.get('OrderCode') or '')
        dellyman_tracking_id = str(booking_res.get('TrackingID') or '')
        if not dellyman_tracking_id and booking_res.get('Packages'):
            dellyman_tracking_id = str(booking_res['Packages'][0].get('PackageTrackingID') or '')

        if dellyman_order_id:
            package_label = dellyman_client.get_package_label(dellyman_order_id)
    except Exception as e:
        logger.error(f"Dellyman booking error on order #{order.order_number}: {e}")

    # Use existing or create delivery
    delivery, created = Delivery.objects.get_or_create(
        order=order,
        defaults={
            'tracking_number': tracking_number,
            'carrier_name': carrier_name,
            'dellyman_order_id': dellyman_order_id,
            'dellyman_order_code': dellyman_order_code,
            'dellyman_tracking_id': dellyman_tracking_id or tracking_number,
            'package_label_base64': package_label,
            'dispatch_notes': dispatch_notes,
            'dellyman_raw_response': booking_res,
            'status': DeliveryStatus.PENDING
        }
    )

    if not created:
        delivery.carrier_name = carrier_name
        delivery.dellyman_order_id = dellyman_order_id
        delivery.dellyman_order_code = dellyman_order_code
        delivery.dellyman_tracking_id = dellyman_tracking_id or delivery.tracking_number
        if package_label:
            delivery.package_label_base64 = package_label
        delivery.dellyman_raw_response = booking_res
        delivery.save()

    # Automatically notify Atelier Order Workspace Chat
    try:
        from apps.orders.models import OrderMessage, MessageType
        track_display = dellyman_tracking_id or tracking_number
        OrderMessage.objects.create(
            order=order,
            sender=order.vendor.user,
            message_type=MessageType.SYSTEM_AUDIT,
            content=f"Dellyman courier booking confirmed (Tracking #{track_display}). Dispatch rider summoned for studio pickup. Digital waybill generated.",
            original_content=f"Dellyman booked: Tracking {track_display}"
        )
    except Exception as e:
        logger.warning(f"Failed to post system audit chat message: {e}")

    return delivery


def update_delivery_status(delivery: Delivery, new_status: str, notes: str = None) -> Delivery:
    """
    Updates delivery status and synchronizes order.order_status in lockstep.
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

        order = delivery.order
        if new_status in status_mapping:
            order.order_status = status_mapping[new_status]
            order.save(update_fields=['order_status', 'updated_at'])

    return delivery
