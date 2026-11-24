from django.contrib import admin
from django.contrib import messages
from django.db.models import Count
from django.utils.html import format_html
from apps.common.admin_display import badge, whatsapp_link
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
    search_help_text = 'Search by studio, owner name, email, Instagram, NIN or CAC'
    prepopulated_fields = {'slug': ('store_name',)}
    autocomplete_fields = ('user',)
    actions = [approve_identity_verification, reject_identity_verification, approve_vendors, reject_vendors]
    # The badge can only change through the review actions above (which keep an audit trail).
    readonly_fields = ('is_verified', 'kyc_tier', 'verification_status', 'verification_submitted_at',
                       'verification_reviewed_at', 'verification_reviewed_by', 'created_at', 'updated_at',
                       'owner_contact', 'pieces_link', 'identity_status', 'reviewed', 'verified_badge')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        labels = {'nin_number': 'NIN', 'cac_number': 'CAC number', 'user': 'Account',
                  'verification_rejection_reason': 'Reason if rejected', 'slug': 'Web address',
                  'status': 'Studio status'}
        for name, label in labels.items():
            if name in form.base_fields:
                form.base_fields[name].label = label
        if 'slug' in form.base_fields:
            form.base_fields['slug'].help_text = 'The end of the studio link, e.g. asomarketplace.com.ng/designers/<this>'
        return form

    @admin.display(description='Check status')
    def identity_status(self, obj):
        label = {'PENDING_REVIEW': 'Waiting for you to check'}.get(obj.verification_status)
        sent = obj.verification_submitted_at
        when = f' · sent {sent:%d %b %Y}' if sent else ''
        return format_html('{}{}', badge(obj.verification_status, label or obj.get_verification_status_display()), when)

    @admin.display(description='Reviewed')
    def reviewed(self, obj):
        if not obj.verification_reviewed_at:
            return 'Not yet'
        who = obj.verification_reviewed_by
        return f'{obj.verification_reviewed_at:%d %b %Y}' + (f' by {who}' if who else '')

    @admin.display(description='Verified badge')
    def verified_badge(self, obj):
        return badge('VERIFIED' if obj.is_verified else '', 'Shows the badge' if obj.is_verified else 'No badge')
    fieldsets = [
        ('Studio', {'fields': ['store_name', 'slug', 'status', 'description', 'instagram_handle', 'pieces_link']}),
        ('Owner and pickup', {'fields': ['user', 'owner_contact', 'workshop_address', 'landmark', 'city', 'state']}),
        ('Identity check (NIN/CAC)', {
            'description': 'To approve or reject, tick the studio on the designers list and pick the action. '
                           'Type a rejection reason here and save first if you want the designer to see why.',
            'fields': ['identity_status', 'nin_number', 'cac_number', 'verification_rejection_reason',
                       'reviewed', 'verified_badge'],
        }),
        ('Logo and banner', {'classes': ['collapse'], 'fields': ['logo_url', 'banner_url']}),
        ('Dates', {'classes': ['collapse'], 'fields': ['created_at', 'updated_at']}),
    ]

    @admin.display(description='Contact')
    def owner_contact(self, obj):
        return format_html('{}<br>{}<br>{}', obj.user.get_full_name() or '—', obj.user.email,
                           whatsapp_link(obj.user.phone_number))

    @admin.display(description='Pieces')
    def pieces_link(self, obj):
        from django.urls import reverse
        if not obj.pk:
            return '—'
        url = reverse('admin:products_product_changelist') + f'?vendor__id__exact={obj.pk}'
        return format_html('<a href="{}">See all pieces from this studio</a>', url)



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
