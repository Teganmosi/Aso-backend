from django.contrib import admin
from .models import VendorProfile, BankAccount, VendorStatus

@admin.action(description='Approve selected vendor applications')
def approve_vendors(modeladmin, request, queryset):
    updated = queryset.update(status=VendorStatus.APPROVED, is_verified=True)
    modeladmin.message_user(request, f"{updated} vendor application(s) successfully approved.")


@admin.action(description='Reject selected vendor applications')
def reject_vendors(modeladmin, request, queryset):
    updated = queryset.update(status=VendorStatus.REJECTED)
    modeladmin.message_user(request, f"{updated} vendor application(s) rejected.")


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display = ('store_name', 'user_email', 'city', 'state', 'status', 'is_verified', 'average_rating', 'created_at')
    list_filter = ('status', 'is_verified', 'state', 'city')
    search_fields = ('store_name', 'slug', 'user__email', 'user__first_name', 'user__last_name')
    prepopulated_fields = {'slug': ('store_name',)}
    actions = [approve_vendors, reject_vendors]

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Owner Email'


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'vendor', 'bank_name', 'account_number', 'bank_code', 'created_at')
    search_fields = ('account_name', 'account_number', 'bank_name', 'vendor__store_name')
