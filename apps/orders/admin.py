from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from apps.common.admin_display import badge, naira
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
        'measurements',
        'unit_price',
        'quantity',
        'line_total',
    ]
    readonly_fields = readonly_fields + ['measurements', 'unit_price', 'line_total']

    @admin.display(description='Unit price')
    def unit_price(self, obj):
        return naira(obj.unit_price_kobo)

    @admin.display(description='Total')
    def line_total(self, obj):
        return naira(obj.total_price_kobo)

    @admin.display(description='Measurements')
    def measurements(self, obj):
        m = obj.custom_measurements or {}
        if not m:
            return '—'
        return ', '.join(f'{k.replace("_", " ")}: {v}' for k, v in m.items() if not isinstance(v, (dict, list)))


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_number',
        'created_at',
        'status_badge',
        'what',
        'vendor',
        'shopper',
        'total',
        'accept_by',
    ]
    list_filter = ['order_status', 'created_at', 'vendor']
    search_fields = ['order_number', 'customer__email', 'customer__phone_number', 'vendor__store_name']
    list_select_related = ['customer', 'vendor']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    list_per_page = 50

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('items')

    @admin.display(description='Status', ordering='order_status')
    def status_badge(self, obj):
        return badge(obj.order_status, obj.get_order_status_display())

    @admin.display(description='Piece')
    def what(self, obj):
        items = list(obj.items.all())
        if not items:
            return '—'
        first = items[0]
        more = f' +{len(items) - 1} more' if len(items) > 1 else ''
        return f'{first.product_title_snapshot} ({first.variant_size_snapshot}){more}'

    @admin.display(description='Shopper', ordering='customer__email')
    def shopper(self, obj):
        name = (obj.shipping_address_snapshot or {}).get('full_name') or obj.customer.get_full_name()
        return format_html('{}<br><small>{}</small>', name or '—', obj.customer.email)

    @admin.display(description='Total', ordering='total_amount_kobo')
    def total(self, obj):
        return naira(obj.total_amount_kobo)

    @admin.display(description='Designer must accept by', ordering='vendor_accept_due_by')
    def accept_by(self, obj):
        from apps.orders.models import OrderStatus
        if obj.order_status != OrderStatus.PAID or not obj.vendor_accept_due_by:
            return '—'
        late = obj.vendor_accept_due_by < timezone.now()
        return format_html('<span class="{}">{}</span>', 'aso-late' if late else '',
                           timezone.localtime(obj.vendor_accept_due_by).strftime('%d %b, %H:%M'))
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

    @admin.action(description="Cancel selected orders and stop the designer payment (then refund the shopper in the Paystack dashboard)")
    def cancel_and_refund_order(self, request, queryset):
        from apps.orders.models import OrderStatus
        from apps.payouts.services import reverse_pending_earning
        count = 0
        for order in queryset:
            if order.order_status not in [OrderStatus.CANCELLED, OrderStatus.REFUNDED, OrderStatus.COMPLETED]:
                order.order_status = OrderStatus.CANCELLED
                order.cancellation_reason = "Cancelled by Aso"
                order.save(update_fields=['order_status', 'cancellation_reason', 'updated_at'])
                reverse_pending_earning(order)
                count += 1
        self.message_user(request, f"{count} order(s) cancelled. Remember to refund each shopper in the Paystack dashboard.")


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

from apps.orders.models import OrderMessage

@admin.register(OrderMessage)
class OrderMessageAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'order',
        'sender',
        'message_type',
        'is_masked',
        'mask_tier',
        'mask_reason',
        'created_at'
    ]
    list_filter = ['is_masked', 'mask_tier', 'message_type', 'created_at']
    search_fields = ['order__order_number', 'sender__email', 'content', 'original_content']
    readonly_fields = [
        'id',
        'order',
        'sender',
        'message_type',
        'content',
        'original_content',
        'is_masked',
        'mask_reason',
        'mask_tier',
        'action_type',
        'action_payload',
        'read_at',
        'created_at',
        'updated_at'
    ]
