from rest_framework import serializers
from apps.orders.models import Order, OrderItem
from apps.accounts.models import Address
from apps.vendors.serializers import PublicVendorProfileSerializer


class OrderCreateSerializer(serializers.Serializer):
    """
    Serializer for creating an order from active cart.
    """
    address_id = serializers.UUIDField(required=True)

    def validate_address_id(self, value):
        user = self.context['request'].user
        try:
            address = Address.objects.get(id=value, user=user)
        except Address.DoesNotExist:
            raise serializers.ValidationError("Shipping address not found or does not belong to your account.")
        
        self.context['address'] = address
        return value


class OrderItemSerializer(serializers.ModelSerializer):
    """
    Serializer for order items containing snapshotted product info.
    """
    unit_price_naira = serializers.FloatField(read_only=True)
    total_price_naira = serializers.FloatField(read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            'id',
            'variant_id',
            'product_title_snapshot',
            'variant_size_snapshot',
            'variant_color_snapshot',
            'sku_snapshot',
            'unit_price_kobo',
            'unit_price_naira',
            'quantity',
            'total_price_kobo',
            'total_price_naira',
            'created_at'
        ]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for customer order summary.
    """
    vendor = PublicVendorProfileSerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    subtotal_naira = serializers.FloatField(read_only=True)
    delivery_fee_naira = serializers.FloatField(read_only=True)
    total_amount_naira = serializers.FloatField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    vendor_accept_due_by = serializers.DateTimeField(read_only=True)
    vendor_accepted_at = serializers.DateTimeField(read_only=True)
    prepared_at = serializers.DateTimeField(read_only=True)
    ready_for_pickup_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Order
        fields = [
            'id',
            'order_number',
            'vendor',
            'order_status',
            'subtotal_kobo',
            'subtotal_naira',
            'delivery_fee_kobo',
            'delivery_fee_naira',
            'total_amount_kobo',
            'total_amount_naira',
            'payment_expires_at',
            'is_expired',
            'vendor_accept_due_by',
            'vendor_accepted_at',
            'prepared_at',
            'ready_for_pickup_at',
            'shipping_address_snapshot',
            'cancellation_reason',
            'items',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields


class VendorOrderSerializer(serializers.ModelSerializer):
    """
    Serializer for vendor-facing order details with embedded delivery snapshot.
    """
    items = OrderItemSerializer(many=True, read_only=True)
    delivery = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id',
            'order_number',
            'order_status',
            'vendor_accept_due_by',
            'vendor_accepted_at',
            'prepared_at',
            'ready_for_pickup_at',
            'subtotal_kobo',
            'delivery_fee_kobo',
            'total_amount_kobo',
            'shipping_address_snapshot',
            'cancellation_reason',
            'items',
            'delivery'
        ]

    def get_delivery(self, order):
        """Return delivery snapshot if it exists."""
        delivery = getattr(order, 'delivery', None)
        if delivery:
            from apps.deliveries.serializers import DeliverySerializer
            return DeliverySerializer(delivery).data
        return None
