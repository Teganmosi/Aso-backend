from django.contrib import admin
from apps.products.models import Category, Product, ProductVariant, ProductMedia, Review, ApprovalStatus, ProductStatus



class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ['size', 'color', 'sku', 'stock_quantity', 'price_override_kobo', 'is_active']
    readonly_fields = ['sku']


class ProductMediaInline(admin.TabularInline):
    model = ProductMedia
    extra = 1
    fields = ['media_type', 'url', 'display_order', 'is_primary']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'parent', 'is_active', 'display_order']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'slug', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['display_order', 'name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'title',
        'vendor',
        'category',
        'base_price_kobo',
        'approval_status',
        'status',
        'is_active',
        'created_at'
    ]
    list_filter = ['approval_status', 'status', 'is_active', 'category']
    search_fields = ['title', 'slug', 'vendor__store_name', 'description']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ProductVariantInline, ProductMediaInline]
    actions = ['approve_selected_products', 'reject_selected_products']

    @admin.action(description="Approve selected products and mark as PUBLISHED")
    def approve_selected_products(self, request, queryset):
        updated_count = queryset.update(
            approval_status=ApprovalStatus.APPROVED,
            status=ProductStatus.PUBLISHED,
            rejection_reason=None
        )
        self.message_user(request, f"{updated_count} product(s) approved and published.")

    @admin.action(description="Reject selected products")
    def reject_selected_products(self, request, queryset):
        updated_count = queryset.update(
            approval_status=ApprovalStatus.REJECTED
        )
        self.message_user(request, f"{updated_count} product(s) rejected.")


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['product', 'size', 'color', 'sku', 'stock_quantity', 'price_override_kobo', 'is_active']
    list_filter = ['size', 'is_active']
    search_fields = ['sku', 'size', 'color', 'product__title']


@admin.register(ProductMedia)
class ProductMediaAdmin(admin.ModelAdmin):
    list_display = ['product', 'media_type', 'url', 'display_order', 'is_primary', 'created_at']
    list_filter = ['media_type', 'is_primary']
    search_fields = ['url', 'product__title']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'vendor', 'customer', 'rating', 'is_verified_purchase', 'created_at']
    list_filter = ['rating', 'is_verified_purchase', 'created_at']
    search_fields = ['product__title', 'vendor__store_name', 'customer__email', 'comment']
    readonly_fields = ['order_item', 'product', 'vendor', 'customer', 'created_at', 'updated_at']

