from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User, CustomerProfile, Address

class UserSerializer(serializers.ModelSerializer):
    is_vendor = serializers.SerializerMethodField()
    vendor_profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone_number',
            'is_staff', 'is_vendor', 'vendor_profile', 'created_at', 'date_joined'
        ]
        read_only_fields = ['id', 'email', 'is_staff', 'created_at', 'date_joined']

    def get_is_vendor(self, obj) -> bool:
        return hasattr(obj, 'vendor_profile') and obj.vendor_profile.status == 'APPROVED'

    def get_vendor_profile(self, obj):
        if hasattr(obj, 'vendor_profile'):
            vp = obj.vendor_profile
            return {
                'id': str(vp.id),
                'store_name': vp.store_name,
                'slug': vp.slug,
                'status': vp.status,
                'is_verified': vp.is_verified,
            }
        return None


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return value.lower()

    def validate_phone_number(self, value):
        if value and User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("A user with this phone number already exists.")
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email', '').lower()
        password = data.get('password', '')

        if not email or not password:
            raise serializers.ValidationError("Both email and password are required.")

        user = authenticate(username=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("User account is disabled.")

        data['user'] = user
        return data


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            'id', 'full_name', 'phone_number', 'street_address',
            'city', 'state', 'landmark', 'is_default', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
