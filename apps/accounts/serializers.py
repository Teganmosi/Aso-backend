from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from apps.common.nigeria import normalize_phone, phone_variants
from .models import User, CustomerProfile, Address


PHONE_FORMAT_MESSAGE = 'Enter a Nigerian mobile number, e.g. 08012345678.'


def clean_phone(value, exclude_user=None):
    """Normalises to +234…, rejects non-Nigerian numbers and numbers already on another account."""
    value = str(value or '').strip()
    if not value:
        return ''
    normalized = normalize_phone(value)
    if not normalized:
        raise serializers.ValidationError(PHONE_FORMAT_MESSAGE)
    taken = User.objects.filter(phone_number__in=phone_variants(normalized))
    if exclude_user is not None:
        taken = taken.exclude(pk=exclude_user.pk)
    if taken.exists():
        raise serializers.ValidationError('This phone number is already on another Aso account.')
    return normalized


class UserSerializer(serializers.ModelSerializer):
    is_vendor = serializers.SerializerMethodField()
    vendor_profile = serializers.SerializerMethodField()
    email_verified = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'email_verified', 'first_name', 'last_name', 'phone_number',
            'is_staff', 'is_vendor', 'vendor_profile', 'saved_measurements', 'created_at', 'date_joined'
        ]
        read_only_fields = ['id', 'email', 'is_staff', 'created_at', 'date_joined']

    def get_email_verified(self, obj) -> bool:
        from .verification import verification_required
        return obj.email_verified or not verification_required()

    saved_measurements = serializers.SerializerMethodField()

    def get_saved_measurements(self, obj) -> dict:
        if hasattr(obj, 'customer_profile') and obj.customer_profile.saved_measurements:
            return obj.customer_profile.saved_measurements
        return {}

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
                'has_started_verification': vp.has_started_verification,
                'verification_status': vp.verification_status,
                'verification_rejection_reason': vp.verification_rejection_reason,
                'kyc_tier': vp.kyc_tier,
                'logo_url': vp.logo_url,
                'banner_url': vp.banner_url,
                'has_bank_account': hasattr(vp, 'bank_account'),
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
            raise serializers.ValidationError(
                "An account with this email already exists. Sign in, or use “Forgot password?”."
            )
        return value.lower()

    def validate_phone_number(self, value):
        return clean_phone(value)

    def validate(self, data):
        # Same rules as a password reset (not just "8 characters"): rejects "password123",
        # all-digit passwords and ones too close to the person's name or email.
        candidate = User(email=data.get('email', ''), first_name=data.get('first_name', ''),
                         last_name=data.get('last_name', ''))
        try:
            validate_password(data.get('password', ''), candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)})
        return data


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
            raise serializers.ValidationError("That email and password don’t match. Check them, or use “Forgot password?”.")
        if not user.is_active:
            raise serializers.ValidationError("This account has been switched off. Contact support@asomarketplace.com.ng.")

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
