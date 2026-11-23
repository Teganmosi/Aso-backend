from apps.common.admin_display import badge, naira, thumb
from apps.common.notifications import send_product_review_notification
from django import forms
from django.contrib import admin
from django.db import models
from django.utils.html import format_html_join
from apps.products.models import Category, Product, ProductVariant, ProductMedia, Review, ApprovalStatus, ProductStatus
from apps.products.services import invalidate_product_caches



class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ['size', 'color', 'sku', 'stock_quantity', 'price_override_kobo', 'is_active']
    readonly_fields = ['sku']


class ProductMediaInline(admin.TabularInline):
    model = ProductMedia
    extra = 0
    fields = ['preview', 'media_type', 'url', 'display_order', 'is_primary']
    readonly_fields = ['preview']
    # One-line address box instead of a large textarea (older photos are long data URIs).
    formfield_overrides = {models.TextField: {'widget': forms.TextInput(attrs={'size': 60})}}

    @admin.display(description='Photo')
    def preview(self, obj):
        return thumb((obj.thumbnail_url or obj.url) if obj and obj.pk else None, 72)


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
        'photo',
        'title',
        'vendor',
        'category',
        'price',
        'review_badge',
        'status',
        'is_active',
        'created_at'
    ]
    list_display_links = ['photo', 'title']
    list_filter = ['approval_status', 'status', 'is_active', 'category', 'vendor']
    search_fields = ['title', 'slug', 'vendor__store_name', 'description']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ProductVariantInline, ProductMediaInline]
    actions = ['approve_selected_products', 'reject_selected_products']
    list_select_related = ['vendor', 'category']
    ordering = ['-created_at']
    list_per_page = 40
    readonly_fields = ['photos_preview', 'price', 'average_rating', 'review_count']
    fieldsets = [
        ('Review', {
            'description': 'Check the photos, title, price and sizes. To ask for changes, choose '
                           '"Rejected", write what to change, and save: the designer is emailed.',
            'fields': ['photos_preview', 'approval_status', 'rejection_reason', 'status', 'is_active'],
        }),
        ('The piece', {
            'fields': ['vendor', 'category', 'title', 'slug', 'description',
                       ('base_price_kobo', 'price'), 'preparation_time_days'],
        }),
        ('Ratings and size chart', {
            'classes': ['collapse'],
            'fields': [('average_rating', 'review_count'), 'size_chart'],
        }),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('media')

    def _media(self, obj):
        return sorted(obj.media.all(), key=lambda m: (not m.is_primary, m.display_order))

    @staticmethod
    def _small_url(m):
        # Older uploads may be inline data URIs; don't paste megabytes into every list row.
        url = m.thumbnail_url or m.url
        return None if url.startswith('data:') and len(url) > 150_000 else url

    @admin.display(description='')
    def photo(self, obj):
        media = self._media(obj)
        return thumb(self._small_url(media[0]) if media else None)

    @admin.display(description='Photos (check front, back and details)')
    def photos_preview(self, obj):
        media = self._media(obj)
        if not media:
            return 'No photos'
        return format_html_join('', '<a href="{0}" target="_blank" rel="noopener">{1}</a> ',
                                ((m.url, thumb(m.thumbnail_url or m.url, 140)) for m in media))

    @admin.display(description='Price', ordering='base_price_kobo')
    def price(self, obj):
        return naira(obj.base_price_kobo)

    @admin.display(description='Review', ordering='approval_status')
    def review_badge(self, obj):
        label = {'PENDING': 'Waiting for review', 'APPROVED': 'Live', 'REJECTED': 'Changes requested'}
        return badge(obj.approval_status, label.get(obj.approval_status))

    @admin.action(description="Approve selected products and mark as PUBLISHED")
    def approve_selected_products(self, request, queryset):
        newly_approved = list(queryset.exclude(approval_status=ApprovalStatus.APPROVED)
                              .select_related('vendor__user'))
        updated_count = queryset.update(
            approval_status=ApprovalStatus.APPROVED,
            status=ProductStatus.PUBLISHED,
            rejection_reason=None
        )
        invalidate_product_caches()  # show approved products publicly right away
        for product in newly_approved:
            send_product_review_notification(product, approved=True)
        self.message_user(request, f"{updated_count} product(s) approved and published. "
                                   f"{len(newly_approved)} designer email(s) sent.")

    @admin.action(description="Reject selected products")
    def reject_selected_products(self, request, queryset):
        updated_count = queryset.update(
            approval_status=ApprovalStatus.REJECTED
        )
        invalidate_product_caches()  # remove rejected products from public lists right away
        self.message_user(
            request,
            f"{updated_count} product(s) rejected. Open each one and fill in “Rejection reason”: "
            "the designer is emailed what to change when you save it.",
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        invalidate_product_caches()  # edits in the admin form show up publicly right away
        review_changed = change and {'approval_status', 'rejection_reason'} & set(form.changed_data)
        if review_changed:
            if obj.approval_status == ApprovalStatus.REJECTED and obj.rejection_reason:
                send_product_review_notification(obj, approved=False)
            elif obj.approval_status == ApprovalStatus.APPROVED and 'approval_status' in form.changed_data:
                send_product_review_notification(obj, approved=True)


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

