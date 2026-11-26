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
from apps.vendors.serializers import PublicVendorProfileSerializer, CompactVendorSerializer
from apps.common.media_storage import is_data_uri


def _card_image_url(media_items):
    """
    Image for product cards and cart lines: the small thumbnail when one exists
    (uploads since local media storage), otherwise the full image.
    Primary image first, then the first image.
    """
    ordered = [m for m in media_items if m.is_primary] + [
        m for m in media_items if not m.is_primary and m.media_type == MediaType.IMAGE
    ]
    for item in ordered:
        return item.thumbnail_url or item.url
    return None


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
        # Uses prefetched in-memory children cache if available to prevent N+1 SQL queries
        all_children = getattr(obj, '_prefetched_objects_cache', {}).get('children')
        if all_children is not None:
            active_children = [c for c in all_children if c.is_active]
        else:
            active_children = list(obj.children.filter(is_active=True))
        if active_children:
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
        if is_data_uri(value):
            # Inline base64 images bloated every product response (see
            # apps/common/media_storage.py). Upload via /api/v1/media/upload/.
            raise serializers.ValidationError(
                "Upload the image first (POST /api/v1/media/upload/) and attach the returned URL."
            )
        return str(value).strip()

    def validate_thumbnail_url(self, value):
        if is_data_uri(value):
            raise serializers.ValidationError("Thumbnail must be an uploaded image URL, not inline data.")
        return value


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

    def validate_size_chart(self, value):
        from apps.products.sizing import clean_designer_chart
        try:
            return clean_designer_chart(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def validate_preparation_time_days(self, value):
        if value < 1 or value > 90:
            raise serializers.ValidationError("Preparation time must be between 1 and 90 days.")
        return value


class ProductListSerializer(serializers.ModelSerializer):
    """
    Serializer for product catalog listings.
    Optimized with CompactVendorSerializer to prevent N+1 query loops.
    """
    vendor = CompactVendorSerializer(read_only=True)
    category = CategorySimpleSerializer(read_only=True)
    base_price_naira = serializers.FloatField(read_only=True)
    primary_image_url = serializers.SerializerMethodField()
    available_sizes = serializers.SerializerMethodField()
    wearer = serializers.SerializerMethodField()
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
            'wearer',
            'size_chart',
            'vendor',
            'category',
            'created_at'
        ]

    def get_wearer(self, obj):
        """'female', 'male' or None: who the piece is for, from its department and title."""
        from apps.products.sizing import wearer_for_product
        return wearer_for_product(obj)

    def get_size_chart(self, obj):
        if obj.size_chart and isinstance(obj.size_chart, dict) and obj.size_chart.get('body_measurements'):
            return obj.size_chart
        return None

    def get_primary_image_url(self, obj):
        # Product grids only need the small thumbnail (uses prefetch cache).
        return _card_image_url(list(obj.media.all()))

    def get_available_sizes(self, obj):
        # Python-level filtering over the prefetched variants (cache-bound, no extra queries)
        return sorted({
            variant.size for variant in obj.variants.all()
            if variant.is_active and variant.stock_quantity > 0
        })


class VendorProductListSerializer(ProductListSerializer):
    """
    The designer's own list. Adds the reviewer's note, so a piece marked "Changes requested"
    says what to change in the studio (it was only in the email before).
    """

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + ['rejection_reason']


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
    wearer = serializers.SerializerMethodField()
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
            'wearer',
            'size_chart',
            'vendor',
            'category',
            'created_at',
            'updated_at'
        ]

    def get_wearer(self, obj):
        """'female', 'male' or None: who the piece is for, from its department and title."""
        from apps.products.sizing import wearer_for_product
        return wearer_for_product(obj)

    def get_size_chart(self, obj):
        if obj.size_chart and isinstance(obj.size_chart, dict) and obj.size_chart.get('body_measurements'):
            return obj.size_chart
        # The designer hasn't added a chart: typical sizes for this kind of piece, for the sizes it is
        # sold in, clearly marked as a general guide (apps/products/sizing.py).
        from apps.products.sizing import generic_size_chart
        return generic_size_chart(obj)

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

