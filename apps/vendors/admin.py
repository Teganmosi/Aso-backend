from django.contrib import admin
from django.contrib import messages
from django.db.models import Count
from django.utils.html import format_html
from apps.common.admin_display import badge
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
    list_display = ('store_name', 'owner', 'location', 'studio_badge', 'identity_badge',
                    'verification_submitted_at', 'pieces', 'bank', 'created_at')
    list_filter = ('verification_status', 'status', 'kyc_tier', 'is_verified', 'state', 'city')
    list_select_related = ('user', 'bank_account')
    ordering = ('-created_at',)
    list_per_page = 50
    search_fields = ('store_name', 'slug', 'user__email', 'user__first_name', 'user__last_name', 'instagram_handle', 'nin_number', 'cac_number')
    prepopulated_fields = {'slug': ('store_name',)}
    actions = [approve_identity_verification, reject_identity_verification, approve_vendors, reject_vendors]
    # The badge can only change through the review actions above (which keep an audit trail).
    readonly_fields = ('is_verified', 'kyc_tier', 'verification_status', 'verification_submitted_at',
                       'verification_reviewed_at', 'verification_reviewed_by', 'created_at', 'updated_at')



    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_pieces=Count('products', distinct=True))

    @admin.display(description='Owner', ordering='user__email')
    def owner(self, obj):
        return format_html('{}<br><small>{} · {}</small>', obj.user.get_full_name() or '—',
                           obj.user.email, obj.user.phone_number or 'no phone')

    @admin.display(description='Location', ordering='state')
    def location(self, obj):
        return ', '.join(x for x in (obj.city, obj.state) if x) or '—'

    @admin.display(description='Studio', ordering='status')
    def studio_badge(self, obj):
        return badge(obj.status, obj.get_status_display())

    @admin.display(description='Identity', ordering='verification_status')
    def identity_badge(self, obj):
        label = {'PENDING_REVIEW': 'Check NIN/CAC'}.get(obj.verification_status)
        return badge(obj.verification_status, label or obj.get_verification_status_display())

    @admin.display(description='Pieces', ordering='_pieces')
    def pieces(self, obj):
        return obj._pieces

    @admin.display(description='Bank account')
    def bank(self, obj):
        acct = getattr(obj, 'bank_account', None)
        if not acct:
            return '—'
        return format_html('{}<br><small>{} · code {}</small>', acct.bank_name, acct.account_number, acct.bank_code or '—')


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'vendor', 'bank_name', 'account_number', 'bank_code', 'created_at')
    search_fields = ('account_name', 'account_number', 'bank_name', 'vendor__store_name')
    list_filter = ('bank_name',)
    list_select_related = ('vendor',)
