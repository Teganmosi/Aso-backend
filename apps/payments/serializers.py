from rest_framework import serializers
from .models import PaymentRequest, PaymentWebhookLog


class PaymentRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for payment request creation and detail view.
    """
    order_number = serializers.CharField(source='order.order_number', read_only=True)

    class Meta:
        model = PaymentRequest
        fields = [
            'id',
            'order',
            'order_number',
            'provider',
            'reference',
            'authorization_url',
            'amount_kobo',
            'currency',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['reference', 'authorization_url', 'created_at', 'updated_at']


class PaymentWebhookLogSerializer(serializers.ModelSerializer):
    """
    Serializer for payment webhook log entries.
    """
    class Meta:
        model = PaymentWebhookLog
        fields = [
            'id',
            'reference',
            'event',
            'payload',
            'signature_verified',
            'processed',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['reference', 'payload', 'signature_verified', 'processed', 'created_at', 'updated_at']