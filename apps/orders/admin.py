from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from apps.common.admin_display import badge, naira, whatsapp_link
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
    fields = ['piece', 'size', 'colour', 'measurements', 'unit_price', 'quantity', 'line_total']
    readonly_fields = readonly_fields + ['piece', 'size', 'colour', 'measurements', 'unit_price', 'line_total']
    verbose_name = 'Piece in this order'
    verbose_name_plural = 'Pieces in this order'
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False  # what was bought is fixed once the shopper pays

    @admin.display(description='Piece')
    def piece(self, obj):
        return obj.product_title_snapshot

    @admin.display(description='Size')
    def size(self, obj):
        return obj.variant_size_snapshot or '—'

    @admin.display(description='Colour')
    def colour(self, obj):
        return obj.variant_color_snapshot or '—'

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
    search_help_text = 'Search by order number, shopper email or phone, or studio name'
    readonly_fields = [
        'id', 'order_number', 'placed', 'shopper_contact', 'designer_contact', 'deliver_to',
        'subtotal', 'delivery_fee', 'total_paid', 'timeline',
    ]
    fieldsets = [
        (None, {'fields': ['order_number', 'order_status', 'placed']}),
        ('Who', {'fields': ['shopper_contact', 'designer_contact', 'deliver_to']}),
        ('Money', {'fields': ['subtotal', 'delivery_fee', 'total_paid']}),
        ('Progress', {'fields': ['timeline']}),
        ('Cancellation note', {
            'classes': ['collapse'],
            'fields': ['cancellation_reason'],
            'description': 'Shown to the shopper and the designer. To cancel and stop the designer payment, '
                           'use the "Cancel selected orders" action on the orders list.',
        }),
        ('Technical', {'fields': ['id'], 'classes': ['collapse']}),
    ]

    def has_add_permission(self, request):
        return False  # orders only come from shoppers checking out

    def has_delete_permission(self, request, obj=None):
        return False  # deleting would orphan payments and designer earnings; cancel instead

    @admin.display(description='So far')
    def timeline(self, obj):
        from django.utils.html import format_html_join

        def when(dt):
            return timezone.localtime(dt).strftime('%d %b, %H:%M')
        steps = [('Order placed', obj.created_at), ('Designer accepted', obj.vendor_accepted_at),
                 ('Finished sewing', obj.prepared_at), ('Ready for pickup', obj.ready_for_pickup_at)]
        rows = [(label, when(dt)) for label, dt in steps if dt]
        if not obj.vendor_accepted_at and obj.vendor_accept_due_by:
            rows.append(('Designer must accept by', when(obj.vendor_accept_due_by)))
        rows.append(('Last change', when(obj.updated_at)))
        return format_html('<ul class="aso-timeline">{}</ul>',
                           format_html_join('', '<li><span>{}</span> {}</li>', rows))

    @admin.display(description='Placed')
    def placed(self, obj):
        return timezone.localtime(obj.created_at).strftime('%d %b %Y, %H:%M')

    @admin.display(description='Shopper')
    def shopper_contact(self, obj):
        snap = obj.shipping_address_snapshot or {}
        name = snap.get('full_name') or obj.customer.get_full_name() or obj.customer.email
        phone = snap.get('phone_number') or obj.customer.phone_number
        return format_html('<strong>{}</strong><br>{}<br>{}', name, obj.customer.email, whatsapp_link(phone))

    @admin.display(description='Designer')
    def designer_contact(self, obj):
        v = obj.vendor
        pickup = ', '.join(x for x in (v.workshop_address, v.landmark, v.city, v.state) if x)
        return format_html('<strong>{}</strong><br>{}<br>{}<br><small>Pickup: {}</small>', v.store_name,
                           v.user.email, whatsapp_link(v.user.phone_number), pickup or 'no workshop address yet')

    @admin.display(description='Deliver to')
    def deliver_to(self, obj):
        snap = obj.shipping_address_snapshot or {}
        lines = [snap.get('street_address') or snap.get('address'), snap.get('landmark') and f"Near {snap['landmark']}",
                 ', '.join(x for x in (snap.get('city'), snap.get('state')) if x)]
        return ', '.join(x for x in lines if x) or '—'

    @admin.display(description='Pieces')
    def subtotal(self, obj):
        return naira(obj.subtotal_kobo)

    @admin.display(description='Delivery')
    def delivery_fee(self, obj):
        return naira(obj.delivery_fee_kobo)

    @admin.display(description='Total paid')
    def total_paid(self, obj):
        return format_html('<strong>{}</strong>', naira(obj.total_amount_kobo))

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

    def has_add_permission(self, request):
        return False
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

    def has_add_permission(self, request):
        return False
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
