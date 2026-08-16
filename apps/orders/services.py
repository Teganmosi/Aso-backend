import uuid
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.cart.models import Cart
from apps.products.models import ProductVariant
from apps.orders.models import Order, OrderItem, OrderStatus


def create_order_from_cart(user, address) -> Order:
    """
    Creates an Order from customer's active cart with pessimistic inventory locking (select_for_update).
    Snapshots shipping address and variant pricing, sets 30m expiration timer, and clears cart.
    """
    with transaction.atomic():
        try:
            cart = Cart.objects.select_for_update().select_related('vendor').get(user=user)
        except Cart.DoesNotExist:
            raise ValidationError({'detail': 'Cart does not exist.'})

        cart_items = list(cart.items.select_related('variant', 'variant__product').order_by('variant_id'))
        if not cart_items:
            raise ValidationError({'detail': 'Your cart is empty.'})

        if not cart.vendor:
            raise ValidationError({'detail': 'Cart vendor is invalid.'})

        # Snapshot address
        address_snapshot = {
            'id': str(address.id),
            'full_name': address.full_name,
            'phone_number': address.phone_number,
            'street_address': address.street_address,
            'city': address.city,
            'state': address.state,
            'landmark': address.landmark or ''
        }

        # Lock variants in deterministic order to prevent deadlocks
        variant_ids = [item.variant_id for item in cart_items]
        variants_qs = ProductVariant.objects.select_for_update().filter(id__in=variant_ids)
        variants_dict = {v.id: v for v in variants_qs}

        # Validate inventory stock availability
        for item in cart_items:
            variant = variants_dict.get(item.variant_id)
            if not variant or not variant.is_active:
                raise ValidationError({
                    'detail': f"Product variant ({item.variant_id}) is no longer available."
                })
            if variant.stock_quantity < item.quantity:
                raise ValidationError({
                    'detail': f"Insufficient stock for {variant.product.title} ({variant.size}). Available stock: {variant.stock_quantity}, requested: {item.quantity}."
                })

        # Atomically decrement stock
        for item in cart_items:
            variant = variants_dict[item.variant_id]
            variant.stock_quantity -= item.quantity
            variant.save(update_fields=['stock_quantity', 'updated_at'])

        subtotal_kobo = sum(item.total_price_kobo for item in cart_items)
        delivery_fee_kobo = 0  # Can be dynamically computed in future sprints
        total_amount_kobo = subtotal_kobo + delivery_fee_kobo

        # Generate unique order number (e.g. ASO-20260816-A1B2C3)
        date_str = timezone.now().strftime('%Y%m%d')
        base_hex = uuid.uuid4().hex[:6].upper()
        order_number = f"ASO-{date_str}-{base_hex}"

        counter = 1
        while Order.objects.filter(order_number=order_number).exists():
            base_hex = uuid.uuid4().hex[:6].upper()
            order_number = f"ASO-{date_str}-{base_hex}-{counter}"
            counter += 1

        payment_expires_at = timezone.now() + timedelta(minutes=30)

        # Create Order
        order = Order.objects.create(
            order_number=order_number,
            customer=user,
            vendor=cart.vendor,
            order_status=OrderStatus.PENDING_PAYMENT,
            subtotal_kobo=subtotal_kobo,
            delivery_fee_kobo=delivery_fee_kobo,
            total_amount_kobo=total_amount_kobo,
            payment_expires_at=payment_expires_at,
            shipping_address_snapshot=address_snapshot
        )

        # Create OrderItems
        order_items = []
        for item in cart_items:
            variant = variants_dict[item.variant_id]
            order_items.append(OrderItem(
                order=order,
                variant=variant,
                product_title_snapshot=variant.product.title,
                variant_size_snapshot=variant.size,
                variant_color_snapshot=variant.color,
                sku_snapshot=variant.sku,
                unit_price_kobo=item.unit_price_kobo,
                quantity=item.quantity,
                total_price_kobo=item.total_price_kobo
            ))
        OrderItem.objects.bulk_create(order_items)

        # Clear cart and reset vendor
        cart.items.all().delete()
        cart.vendor = None
        cart.save(update_fields=['vendor', 'updated_at'])

        return order


def cancel_expired_orders() -> int:
    """
    Cancels unconfirmed PENDING_PAYMENT orders exceeding the 30-minute window
    and restores reserved stock to product variants.
    """
    expired_order_ids = list(
        Order.objects.filter(
            order_status=OrderStatus.PENDING_PAYMENT,
            payment_expires_at__lte=timezone.now()
        ).values_list('id', flat=True)
    )

    cancelled_count = 0
    for order_id in expired_order_ids:
        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(id=order_id)
            except Order.DoesNotExist:
                continue

            # TOCTOU Guard: Re-verify status under DB row lock in case a concurrent webhook marked it PAID
            if order.order_status != OrderStatus.PENDING_PAYMENT:
                continue

            # Restore variant stock
            items = list(order.items.select_related('variant').all())
            for item in items:
                if item.variant:
                    variant = ProductVariant.objects.select_for_update().get(id=item.variant.id)
                    variant.stock_quantity += item.quantity
                    variant.save(update_fields=['stock_quantity', 'updated_at'])

            order.order_status = OrderStatus.CANCELLED
            order.cancellation_reason = "Payment reservation window expired (30m timeout)"
            order.save(update_fields=['order_status', 'cancellation_reason', 'updated_at'])
            cancelled_count += 1

    return cancelled_count
