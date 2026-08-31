from django.contrib import admin
from .models import Delivery, DeliveryStatus


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = [
        'tracking_number',
        'order',
        'carrier_name',
        'status',
        'dispatched_at',
        'delivered_at',
        'created_at'
    ]
    list_filter = ['status', 'carrier_name', 'created_at']
    search_fields = [
        'tracking_number',
        'order__order_number',
        'carrier_name',
        'dispatch_notes'
    ]
    readonly_fields = [
        'id',
        'order',
        'tracking_number',
        'picked_up_at',
        'dispatched_at',
        'delivered_at',
        'created_at',
        'updated_at'
    ]
    actions = ['mark_in_transit', 'mark_delivered']

    @admin.action(description="Mark selected deliveries as In Transit (Out for Delivery)")
    def mark_in_transit(self, request, queryset):
        from .services import update_delivery_status
        count = 0
        for delivery in queryset:
            if delivery.status != DeliveryStatus.DELIVERED:
                update_delivery_status(delivery, DeliveryStatus.IN_TRANSIT)
                count += 1
        self.message_user(request, f"{count} delivery/deliveries marked as In Transit.")

    @admin.action(description="Mark selected deliveries as Delivered")
    def mark_delivered(self, request, queryset):
        from .services import update_delivery_status
        count = 0
        for delivery in queryset:
            update_delivery_status(delivery, DeliveryStatus.DELIVERED)
            count += 1
        self.message_user(request, f"{count} delivery/deliveries marked as Delivered.")
