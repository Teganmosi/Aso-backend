from rest_framework import serializers
from apps.products.models import Category, Product, ApprovalStatus, ProductStatus
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
            'vendor',
            'category',
            'created_at'
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Detailed product serializer.
    """
    vendor = PublicVendorProfileSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    base_price_naira = serializers.FloatField(read_only=True)

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
            'vendor',
            'category',
            'created_at',
            'updated_at'
        ]
