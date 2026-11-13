from rest_framework import serializers
from apps.deliveries.models import Delivery, DeliveryStatus


class DeliverySerializer(serializers.ModelSerializer):
    """
    Read serializer for delivery tracking details.
    """
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    # False when the courier API could not book a rider (e.g. no Dellyman key): the Aso team
    # books one by hand, and the studio must not be told a rider is on the way.
    courier_booked = serializers.SerializerMethodField()
    has_waybill = serializers.SerializerMethodField()

    class Meta:
        model = Delivery
        fields = [
            'id',
            'courier_booked',
            'has_waybill',
            'dellyman_tracking_id',
            'rider_name',
            'rider_phone',
            'tracking_number',
            'carrier_name',
            'status',
            'status_display',
            'dispatch_notes',
            'picked_up_at',
            'dispatched_at',
            'delivered_at',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields

    def get_courier_booked(self, obj) -> bool:
        return bool(obj.dellyman_order_id)

    def get_has_waybill(self, obj) -> bool:
        return bool(obj.package_label_base64)


class DeliveryStatusUpdateSerializer(serializers.Serializer):
    """
    Validation serializer for updating delivery status.
    """
    status = serializers.ChoiceField(choices=DeliveryStatus.choices)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_status(self, value):
        """Ensure only valid status transitions are allowed."""
        if not self.instance:
            return value

        current_status = self.instance.status
        if current_status == value:
            return value

        valid_transitions = {
            DeliveryStatus.PENDING: [DeliveryStatus.PICKED_UP, DeliveryStatus.FAILED_DELIVERY],
            DeliveryStatus.PICKED_UP: [DeliveryStatus.IN_TRANSIT, DeliveryStatus.FAILED_DELIVERY],
            DeliveryStatus.IN_TRANSIT: [DeliveryStatus.DELIVERED, DeliveryStatus.FAILED_DELIVERY],
            DeliveryStatus.FAILED_DELIVERY: [DeliveryStatus.PICKED_UP, DeliveryStatus.IN_TRANSIT, DeliveryStatus.DELIVERED],
            DeliveryStatus.DELIVERED: [],  # Terminal state
        }

        allowed_next = valid_transitions.get(current_status, [])
        if value not in allowed_next:
            raise serializers.ValidationError(
                f"Cannot transition delivery status from {current_status} to {value}."
            )

        return value