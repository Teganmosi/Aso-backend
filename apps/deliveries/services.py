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


def _flat_fee_kobo(is_interstate: bool) -> int:
    from django.conf import settings
    naira = getattr(settings, 'DELIVERY_FLAT_FEE_INTERSTATE_NAIRA' if is_interstate
                    else 'DELIVERY_FLAT_FEE_SAME_STATE_NAIRA', 0) or 0
    return int(round(float(naira) * 100))


def quote_delivery(address, vendor=None) -> dict:
    """
    The delivery fee for sending an order from `vendor` to `address`.

    Used by the checkout quote AND by order creation, so the shopper is charged exactly what
    they were shown. Order of preference: live Dellyman quote, then the flat fee set in
    DELIVERY_FLAT_FEE_SAME_STATE_NAIRA / DELIVERY_FLAT_FEE_INTERSTATE_NAIRA, then 0
    (delivery included: Aso pays the courier).
    """
    from apps.common.nigeria import normalize_state, same_state

    vendor_city = (getattr(vendor, 'city', '') or 'Lagos').strip()
    vendor_state = normalize_state(getattr(vendor, 'state', '')) or 'Lagos'
    workshop = (getattr(vendor, 'workshop_address', '') or '').strip()
    # Never quote from a made-up street: without a workshop address, quote city to city.
    pickup_addr = ", ".join(p for p in (workshop, vendor_city, vendor_state, "Nigeria") if p)

    dest_state = normalize_state(address.state) or 'Lagos'
    street = address.street_address
    if address.landmark:
        street = f"{street} (Near {address.landmark})"
    dest_addr = f"{street}, {address.city}, {dest_state}, Nigeria"
    is_interstate = not same_state(dest_state, vendor_state)
    eta = "Interstate delivery (2 to 3 days)" if is_interstate else "Same-day or next-day delivery"

    def result(fee_kobo, live, carrier="Dellyman Logistics", message=None):
        out = {
            'has_live_quote': live,
            'delivery_fee_kobo': fee_kobo,
            'delivery_fee_naira': round(fee_kobo / 100, 2) if fee_kobo else None,
            'eta': eta,
            'carrier': carrier,
            'is_interstate': is_interstate,
        }
        if message:
            out['message'] = message
        return out

    if dellyman_client.api_key:
        try:
            if is_interstate:
                res = dellyman_client.get_interstate_quote(
                    pickup_state=vendor_state, pickup_city=vendor_city, pickup_address=pickup_addr,
                    delivery_state=dest_state, delivery_city=address.city or dest_state, delivery_address=dest_addr,
                )
                fare, carrier = res.get('TotalPrice') or res.get('PayableAmount'), res.get('Name')
            else:
                res = dellyman_client.get_quotes(pickup_address=pickup_addr, delivery_address=dest_addr)
                companies = res.get('Companies') or []
                fare = (companies[0].get('TotalPrice') or companies[0].get('PayableAmount')) if companies else None
                carrier = companies[0].get('Name') if companies else None
            if fare and float(fare) > 0:
                return result(int(round(float(fare) * 100)), True, carrier or "Dellyman Logistics")
        except Exception as exc:  # network / API errors fall through to the flat fee
            logger.warning("Delivery quote failed: %s", exc)

    flat = _flat_fee_kobo(is_interstate)
    if flat:
        return result(flat, False, message="Standard delivery fee.")
    return result(0, False, message="Delivery is included. The courier is booked when your piece is ready.")


def create_delivery_for_order(order, carrier_name: str = 'DELLYMAN', dispatch_notes: str = None) -> Delivery:
    """
    Automated Dellyman booking and digital package waybill generation when order is ready for pickup.
    """
    tracking_number = generate_tracking_number()

    # Extract vendor studio address
    vendor = order.vendor
    pickup_name = vendor.store_name
    pickup_phone = getattr(vendor.user, 'phone_number', '08000000000')
    pickup_address = getattr(vendor, 'workshop_address', None) or f"{getattr(vendor, 'city', 'Ikeja')}, {getattr(vendor, 'state', 'Lagos')}, Nigeria"
    if not ('nigeria' in pickup_address.lower()):
        pickup_address += ", Nigeria"
    pickup_landmark = getattr(vendor, 'landmark', None) or 'N/A'

    # Extract destination customer address
    ship_snap = order.shipping_address_snapshot or {}
    dest_name = ship_snap.get('full_name') or f"{order.customer.first_name} {order.customer.last_name}".strip() or "Customer"
    dest_phone = ship_snap.get('phone_number') or "08000000000"
    street = ship_snap.get('street_address', '')
    city = ship_snap.get('city', 'Lagos')
    state = ship_snap.get('state', 'Lagos')
    dest_address = f"{street}, {city}, {state}, Nigeria".strip(', ')
    dest_landmark = ship_snap.get('landmark', '') or 'N/A'

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
            weight_kg=2.0,
            pickup_landmark=pickup_landmark,
            delivery_landmark=dest_landmark
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

    if not dellyman_order_id:
        # No rider was booked: tell the Aso team to book one by hand, never pretend otherwise.
        from apps.common.notifications import send_manual_courier_request
        send_manual_courier_request(order, pickup_address, pickup_phone, dest_address, dest_phone)

    # Post the dispatch status into the order chat.
    try:
        from apps.orders.models import OrderMessage, MessageType
        track_display = dellyman_tracking_id or tracking_number
        if dellyman_order_id:
            content = f"Courier booked with Dellyman (tracking #{track_display}). A rider will come to the studio for pickup."
        else:
            content = "The piece is ready. The Aso team is booking a rider and will confirm the pickup time with the studio."
        OrderMessage.objects.create(
            order=order,
            sender=order.vendor.user,
            message_type=MessageType.SYSTEM_AUDIT,
            content=content,
            original_content=content,
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
