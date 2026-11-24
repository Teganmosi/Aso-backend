from django.db import transaction
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from .models import VendorProfile, BankAccount, VendorStatus, VerificationStatus, KYCTier
from apps.accounts.models import User

def register_vendor_service(
    *,
    user: User,
    store_name: str,
    city: str,
    state: str,
    description: str = '',
    instagram_handle: str = '',
    workshop_address: str = '',
    landmark: str = '',
    nin_number: str = '',
    cac_number: str = '',
    bank_data: dict = None
) -> VendorProfile:
    """
    Registers a user as a Vendor with a PENDING profile status, progressive KYC fields, and optional BankAccount.
    """
    if hasattr(user, 'vendor_profile'):
        raise ValidationError("User has already registered a vendor profile.")

    with transaction.atomic():
        vendor_profile = VendorProfile.objects.create(
            user=user,
            store_name=store_name,
            city=city,
            state=state,
            description=description or None,
            instagram_handle=instagram_handle or None,
            workshop_address=workshop_address or None,
            landmark=landmark or None,
            nin_number=nin_number or None,
            cac_number=cac_number or None,
            status=VendorStatus.APPROVED
        )

        if bank_data and all(k in bank_data for k in ['account_name', 'account_number', 'bank_name', 'bank_code']):
            BankAccount.objects.create(
                vendor=vendor_profile,
                account_name=bank_data['account_name'],
                account_number=bank_data['account_number'],
                bank_name=bank_data['bank_name'],
                bank_code=bank_data['bank_code']
            )

        return vendor_profile



def update_bank_account_service(*, vendor_profile: VendorProfile, bank_data: dict) -> tuple[BankAccount, bool]:
    """
    Creates or updates the bank account details for an approved vendor.
    Returns (account_instance, created_boolean).
    """
    with transaction.atomic():
        account, created = BankAccount.objects.update_or_create(
            vendor=vendor_profile,
            defaults={
                'account_name': bank_data['account_name'],
                'account_number': bank_data['account_number'],
                'bank_name': bank_data['bank_name'],
                'bank_code': bank_data['bank_code']
            }
        )
        return account, created


# ---------------------------------------------------------------------------
# Identity verification (admin-reviewed). Designers submit; only staff decide.
# ---------------------------------------------------------------------------

def submit_verification_for_review(vendor: VendorProfile, *, nin_number=None, cac_number=None) -> VendorProfile:
    """Saves NIN/CAC (if given) and places the designer in the admin review queue.
    Never grants verification by itself."""
    from apps.common.notifications import send_verification_submitted_notification

    previous_submitted_at = vendor.verification_submitted_at
    if nin_number is not None:
        vendor.nin_number = (nin_number or '').strip() or None
    if cac_number is not None:
        vendor.cac_number = (cac_number or '').strip().upper() or None
    if not (vendor.nin_number or vendor.cac_number):
        raise ValidationError("Please provide your NIN or CAC registration number to request verification.")
    vendor.save()  # identity change -> PENDING_REVIEW via VendorProfile._sync_verification_with_identity

    # Resubmitting unchanged details after a rejection also goes back into the queue.
    if vendor.verification_status in (VerificationStatus.NOT_SUBMITTED, VerificationStatus.REJECTED):
        vendor.verification_status = VerificationStatus.PENDING_REVIEW
        vendor.verification_submitted_at = timezone.now()
        vendor.verification_rejection_reason = ''
        vendor.save(update_fields=['verification_status', 'verification_submitted_at', 'verification_rejection_reason', 'updated_at'])

    # Alert the review inbox only when this call actually (re)queued the designer.
    if (vendor.verification_status == VerificationStatus.PENDING_REVIEW
            and vendor.verification_submitted_at != previous_submitted_at):
        send_verification_submitted_notification(vendor)
    return vendor


def approve_verification(vendor: VendorProfile, reviewer) -> VendorProfile:
    from apps.common.notifications import send_verification_decision_notification

    if not (vendor.nin_number or vendor.cac_number):
        raise ValidationError(f"{vendor.store_name} has not submitted a NIN or CAC number.")
    vendor.verification_status = VerificationStatus.VERIFIED
    vendor.is_verified = True
    vendor.kyc_tier = KYCTier.TIER_3_ENTERPRISE if vendor.cac_number else KYCTier.TIER_2_VERIFIED
    vendor.verification_reviewed_at = timezone.now()
    vendor.verification_reviewed_by = reviewer
    vendor.verification_rejection_reason = ''
    vendor.save(update_fields=[
        'verification_status', 'is_verified', 'kyc_tier', 'verification_reviewed_at',
        'verification_reviewed_by', 'verification_rejection_reason', 'updated_at',
    ])
    send_verification_decision_notification(vendor)
    return vendor


def reject_verification(vendor: VendorProfile, reviewer, reason: str = '') -> VendorProfile:
    from apps.common.notifications import send_verification_decision_notification

    vendor.verification_status = VerificationStatus.REJECTED
    vendor.is_verified = False
    vendor.kyc_tier = KYCTier.TIER_1_STARTER
    vendor.verification_reviewed_at = timezone.now()
    vendor.verification_reviewed_by = reviewer
    vendor.verification_rejection_reason = reason or 'We could not confirm the NIN/CAC details you submitted.'
    vendor.save(update_fields=[
        'verification_status', 'is_verified', 'kyc_tier', 'verification_reviewed_at',
        'verification_reviewed_by', 'verification_rejection_reason', 'updated_at',
    ])
    send_verification_decision_notification(vendor)
    return vendor


# Order states where a shopper's money is (or was) with Aso and the order still matters.
_LIVE_ORDER_STATES = {'PAID', 'VENDOR_ACCEPTED', 'PREPARING', 'READY_FOR_PICKUP', 'PICKED_UP',
                      'OUT_FOR_DELIVERY', 'DELIVERED', 'DISPUTED'}


def designer_erase_summary(vendor: VendorProfile) -> dict:
    """What erasing this studio would touch, for the confirmation page."""
    orders = vendor.orders.all()
    return {
        'pieces': vendor.products.count(),
        'orders': orders.count(),
        'live_orders': orders.filter(order_status__in=_LIVE_ORDER_STATES).count(),
    }


@transaction.atomic
def erase_designer_personal_data(vendor: VendorProfile) -> dict:
    """
    Remove a designer's personal data while keeping order and money records consistent.
    Order rows cannot be deleted (they hold payment history), so instead everything that
    identifies the person is wiped and the account is closed:
      * account: name, phone, password; email replaced so the real one can sign up again
      * studio: name, links, description, address, NIN/CAC, logo, banner; hidden from the site
      * bank account details, saved addresses, chat messages they sent
      * pieces: hidden, with photos deleted and text cleared (orders keep their own snapshots)
    """
    import uuid
    from django.core.files.storage import default_storage
    from apps.accounts.models import Address, EmailVerificationCode
    from apps.orders.models import OrderMessage
    from apps.products.models import ProductMedia, ProductStatus
    from apps.products.services import invalidate_product_caches

    tag = uuid.uuid4().hex[:10]
    user = vendor.user
    summary = designer_erase_summary(vendor)

    def drop_file(url):
        if url and str(url).startswith('/media/'):
            name = str(url)[len('/media/'):]
            try:
                if default_storage.exists(name):
                    default_storage.delete(name)
            except Exception:
                pass

    # Pieces and their photos
    media = ProductMedia.objects.filter(product__vendor=vendor)
    for m in media:
        drop_file(m.url)
        drop_file(m.thumbnail_url)
    media.delete()
    for i, product in enumerate(vendor.products.all(), start=1):
        product.title = f'Removed piece {i}'
        product.slug = f'removed-{tag}-{i}'
        product.description = ''
        product.size_chart = {}
        product.is_active = False
        product.is_featured = False
        product.status = ProductStatus.ARCHIVED
        product.save()

    # Studio
    drop_file(vendor.logo_url)
    drop_file(vendor.banner_url)
    vendor.store_name = f'Removed studio {tag}'
    vendor.slug = f'removed-{tag}'
    vendor.description = None
    vendor.logo_url = None
    vendor.banner_url = None
    vendor.city = ''
    vendor.state = ''
    vendor.instagram_handle = None
    vendor.workshop_address = None
    vendor.landmark = None
    vendor.nin_number = None
    vendor.cac_number = None
    vendor.verification_rejection_reason = ''
    vendor.is_verified = False
    vendor.is_featured = False
    vendor.status = VendorStatus.SUSPENDED
    vendor.save()

    # Bank details: delete, unless a payout record points at them (then blank them).
    bank = getattr(vendor, 'bank_account', None)
    if bank is not None:
        if bank.payout_requests.exists():
            bank.account_name = 'Removed'
            bank.account_number = '0000000000'
            bank.recipient_code = None
            bank.save()
        else:
            bank.delete()

    # Account
    OrderMessage.objects.filter(sender=user).update(content='[removed]', original_content='[removed]')
    Address.objects.filter(user=user).delete()
    EmailVerificationCode.objects.filter(user=user).delete()
    user.email = f'erased-{tag}@erased.invalid'
    user.first_name = ''
    user.last_name = ''
    user.phone_number = None
    user.is_active = False
    user.set_unusable_password()
    user.save()

    # The admin history list shows old names; clear those too.
    from django.contrib.admin.models import LogEntry
    from django.contrib.contenttypes.models import ContentType
    for obj, label in ((vendor, vendor.store_name), (user, user.email)):
        LogEntry.objects.filter(content_type=ContentType.objects.get_for_model(obj),
                                object_id=str(obj.pk)).update(object_repr=label, change_message='')

    invalidate_product_caches()
    return summary


@transaction.atomic
def delete_test_studio(vendor: VendorProfile) -> None:
    """
    Delete a studio that only ever had test activity: its orders (with their payment,
    delivery and chat records and the designer earnings they created), pieces, photos,
    bank details and the owner's account. Refuses if a payout was ever sent (or is being
    sent) to the designer, because that is a real transfer that must stay on record.
    """
    from django.core.files.storage import default_storage
    from apps.orders.models import Order
    from apps.payouts.models import LedgerEntry, PayoutRequest
    from apps.products.models import ProductMedia
    from apps.products.services import invalidate_product_caches

    from apps.payouts.models import PayoutStatus
    if PayoutRequest.objects.filter(vendor=vendor,
                                    status__in=[PayoutStatus.SUCCESSFUL, PayoutStatus.PROCESSING]).exists():
        raise ValidationError('Money has been paid out to this designer, so the studio cannot be deleted. '
                              'Use "Erase personal data" instead.')
    user = vendor.user

    def drop_file(url):
        if url and str(url).startswith('/media/'):
            try:
                name = str(url)[len('/media/'):]
                if default_storage.exists(name):
                    default_storage.delete(name)
            except Exception:
                pass

    for m in ProductMedia.objects.filter(product__vendor=vendor):
        drop_file(m.url)
        drop_file(m.thumbnail_url)
    drop_file(vendor.logo_url)
    drop_file(vendor.banner_url)

    LedgerEntry.objects.filter(vendor=vendor).delete()
    PayoutRequest.objects.filter(vendor=vendor).delete()  # only unsent requests are left at this point
    Order.objects.filter(vendor=vendor).delete()  # items, payments, delivery and chat go with them
    if Order.objects.filter(customer=user).exists():
        # They also bought something as a shopper: keep that account, remove the studio only.
        vendor.delete()
    else:
        user.delete()  # studio, pieces, bank details, addresses and carts go with the account
    invalidate_product_caches()
