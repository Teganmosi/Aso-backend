from django.contrib import admin
from .models import VendorProfile, BankAccount, VendorStatus, KYCTier

@admin.action(description='Approve selected vendor applications')
def approve_vendors(modeladmin, request, queryset):
    count = 0
    for vendor in queryset.select_related('user', 'bank_account'):
        vendor.status = VendorStatus.APPROVED
        vendor.is_verified = True
        # Elevate to Tier 2 Verified if NIN or Bank details are configured
        if vendor.nin_number or hasattr(vendor, 'bank_account'):
            vendor.kyc_tier = KYCTier.TIER_2_VERIFIED
        vendor.save(update_fields=['status', 'is_verified', 'kyc_tier'])
        count += 1
    modeladmin.message_user(request, f"{count} vendor application(s) successfully approved.")


@admin.action(description='Reject selected vendor applications')
def reject_vendors(modeladmin, request, queryset):
    count = 0
    for vendor in queryset:
        vendor.status = VendorStatus.REJECTED
        vendor.save(update_fields=['status'])
        count += 1
    modeladmin.message_user(request, f"{count} vendor application(s) rejected.")


@admin.action(description='Promote selected vendors to Tier 2 (Verified Designer)')
def promote_to_tier_2_verified(modeladmin, request, queryset):
    count = 0
    for vendor in queryset:
        vendor.kyc_tier = KYCTier.TIER_2_VERIFIED
        vendor.is_verified = True
        vendor.save(update_fields=['kyc_tier', 'is_verified'])
        count += 1
    modeladmin.message_user(request, f"{count} vendor(s) promoted to Tier 2 (Verified Designer).")


@admin.action(description='Promote selected vendors to Tier 3 (Enterprise Partner)')
def promote_to_tier_3_enterprise(modeladmin, request, queryset):
    count = 0
    for vendor in queryset:
        vendor.kyc_tier = KYCTier.TIER_3_ENTERPRISE
        vendor.is_verified = True
        vendor.save(update_fields=['kyc_tier', 'is_verified'])
        count += 1
    modeladmin.message_user(request, f"{count} vendor(s) promoted to Tier 3 (Enterprise Partner).")


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display = ('store_name', 'user_email', 'city', 'state', 'status', 'kyc_tier', 'is_verified', 'instagram_handle', 'created_at')
    list_filter = ('status', 'kyc_tier', 'is_verified', 'state', 'city')
    search_fields = ('store_name', 'slug', 'user__email', 'user__first_name', 'user__last_name', 'instagram_handle', 'nin_number', 'cac_number')
    prepopulated_fields = {'slug': ('store_name',)}
    actions = [approve_vendors, reject_vendors, promote_to_tier_2_verified, promote_to_tier_3_enterprise]



    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Owner Email'


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'vendor', 'bank_name', 'account_number', 'bank_code', 'created_at')
    search_fields = ('account_name', 'account_number', 'bank_name', 'vendor__store_name')
