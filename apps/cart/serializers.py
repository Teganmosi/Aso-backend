from rest_framework import serializers
from apps.cart.models import Cart, CartItem
from apps.products.models import ProductVariant, ApprovalStatus, ProductStatus, MediaType
from apps.vendors.serializers import PublicVendorProfileSerializer


class CartItemSerializer(serializers.ModelSerializer):
    """
    Serializer for items in the customer's cart.
    """
    variant_id = serializers.UUIDField(source='variant.id', read_only=True)
    product_id = serializers.UUIDField(source='variant.product.id', read_only=True)
    product_title = serializers.CharField(source='variant.product.title', read_only=True)
    product_slug = serializers.CharField(source='variant.product.slug', read_only=True)
    size = serializers.CharField(source='variant.size', read_only=True)
    color = serializers.CharField(source='variant.color', read_only=True)
    sku = serializers.CharField(source='variant.sku', read_only=True)
    stock_quantity = serializers.IntegerField(source='variant.stock_quantity', read_only=True)
    unit_price_kobo = serializers.IntegerField(read_only=True)
    unit_price_naira = serializers.FloatField(read_only=True)
    total_price_kobo = serializers.IntegerField(read_only=True)
    total_price_naira = serializers.FloatField(read_only=True)
    primary_image_url = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            'id',
            'variant_id',
            'product_id',
            'product_title',
            'product_slug',
            'size',
            'color',
            'sku',
            'stock_quantity',
            'unit_price_kobo',
            'unit_price_naira',
            'quantity',
            'total_price_kobo',
            'total_price_naira',
            'primary_image_url',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields

    def get_primary_image_url(self, obj) -> str | None:
        media_items = list(obj.variant.product.media.all())
        for item in media_items:
            if item.is_primary:
                return item.url
        for item in media_items:
            if item.media_type == MediaType.IMAGE:
                return item.url
        return None


class CartSerializer(serializers.ModelSerializer):
    """
    Serializer for the customer's single-vendor cart.
    """
    vendor = PublicVendorProfileSerializer(read_only=True)
    items = CartItemSerializer(many=True, read_only=True)
    subtotal_kobo = serializers.IntegerField(read_only=True)
    subtotal_naira = serializers.FloatField(read_only=True)
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Cart
        fields = [
            'id',
            'vendor',
            'items',
            'subtotal_kobo',
            'subtotal_naira',
            'item_count',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields


class AddCartItemSerializer(serializers.Serializer):
    """
    Serializer for adding a product variant to the cart.
    """
    variant_id = serializers.UUIDField(required=True)
    quantity = serializers.IntegerField(default=1, min_value=1)

    def validate_variant_id(self, value):
        try:
            variant = ProductVariant.objects.select_related('product', 'product__vendor').get(id=value)
        except ProductVariant.DoesNotExist:
            raise serializers.ValidationError("Product variant does not exist.")

        if not variant.is_active:
            raise serializers.ValidationError("Product variant is inactive.")

        product = variant.product
        if not product.is_active or product.approval_status != ApprovalStatus.APPROVED or product.status != ProductStatus.PUBLISHED:
            raise serializers.ValidationError("Product is not available for purchase.")

        self._variant = variant
        return value

    def validate(self, attrs):
        quantity = attrs.get('quantity', 1)
        variant = getattr(self, '_variant', None)

        if not variant:
            raise serializers.ValidationError({"variant_id": "Product variant does not exist."})

        if variant.stock_quantity < quantity:
            raise serializers.ValidationError({
                "quantity": f"Requested quantity ({quantity}) exceeds available stock ({variant.stock_quantity})."
            })

        attrs['variant'] = variant
        return attrs


class UpdateCartItemSerializer(serializers.Serializer):
    """
    Serializer for updating cart item quantity.
    """
    quantity = serializers.IntegerField(required=True, min_value=0)
