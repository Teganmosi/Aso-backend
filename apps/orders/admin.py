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
    actions = ['mark_as_disputed', 'resolve_dispute_complete', 'cancel_and_refund_order']

    @admin.action(description="Mark selected orders as DISPUTED")
    def mark_as_disputed(self, request, queryset):
        from apps.orders.models import OrderStatus
        count = queryset.exclude(order_status__in=[OrderStatus.CANCELLED, OrderStatus.REFUNDED]).update(
            order_status=OrderStatus.DISPUTED
        )
        self.message_user(request, f"{count} order(s) marked as Disputed.")

    @admin.action(description="Resolve dispute: Mark selected orders as COMPLETED")
    def resolve_dispute_complete(self, request, queryset):
        from apps.payouts.services import complete_order
        count = 0
        for order in queryset:
            complete_order(order)
            count += 1
        self.message_user(request, f"{count} order(s) completed and funds released.")

    @admin.action(description="Cancel and release pending earnings for selected orders")
    def cancel_and_refund_order(self, request, queryset):
        from apps.orders.models import OrderStatus
        from apps.payouts.services import reverse_pending_earning
        count = 0
        for order in queryset:
            if order.order_status not in [OrderStatus.CANCELLED, OrderStatus.REFUNDED, OrderStatus.COMPLETED]:
                order.order_status = OrderStatus.CANCELLED
                order.cancellation_reason = "Admin cancelled / dispute refunded"
                order.save(update_fields=['order_status', 'cancellation_reason', 'updated_at'])
                reverse_pending_earning(order)
                count += 1
        self.message_user(request, f"{count} order(s) cancelled.")


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
