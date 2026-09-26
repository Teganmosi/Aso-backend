import uuid
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from .models import VendorProfile, BankAccount, VendorStatus


def get_vendor_by_slug(slug: str) -> VendorProfile:
    """
    Public storefront selector returning active registered vendor profile.
    Excludes suspended and rejected storefronts.
    Resilient matching:
    1. Exact slug match
    2. Case-insensitive slug match
    3. UUID match
    4. Slugified store_name match
    5. Partial slug or store_name match
    """
    qs = VendorProfile.objects.select_related('user').exclude(status__in=[VendorStatus.SUSPENDED, VendorStatus.REJECTED])
    cleaned = (slug or '').strip()

    # 1. Exact or case-insensitive match on slug
    vendor = qs.filter(slug__iexact=cleaned).first()
    if vendor:
        return vendor

    # 2. Check if slug is a valid UUID matching vendor ID
    try:
        val = uuid.UUID(cleaned)
        vendor = qs.filter(id=val).first()
        if vendor:
            return vendor
    except (ValueError, TypeError):
        pass

    # 3. Slugify lookup
    slugified = slugify(cleaned)
    if slugified:
        vendor = qs.filter(slug__iexact=slugified).first()
        if vendor:
            return vendor

    # 4. Partial / fuzzy prefix match on slug or store_name
    vendor = qs.filter(slug__icontains=cleaned).first()
    if vendor:
        return vendor

    vendor = qs.filter(store_name__icontains=cleaned).first()
    if vendor:
        return vendor

    # 5. Fallback 404
    return get_object_or_404(qs, slug=cleaned)


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
