import re
from rest_framework import serializers
from apps.common.media_storage import is_data_uri
from .models import VendorProfile, BankAccount


def _reject_inline_image(value):
    """Logos and banners must be uploaded files, never inline base64 (it bloats every vendor response)."""
    if is_data_uri(value):
        raise serializers.ValidationError(
            "Upload the image first (POST /api/v1/media/upload/) and save the returned URL."
        )
    return value

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


class CompactVendorSerializer(serializers.ModelSerializer):
    """
    Ultra-lightweight vendor serializer for catalog cards, cart items, reviews, and order listings.
    Zero N+1 queries. Zero embedded preview image overhead.
    """
    class Meta:
        model = VendorProfile
        fields = [
            'id', 'store_name', 'slug', 'city', 'state',
            'logo_url', 'is_verified', 'average_rating', 'review_count'
        ]
        read_only_fields = fields


class PublicVendorProfileSerializer(serializers.ModelSerializer):
    """
    Public storefront serializer with real product aggregates (count, starting price, preview images).
    Strict data boundary: ZERO private KYC (NIN/CAC), workshop address, landmark, or bank account fields exposed.
    """
    product_count = serializers.SerializerMethodField()
    starting_price_naira = serializers.SerializerMethodField()
    preview_images = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()
    whatsapp_phone = serializers.SerializerMethodField()
    lead_designer_name = serializers.SerializerMethodField()
    has_started_verification = serializers.SerializerMethodField()

    class Meta:
        model = VendorProfile
        fields = [
            'id', 'store_name', 'slug', 'description', 'logo_url',
            'banner_url', 'city', 'state', 'status', 'is_verified',
            'has_started_verification',
            'instagram_handle', 'whatsapp_phone', 'lead_designer_name',
            'average_rating', 'review_count', 'product_count',
            'starting_price_naira', 'preview_images', 'categories',
            'created_at'
        ]
        read_only_fields = fields

    def get_product_count(self, obj) -> int:
        if hasattr(obj, 'annotated_product_count'):
            return obj.annotated_product_count
        return obj.products.filter(status='PUBLISHED', is_active=True).count()

    def get_starting_price_naira(self, obj):
        if hasattr(obj, 'annotated_starting_price') and obj.annotated_starting_price is not None:
            return round(obj.annotated_starting_price / 100.0, 2)
        lowest = obj.products.filter(status='PUBLISHED', is_active=True).order_by('base_price_kobo').first()
        if lowest:
            return lowest.base_price_naira
        return None

    def get_preview_images(self, obj) -> list:
        images = []
        prods = obj.products.filter(status='PUBLISHED', is_active=True).prefetch_related('media')[:3]
        for p in prods:
            media_list = list(p.media.all())
            primary = next((m for m in media_list if m.is_primary), None) or (media_list[0] if media_list else None)
            if primary and primary.url:
                images.append(primary.url)
        return images

    def get_categories(self, obj) -> list:
        cats = obj.products.filter(status='PUBLISHED', is_active=True).values_list('category__name', flat=True)
        return sorted(list(set(cats)))

    def get_has_started_verification(self, obj) -> bool:
        return obj.has_started_verification

    def get_whatsapp_phone(self, obj) -> str | None:
        return None

    def get_lead_designer_name(self, obj) -> str:
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}".strip()
        return ''


class VendorProfileSerializer(serializers.ModelSerializer):
    """
    Private vendor profile serializer for Designer Studio including bank details, workshop address and KYC proof.
    """
    bank_account = BankAccountSerializer(read_only=True)
    lead_designer_name = serializers.SerializerMethodField()
    phone_number = serializers.CharField(source='user.phone_number', read_only=True)
    has_started_verification = serializers.BooleanField(read_only=True)

    class Meta:
        model = VendorProfile
        fields = [
            'id', 'store_name', 'slug', 'description', 'logo_url',
            'banner_url', 'city', 'state', 'status', 'kyc_tier', 'is_verified',
            'has_started_verification', 'verification_status', 'verification_submitted_at',
            'verification_rejection_reason',
            'instagram_handle', 'workshop_address', 'landmark',
            'nin_number', 'cac_number', 'average_rating', 'review_count',
            'lead_designer_name', 'phone_number',
            'bank_account', 'created_at'
        ]
        read_only_fields = ['id', 'slug', 'status', 'kyc_tier', 'is_verified', 'average_rating', 'review_count', 'created_at',
                            'verification_status', 'verification_submitted_at', 'verification_rejection_reason']

    def validate_logo_url(self, value):
        return _reject_inline_image(value)

    def validate_banner_url(self, value):
        return _reject_inline_image(value)

    def validate_nin_number(self, value):
        value = (value or '').strip()
        if value and not (value.isdigit() and len(value) == 11):
            raise serializers.ValidationError("NIN must be exactly 11 digits.")
        return value or None

    def validate_cac_number(self, value):
        value = (value or '').strip().upper()
        if value and not re.fullmatch(r'(RC|BN|IT)[\s-]?\d{4,9}', value):
            raise serializers.ValidationError("CAC number should look like RC123456, BN1234567 or IT12345.")
        return value or None

    def get_lead_designer_name(self, obj) -> str:
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}".strip()
        return ''


class VendorRegistrationSerializer(serializers.Serializer):
    store_name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100)

    # Optional Verification & Logistics Pickup Fields
    instagram_handle = serializers.CharField(max_length=100, required=False, allow_blank=True)
    workshop_address = serializers.CharField(required=False, allow_blank=True)
    landmark = serializers.CharField(max_length=255, required=False, allow_blank=True)
    nin_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    cac_number = serializers.CharField(max_length=50, required=False, allow_blank=True)

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

    def validate_nin_number(self, value):
        if value:
            if not value.isdigit() or len(value) != 11:
                raise serializers.ValidationError("NIN number must consist of exactly 11 numeric digits.")
        return value

    def validate_cac_number(self, value):
        value = (value or '').strip().upper()
        if value and not re.fullmatch(r'(RC|BN|IT)[\s-]?\d{4,9}', value):
            raise serializers.ValidationError("CAC number should look like RC123456, BN1234567 or IT12345.")
        return value

    def validate(self, data):
        bank_fields = ['account_name', 'account_number', 'bank_name', 'bank_code']
        provided = [f for f in bank_fields if f in data and data[f]]

        if provided and len(provided) != 4:
            raise serializers.ValidationError(
                "If bank details are provided, all four fields (account_name, account_number, bank_name, bank_code) must be provided."
            )
        return data
