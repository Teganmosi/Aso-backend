from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from apps.common.models import UUIDModel
from apps.accounts.models import User

class VendorStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Approval'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    SUSPENDED = 'SUSPENDED', 'Suspended'


class KYCTier(models.TextChoices):
    TIER_1_STARTER = 'TIER_1_STARTER', 'Tier 1: Starter (Basic Verification)'
    TIER_2_VERIFIED = 'TIER_2_VERIFIED', 'Tier 2: Verified Designer (ID & NUBAN Verified)'
    TIER_3_ENTERPRISE = 'TIER_3_ENTERPRISE', 'Tier 3: Enterprise Partner (Studio Inspected & CAC)'


class VerificationStatus(models.TextChoices):
    """Identity (NIN/CAC) verification review state. Independent of storefront `status`:
    designers can sell while unverified, but only an Aso admin can grant VERIFIED."""
    NOT_SUBMITTED = 'NOT_SUBMITTED', 'Not Submitted'
    PENDING_REVIEW = 'PENDING_REVIEW', 'Pending Admin Review'
    VERIFIED = 'VERIFIED', 'Verified'
    REJECTED = 'REJECTED', 'Rejected'



class VendorProfile(UUIDModel):
    """
    Storefront profile for fashion designers / vendors.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='vendor_profile')
    store_name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)
    logo_url = models.TextField(null=True, blank=True)
    banner_url = models.TextField(null=True, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=VendorStatus.choices, default=VendorStatus.PENDING)
    kyc_tier = models.CharField(max_length=30, choices=KYCTier.choices, default=KYCTier.TIER_1_STARTER)
    is_verified = models.BooleanField(default=False)
    
    # Verification & Pickup Location Fields
    instagram_handle = models.CharField(max_length=100, null=True, blank=True)
    workshop_address = models.TextField(null=True, blank=True)
    landmark = models.CharField(max_length=255, null=True, blank=True)
    nin_number = models.CharField(max_length=20, null=True, blank=True)
    cac_number = models.CharField(max_length=50, null=True, blank=True)

    # Admin-reviewed identity verification (is_verified mirrors verification_status == VERIFIED)
    verification_status = models.CharField(
        max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.NOT_SUBMITTED, db_index=True
    )
    verification_submitted_at = models.DateTimeField(null=True, blank=True)
    verification_reviewed_at = models.DateTimeField(null=True, blank=True)
    verification_reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    verification_rejection_reason = models.TextField(blank=True, default='')

    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    review_count = models.PositiveIntegerField(default=0)


    class Meta:
        db_table = 'vendors_vendorprofile'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.store_name} ({self.status})"

    @property
    def has_started_verification(self) -> bool:
        """True once NIN/CAC has been submitted and is awaiting review or approved.
        Drives the "Verification in Progress" UI; storefront `status` is unrelated."""
        return self.verification_status in (VerificationStatus.PENDING_REVIEW, VerificationStatus.VERIFIED)

    _IDENTITY_FIELDS = ('nin_number', 'cac_number')
    _VERIFICATION_FIELDS = (
        'verification_status', 'verification_submitted_at', 'verification_reviewed_at',
        'verification_reviewed_by', 'verification_rejection_reason', 'is_verified', 'kyc_tier',
    )

    def _sync_verification_with_identity(self, update_fields):
        """Any change to NIN/CAC (by any code path) sends the designer back to admin review and
        removes the Verified badge, so a verified identity can never be silently swapped."""
        if update_fields is not None and not set(self._IDENTITY_FIELDS) & set(update_fields):
            return update_fields
        new = {f: (getattr(self, f) or '').strip() for f in self._IDENTITY_FIELDS}
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).values(*self._IDENTITY_FIELDS).first()
            old = {f: ((old or {}).get(f) or '').strip() for f in self._IDENTITY_FIELDS}
        else:
            old = {f: '' for f in self._IDENTITY_FIELDS}
        if new == old:
            return update_fields

        self.is_verified = False
        self.kyc_tier = KYCTier.TIER_1_STARTER
        self.verification_reviewed_at = None
        self.verification_reviewed_by = None
        self.verification_rejection_reason = ''
        if any(new.values()):
            self.verification_status = VerificationStatus.PENDING_REVIEW
            self.verification_submitted_at = timezone.now()
        else:
            self.verification_status = VerificationStatus.NOT_SUBMITTED
            self.verification_submitted_at = None
        if update_fields is not None:
            update_fields = list(set(update_fields) | set(self._VERIFICATION_FIELDS))
        return update_fields

    def save(self, *args, **kwargs):
        update_fields = self._sync_verification_with_identity(kwargs.get('update_fields'))
        if update_fields is not None:
            kwargs['update_fields'] = update_fields
        if not self.slug:
            base_slug = slugify(self.store_name) or "store"
        else:
            base_slug = self.slug

        slug = base_slug
        counter = 1
        qs = VendorProfile.objects.filter(slug=slug)
        if self.pk:
            qs = qs.exclude(pk=self.pk)

        while qs.exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
            qs = VendorProfile.objects.filter(slug=slug)
            if self.pk:
                qs = qs.exclude(pk=self.pk)

        self.slug = slug
        super().save(*args, **kwargs)


class BankAccount(UUIDModel):
    """
    Bank account details for vendor payout withdrawals.
    """
    vendor = models.OneToOneField(VendorProfile, on_delete=models.CASCADE, related_name='bank_account')
    account_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=10)
    bank_name = models.CharField(max_length=100)
    bank_code = models.CharField(max_length=20)
    recipient_code = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'vendors_bankaccount'

    def __str__(self):
        return f"{self.account_name} - {self.bank_name} ({self.account_number})"
