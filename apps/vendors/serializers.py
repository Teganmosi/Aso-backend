from rest_framework import serializers
from .models import VendorProfile, BankAccount

class BankAccountSerializer(serializers.ModelSerializer):
    account_number = serializers.CharField(max_length=10, min_length=10)

    class Meta:
        model = BankAccount
        fields = ['id', 'account_name', 'account_number', 'bank_name', 'bank_code', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_account_number(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Account number must consist of 10 numeric digits.")
        return value


class PublicVendorProfileSerializer(serializers.ModelSerializer):
    """
    Public storefront serializer excluding sensitive bank information.
    """
    class Meta:
        model = VendorProfile
        fields = [
            'id', 'store_name', 'slug', 'description', 'logo_url',
            'banner_url', 'city', 'state', 'is_verified',
            'average_rating', 'review_count', 'created_at'
        ]
        read_only_fields = fields


class VendorProfileSerializer(serializers.ModelSerializer):
    """
    Private vendor profile serializer including bank details (for vendor owner dashboard).
    """
    bank_account = BankAccountSerializer(read_only=True)

    class Meta:
        model = VendorProfile
        fields = [
            'id', 'store_name', 'slug', 'description', 'logo_url',
            'banner_url', 'city', 'state', 'status', 'is_verified',
            'average_rating', 'review_count', 'bank_account', 'created_at'
        ]
        read_only_fields = ['id', 'slug', 'status', 'is_verified', 'average_rating', 'review_count', 'created_at']


class VendorRegistrationSerializer(serializers.Serializer):
    store_name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100)

    # Optional initial bank account fields
    account_name = serializers.CharField(max_length=255, required=False)
    account_number = serializers.CharField(max_length=10, min_length=10, required=False)
    bank_name = serializers.CharField(max_length=100, required=False)
    bank_code = serializers.CharField(max_length=20, required=False)

    def validate_store_name(self, value):
        if VendorProfile.objects.filter(store_name__iexact=value).exists():
            raise serializers.ValidationError("A store with this name already exists.")
        return value

    def validate_account_number(self, value):
        if value and not value.isdigit():
            raise serializers.ValidationError("Account number must consist of 10 numeric digits.")
        return value

    def validate(self, data):
        bank_fields = ['account_name', 'account_number', 'bank_name', 'bank_code']
        provided = [f for f in bank_fields if f in data and data[f]]

        if provided and len(provided) != 4:
            raise serializers.ValidationError(
                "If bank details are provided, all four fields (account_name, account_number, bank_name, bank_code) must be provided."
            )
        return data

