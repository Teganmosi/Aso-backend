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
