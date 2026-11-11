from django.contrib import admin
from django.contrib import messages
from rest_framework.exceptions import ValidationError
from .models import VendorProfile, BankAccount, VendorStatus
from .services import approve_verification, reject_verification

@admin.action(description='Approve selected storefront applications (does NOT grant Verified badge)')
def approve_vendors(modeladmin, request, queryset):
    count = queryset.update(status=VendorStatus.APPROVED)
    modeladmin.message_user(request, f"{count} storefront(s) approved.")


@admin.action(description='Reject selected storefront applications')
def reject_vendors(modeladmin, request, queryset):
    count = queryset.update(status=VendorStatus.REJECTED)
    modeladmin.message_user(request, f"{count} storefront(s) rejected.")


@admin.action(description='✓ Approve identity verification (grant Verified badge)')
def approve_identity_verification(modeladmin, request, queryset):
    approved, skipped = 0, []
    for vendor in queryset.select_related('user'):
        try:
            approve_verification(vendor, request.user)
            approved += 1
        except ValidationError:
            skipped.append(vendor.store_name)
    modeladmin.message_user(request, f"{approved} designer(s) verified.")
    if skipped:
        modeladmin.message_user(
            request, f"Skipped (no NIN/CAC submitted): {', '.join(skipped)}", level=messages.WARNING
        )


@admin.action(description='✗ Reject identity verification (designer is asked to resubmit)')
def reject_identity_verification(modeladmin, request, queryset):
    count = 0
    for vendor in queryset.select_related('user'):
        # Uses any reason typed into the vendor's "Verification rejection reason" field, else a default.
        reject_verification(vendor, request.user, vendor.verification_rejection_reason)
        count += 1
    modeladmin.message_user(request, f"{count} verification request(s) rejected; designers have been notified.")


@admin.register(VendorProfile)
class VendorProfileAdmin(admin.ModelAdmin):
    list_display = ('store_name', 'user_email', 'city', 'state', 'status', 'verification_status',
                    'verification_submitted_at', 'kyc_tier', 'is_verified', 'created_at')
    list_filter = ('verification_status', 'status', 'kyc_tier', 'is_verified', 'state', 'city')
    search_fields = ('store_name', 'slug', 'user__email', 'user__first_name', 'user__last_name', 'instagram_handle', 'nin_number', 'cac_number')
    prepopulated_fields = {'slug': ('store_name',)}
    actions = [approve_identity_verification, reject_identity_verification, approve_vendors, reject_vendors]
    # The badge can only change through the review actions above (which keep an audit trail).
    readonly_fields = ('is_verified', 'kyc_tier', 'verification_status', 'verification_submitted_at',
                       'verification_reviewed_at', 'verification_reviewed_by', 'created_at', 'updated_at')



    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Owner Email'


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'vendor', 'bank_name', 'account_number', 'bank_code', 'created_at')
    search_fields = ('account_name', 'account_number', 'bank_name', 'vendor__store_name')
