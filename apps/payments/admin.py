from django.contrib import admin
from .models import PaymentProvider, PaymentRequest, PaymentWebhookLog


@admin.register(PaymentProvider)
class PaymentProviderAdmin(admin.ModelAdmin):
    """Admin interface for PaymentProvider configuration."""
    list_display = ['name', 'display_name', 'is_active', 'created_at']
    list_editable = ['is_active']
    search_fields = ['name', 'display_name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    """Admin interface for PaymentRequest tracking."""
    list_display = ['id', 'order', 'provider', 'reference', 'amount_kobo', 'currency', 'status', 'created_at']
    list_filter = ['provider', 'status', 'created_at']
    search_fields = ['reference', 'order__order_number', 'order__customer__email']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['order']


@admin.register(PaymentWebhookLog)
class PaymentWebhookLogAdmin(admin.ModelAdmin):
    """Admin interface for PaymentWebhookLog audit trail."""
    list_display = ['id', 'reference', 'event', 'signature_verified', 'processed', 'created_at']
    list_filter = ['event', 'signature_verified', 'processed', 'created_at']
    search_fields = ['reference', 'event']
    readonly_fields = ['created_at']
    # Disable add/change from admin - logs are created programmatically only
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False