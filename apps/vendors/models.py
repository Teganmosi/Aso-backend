from django.db import models
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

    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    review_count = models.PositiveIntegerField(default=0)


    class Meta:
        db_table = 'vendors_vendorprofile'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.store_name} ({self.status})"

    def save(self, *args, **kwargs):
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
