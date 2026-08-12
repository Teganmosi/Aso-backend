from django.contrib import admin
from apps.products.models import Category, Product, ApprovalStatus, ProductStatus


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
