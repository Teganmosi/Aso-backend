from rest_framework import serializers
from apps.products.models import (
    Category,
    Product,
    ProductVariant,
    ProductMedia,
    Review,
    ApprovalStatus,
    ProductStatus,
    MediaType
)
from apps.vendors.serializers import PublicVendorProfileSerializer


class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer for product categories, including nested child categories.
    """
    children = serializers.SerializerMethodField()
    parent_name = serializers.CharField(source='parent.name', read_only=True, default=None)

    class Meta:
        model = Category
        fields = [
            'id',
            'name',
            'slug',
            'parent',
            'parent_name',
            'description',
            'image_url',
            'is_active',
            'display_order',
            'children'
        ]
        read_only_fields = ['id', 'slug', 'children']

    def get_children(self, obj):
        active_children = obj.children.filter(is_active=True)
        if active_children.exists():
            return CategorySerializer(active_children, many=True).data
        return []


class CategorySimpleSerializer(serializers.ModelSerializer):
    """
    Flat category serializer without nested children for embedded product references.
    """
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'image_url']


class ProductVariantSerializer(serializers.ModelSerializer):
    """
    Serializer for product variants (sizes, colors, SKU, stock quantity).
    """
    price_kobo = serializers.IntegerField(read_only=True)
    price_naira = serializers.FloatField(read_only=True)
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            'id',
            'size',
            'color',
            'sku',
            'stock_quantity',
            'price_override_kobo',
            'price_kobo',
            'price_naira',
            'in_stock',
            'is_active',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'sku', 'price_kobo', 'price_naira', 'in_stock', 'created_at', 'updated_at']

    def get_in_stock(self, obj) -> bool:
        return obj.stock_quantity > 0 and obj.is_active

    def validate_stock_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Stock quantity cannot be negative.")
        return value

    def validate_size(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("Size cannot be blank.")
        return str(value).strip()

    def validate_price_override_kobo(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Price override must be greater than 0 Kobo.")
        return value


class ProductMediaSerializer(serializers.ModelSerializer):
    """
    Serializer for product media gallery assets (photos and videos).
    """
    class Meta:
        model = ProductMedia
        fields = [
            'id',
            'media_type',
            'url',
            'thumbnail_url',
            'display_order',
            'is_primary',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def validate_url(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("Media URL cannot be blank.")
        return str(value).strip()


class PresignedUploadUrlRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting an S3/R2 presigned upload URL.
    """
    filename = serializers.CharField(max_length=255)
    file_type = serializers.CharField(max_length=50)

    def validate_filename(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("Filename is required.")
        return str(value).strip()



def generate_default_size_chart(product) -> dict:
    """
    Generates an authentic Nigerian fashion sizing & measurement guide modeled
    after Temu's dual-layer dimensional framework (Body Measurements + Garment Dimensions).
    """
    title_lower = (product.title or '').lower()
    cat_slug = (product.category.slug if getattr(product, 'category', None) else '').lower()
    is_women = any(k in title_lower or k in cat_slug for k in ['women', 'female', 'gown', 'dress', 'iro', 'buba', 'skirt'])

    if is_women:
        return {
            "stretch": "SLIGHT",
            "unit_default": "IN",
            "garment_type": "DRESS_AND_SUIT",
            "body_measurements": [
                { "size": "S", "us_size": "4", "bust": "33.9-35.4", "waist": "26.0-27.6", "hip": "36.2-37.8", "height": "5'3\"-5'5\"", "bust_cm": "86-90", "waist_cm": "66-70", "hip_cm": "92-96", "height_cm": "160-165" },
                { "size": "M", "us_size": "6", "bust": "35.4-37.0", "waist": "27.6-29.1", "hip": "37.8-39.4", "height": "5'5\"-5'7\"", "bust_cm": "90-94", "waist_cm": "70-74", "hip_cm": "96-100", "height_cm": "165-170" },
                { "size": "L", "us_size": "8", "bust": "37.0-39.4", "waist": "29.1-31.5", "hip": "39.4-41.7", "height": "5'6\"-5'8\"", "bust_cm": "94-100", "waist_cm": "74-80", "hip_cm": "100-106", "height_cm": "168-173" },
                { "size": "XL", "us_size": "10", "bust": "39.4-41.7", "waist": "31.5-33.9", "hip": "41.7-44.1", "height": "5'7\"-5'9\"", "bust_cm": "100-106", "waist_cm": "80-86", "hip_cm": "106-112", "height_cm": "170-175" },
                { "size": "XXL", "us_size": "12", "bust": "41.7-44.1", "waist": "33.9-36.2", "hip": "44.1-46.5", "height": "5'7\"-5'10\"", "bust_cm": "106-112", "waist_cm": "86-92", "hip_cm": "112-118", "height_cm": "170-178" }
            ],
            "garment_measurements": {
                "tops": [
                    { "size": "S", "us_size": "4", "shoulder": "15.0", "chest": "37.0", "length": "42.5", "sleeve": "23.6", "shoulder_cm": "38", "chest_cm": "94", "length_cm": "108", "sleeve_cm": "60" },
                    { "size": "M", "us_size": "6", "shoulder": "15.4", "chest": "38.6", "length": "43.3", "sleeve": "24.0", "shoulder_cm": "39", "chest_cm": "98", "length_cm": "110", "sleeve_cm": "61" },
                    { "size": "L", "us_size": "8", "shoulder": "15.7", "chest": "40.9", "length": "44.1", "sleeve": "24.4", "shoulder_cm": "40", "chest_cm": "104", "length_cm": "112", "sleeve_cm": "62" },
                    { "size": "XL", "us_size": "10", "shoulder": "16.1", "chest": "43.3", "length": "44.9", "sleeve": "24.8", "shoulder_cm": "41", "chest_cm": "110", "length_cm": "114", "sleeve_cm": "63" },
                    { "size": "XXL", "us_size": "12", "shoulder": "16.5", "chest": "45.7", "length": "45.7", "sleeve": "25.2", "shoulder_cm": "42", "chest_cm": "116", "length_cm": "116", "sleeve_cm": "64" }
                ],
                "bottoms": [
                    { "size": "S", "us_size": "4", "waist": "27.6", "hip": "38.6", "length": "39.4", "inseam": "29.1", "waist_cm": "70", "hip_cm": "98", "length_cm": "100", "inseam_cm": "74" },
                    { "size": "M", "us_size": "6", "waist": "29.1", "hip": "40.2", "length": "40.2", "inseam": "29.5", "waist_cm": "74", "hip_cm": "102", "length_cm": "102", "inseam_cm": "75" },
                    { "size": "L", "us_size": "8", "waist": "31.5", "hip": "42.5", "length": "40.9", "inseam": "29.9", "waist_cm": "80", "hip_cm": "108", "length_cm": "104", "inseam_cm": "76" },
                    { "size": "XL", "us_size": "10", "waist": "33.9", "hip": "44.9", "length": "41.7", "inseam": "30.3", "waist_cm": "86", "hip_cm": "114", "length_cm": "106", "inseam_cm": "77" },
                    { "size": "XXL", "us_size": "12", "waist": "36.2", "hip": "47.2", "length": "42.5", "inseam": "30.7", "waist_cm": "92", "hip_cm": "120", "length_cm": "108", "inseam_cm": "78" }
                ]
            }
        }

    return {
        "stretch": "NON",
        "unit_default": "IN",
        "garment_type": "TWO_PIECE_SUIT",
        "body_measurements": [
            { "size": "S", "us_size": "36", "bust": "36.2-37.8", "waist": "30.7-32.3", "height": "5'7\"-5'9\"", "bust_cm": "92-96", "waist_cm": "78-82", "height_cm": "170-175" },
            { "size": "M", "us_size": "38", "bust": "37.8-39.4", "waist": "32.3-33.9", "height": "5'9\"-5'11\"", "bust_cm": "96-100", "waist_cm": "82-86", "height_cm": "175-180" },
            { "size": "L", "us_size": "40", "bust": "39.4-41.4", "waist": "33.9-35.9", "height": "5'11\"-6'1\"", "bust_cm": "100-105", "waist_cm": "86-91", "height_cm": "180-185" },
            { "size": "XL", "us_size": "42", "bust": "41.4-43.3", "waist": "35.9-37.8", "height": "6'1\"-6'3\"", "bust_cm": "105-110", "waist_cm": "91-96", "height_cm": "185-190" },
            { "size": "XXL", "us_size": "44", "bust": "43.3-45.3", "waist": "37.8-40.2", "height": "6'1\"-6'3\"", "bust_cm": "110-115", "waist_cm": "96-102", "height_cm": "185-190" }
        ],
        "garment_measurements": {
            "tops": [
                { "size": "S", "us_size": "36", "shoulder": "18.3", "chest": "43.3", "length": "35.5", "sleeve": "25.2", "shoulder_cm": "46.5", "chest_cm": "110", "length_cm": "90", "sleeve_cm": "64" },
                { "size": "M", "us_size": "38", "shoulder": "18.9", "chest": "45.3", "length": "35.9", "sleeve": "25.6", "shoulder_cm": "48", "chest_cm": "115", "length_cm": "91", "sleeve_cm": "65" },
                { "size": "L", "us_size": "40", "shoulder": "19.5", "chest": "47.3", "length": "36.2", "sleeve": "26.0", "shoulder_cm": "49.5", "chest_cm": "120", "length_cm": "92", "sleeve_cm": "66" },
                { "size": "XL", "us_size": "42", "shoulder": "20.1", "chest": "49.3", "length": "36.6", "sleeve": "26.4", "shoulder_cm": "51", "chest_cm": "125", "length_cm": "93", "sleeve_cm": "67" },
                { "size": "XXL", "us_size": "44", "shoulder": "20.7", "chest": "51.2", "length": "37.0", "sleeve": "26.8", "shoulder_cm": "52.5", "chest_cm": "130", "length_cm": "94", "sleeve_cm": "68" }
            ],
            "bottoms": [
                { "size": "S", "us_size": "31", "waist": "28.3", "hip": "42.5", "length": "40.5", "inseam": "28.3", "waist_cm": "72", "hip_cm": "108", "length_cm": "103", "inseam_cm": "72" },
                { "size": "M", "us_size": "32", "waist": "29.9", "hip": "44.5", "length": "40.9", "inseam": "28.3", "waist_cm": "76", "hip_cm": "113", "length_cm": "104", "inseam_cm": "72" },
                { "size": "L", "us_size": "34", "waist": "31.5", "hip": "46.5", "length": "41.3", "inseam": "28.3", "waist_cm": "80", "hip_cm": "118", "length_cm": "105", "inseam_cm": "72" },
                { "size": "XL", "us_size": "36", "waist": "33.1", "hip": "48.4", "length": "41.7", "inseam": "28.3", "waist_cm": "84", "hip_cm": "123", "length_cm": "106", "inseam_cm": "72" },
                { "size": "XXL", "us_size": "38", "waist": "34.6", "hip": "50.4", "length": "42.1", "inseam": "28.3", "waist_cm": "88", "hip_cm": "128", "length_cm": "107", "inseam_cm": "72" }
            ]
        }
    }


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for vendor product creation and editing.
    """
    category_id = serializers.UUIDField(write_only=True)
    base_price_naira = serializers.FloatField(read_only=True)
    sizes = serializers.ListField(child=serializers.CharField(max_length=50), required=False, write_only=True)
    colors = serializers.ListField(child=serializers.CharField(max_length=50), required=False, write_only=True)
    stock_quantity = serializers.IntegerField(required=False, write_only=True)
    size_chart = serializers.JSONField(required=False)

    class Meta:
        model = Product
        fields = [
            'id',
            'title',
            'slug',
            'category_id',
            'description',
            'base_price_kobo',
            'base_price_naira',
            'preparation_time_days',
            'status',
            'approval_status',
            'rejection_reason',
            'sizes',
            'colors',
            'stock_quantity',
            'size_chart',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id',
            'slug',
            'base_price_naira',
            'approval_status',
            'rejection_reason',
            'created_at',
            'updated_at'
        ]

    def validate_category_id(self, value):
        try:
            category = Category.objects.get(id=value, is_active=True)
        except Category.DoesNotExist:
            raise serializers.ValidationError("Category does not exist or is inactive.")
        return value

    def validate_base_price_kobo(self, value):
        if value <= 0:
            raise serializers.ValidationError("Base price must be greater than 0 Kobo.")
        return value

    def validate_preparation_time_days(self, value):
        if value < 1 or value > 90:
            raise serializers.ValidationError("Preparation time must be between 1 and 90 days.")
        return value


class ProductListSerializer(serializers.ModelSerializer):
    """
    Serializer for product catalog listings.
    """
    vendor = PublicVendorProfileSerializer(read_only=True)
    category = CategorySimpleSerializer(read_only=True)
    base_price_naira = serializers.FloatField(read_only=True)
    primary_image_url = serializers.SerializerMethodField()
    available_sizes = serializers.SerializerMethodField()
    size_chart = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id',
            'title',
            'slug',
            'description',
            'base_price_kobo',
            'base_price_naira',
            'preparation_time_days',
            'approval_status',
            'status',
            'is_active',
            'average_rating',
            'review_count',
            'primary_image_url',
            'available_sizes',
            'size_chart',
            'vendor',
            'category',
            'created_at'
        ]

    def get_size_chart(self, obj):
        if obj.size_chart and isinstance(obj.size_chart, dict) and obj.size_chart.get('body_measurements'):
            return obj.size_chart
        return generate_default_size_chart(obj)

    def get_primary_image_url(self, obj):
        media_items = list(obj.media.all())  # uses prefetch cache
        for item in media_items:
            if item.is_primary:
                return item.url
        for item in media_items:
            if item.media_type == MediaType.IMAGE:
                return item.url
        return None

    def get_available_sizes(self, obj):
        # Python-level filtering over the prefetched variants (cache-bound, no extra queries)
        return sorted({
            variant.size for variant in obj.variants.all()
            if variant.is_active and variant.stock_quantity > 0
        })


class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Detailed product serializer including media gallery, variant availability matrix, and Temu-style size chart.
    """
    vendor = PublicVendorProfileSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    base_price_naira = serializers.FloatField(read_only=True)
    primary_image_url = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()
    size_chart = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id',
            'title',
            'slug',
            'description',
            'base_price_kobo',
            'base_price_naira',
            'preparation_time_days',
            'approval_status',
            'status',
            'is_active',
            'rejection_reason',
            'average_rating',
            'review_count',
            'primary_image_url',
            'media',
            'variants',
            'size_chart',
            'vendor',
            'category',
            'created_at',
            'updated_at'
        ]

    def get_size_chart(self, obj):
        if obj.size_chart and isinstance(obj.size_chart, dict) and obj.size_chart.get('body_measurements'):
            return obj.size_chart
        return generate_default_size_chart(obj)

    def get_media(self, obj):
        # Full gallery (model Meta ordering: display_order, -is_primary, created_at)
        return ProductMediaSerializer(list(obj.media.all()), many=True).data

    def get_variants(self, obj):
        # Variant availability matrix: only active variants are exposed publicly
        active_variants = [variant for variant in obj.variants.all() if variant.is_active]
        return ProductVariantSerializer(active_variants, many=True).data

    def get_primary_image_url(self, obj):
        media_items = list(obj.media.all())  # uses prefetch cache
        for item in media_items:
            if item.is_primary:
                return item.url
        for item in media_items:
            if item.media_type == MediaType.IMAGE:
                return item.url
        return None


class ReviewSerializer(serializers.ModelSerializer):
    """
    Public serializer for customer product and designer reviews.
    """
    customer_name = serializers.SerializerMethodField()
    product_title = serializers.CharField(source='product.title', read_only=True)

    class Meta:
        model = Review
        fields = [
            'id',
            'product',
            'product_title',
            'vendor',
            'customer_name',
            'rating',
            'comment',
            'is_verified_purchase',
            'created_at'
        ]
        read_only_fields = fields

    def get_customer_name(self, obj) -> str:
        if obj.customer.first_name:
            last_initial = f" {obj.customer.last_name[0]}." if obj.customer.last_name else ""
            return f"{obj.customer.first_name}{last_initial}"
        return "Verified Customer"


class CreateReviewSerializer(serializers.Serializer):
    """
    Validation serializer for submitting a verified buyer review.
    """
    order_item_id = serializers.UUIDField(required=True)
    rating = serializers.IntegerField(required=True, min_value=1, max_value=5)
    comment = serializers.CharField(required=True, max_length=2000, allow_blank=False)

