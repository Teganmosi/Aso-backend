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


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for vendor product creation and editing.
    """
    category_id = serializers.UUIDField(write_only=True)
    base_price_naira = serializers.FloatField(read_only=True)

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
            'vendor',
            'category',
            'created_at'
        ]

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
    Detailed product serializer including media gallery and variant availability matrix.
    """
    vendor = PublicVendorProfileSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    base_price_naira = serializers.FloatField(read_only=True)
    primary_image_url = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()

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
            'vendor',
            'category',
            'created_at',
            'updated_at'
        ]

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

