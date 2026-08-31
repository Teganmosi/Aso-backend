from decimal import Decimal
from rest_framework import serializers
from .models import VendorBalance, PayoutRequest


class VendorBalanceSerializer(serializers.ModelSerializer):
    pending_balance = serializers.IntegerField(source='pending_balance_kobo')
    available_balance = serializers.IntegerField(source='available_balance_kobo')
    reserved_payout_balance = serializers.IntegerField(source='reserved_balance_kobo')
    
    pending_balance_naira = serializers.SerializerMethodField()
    available_balance_naira = serializers.SerializerMethodField()
    reserved_payout_balance_naira = serializers.SerializerMethodField()

    class Meta:
        model = VendorBalance
        fields = [
            'pending_balance', 
            'available_balance', 
            'reserved_payout_balance',
            'pending_balance_naira', 
            'available_balance_naira', 
            'reserved_payout_balance_naira'
        ]

    def get_pending_balance_naira(self, obj) -> float:
        return round(obj.pending_balance_kobo / 100.0, 2)

    def get_available_balance_naira(self, obj) -> float:
        return round(obj.available_balance_kobo / 100.0, 2)

    def get_reserved_payout_balance_naira(self, obj) -> float:
        return round(obj.reserved_balance_kobo / 100.0, 2)


class PayoutWithdrawalSerializer(serializers.Serializer):
    amount_kobo = serializers.IntegerField(required=False, min_value=1)
    amount = serializers.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=Decimal('0.01'))

    def validate(self, data):
        if 'amount_kobo' not in data and 'amount' not in data:
            raise serializers.ValidationError("Either amount or amount_kobo must be provided.")
        
        # Calculate amount_kobo if only amount is provided
        if 'amount_kobo' not in data and 'amount' in data:
            data['amount_kobo'] = int(data['amount'] * Decimal('100'))
            
        return data


class PayoutRequestSerializer(serializers.ModelSerializer):
    amount_naira = serializers.SerializerMethodField()

    class Meta:
        model = PayoutRequest
        fields = [
            'id', 
            'amount_kobo', 
            'amount_naira',
            'status', 
            'reference', 
            'transfer_code', 
            'failure_reason', 
            'created_at'
        ]
        read_only_fields = fields

    def get_amount_naira(self, obj) -> float:
        return round(obj.amount_kobo / 100.0, 2)
