from django.contrib import admin
from apps.orders.models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = [
        'id',
        'variant',
        'product_title_snapshot',
        'variant_size_snapshot',
        'variant_color_snapshot',
        'sku_snapshot',
        'unit_price_kobo',
        'quantity',
        'total_price_kobo',
        'created_at'
    ]
    fields = [
        'product_title_snapshot',
        'variant_size_snapshot',
        'variant_color_snapshot',
        'sku_snapshot',
        'unit_price_kobo',
        'quantity',
        'total_price_kobo'
    ]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_number',
        'customer',
        'vendor',
        'order_status',
        'total_amount_naira',
        'payment_expires_at',
        'created_at'
    ]
    list_filter = ['order_status', 'created_at']
    search_fields = ['order_number', 'customer__email', 'vendor__store_name']
    readonly_fields = [
        'id',
        'order_number',
        'customer',
        'vendor',
        'subtotal_kobo',
        'delivery_fee_kobo',
        'total_amount_kobo',
        'subtotal_naira',
        'delivery_fee_naira',
        'total_amount_naira',
        'payment_expires_at',
        'shipping_address_snapshot',
        'created_at',
        'updated_at'
    ]
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'order',
        'product_title_snapshot',
        'variant_size_snapshot',
        'unit_price_naira',
        'quantity',
        'total_price_naira',
        'created_at'
    ]
    search_fields = ['order__order_number', 'sku_snapshot', 'product_title_snapshot']
    readonly_fields = [
        'id',
        'order',
        'variant',
        'product_title_snapshot',
        'variant_size_snapshot',
        'variant_color_snapshot',
        'sku_snapshot',
        'unit_price_kobo',
        'quantity',
        'total_price_kobo',
        'created_at',
        'updated_at'
    ]
