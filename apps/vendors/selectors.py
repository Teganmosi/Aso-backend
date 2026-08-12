from django.shortcuts import get_object_or_404
from .models import VendorProfile, BankAccount, VendorStatus


def get_vendor_by_slug(slug: str) -> VendorProfile:
    """
    Public storefront selector returning approved vendor profile.
    """
    return get_object_or_404(
        VendorProfile.objects.select_related('user'),
        slug=slug,
        status=VendorStatus.APPROVED
    )


def get_vendor_by_id(vendor_id) -> VendorProfile:
    return get_object_or_404(
        VendorProfile.objects.select_related('bank_account', 'user'),
        id=vendor_id
    )


def get_vendor_bank_account(vendor_profile: VendorProfile) -> BankAccount:
    """
    Returns linked BankAccount for vendor profile, or None if not set up.
    """
    return BankAccount.objects.filter(vendor=vendor_profile).first()


