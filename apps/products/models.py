from decimal import Decimal
from django.db import models
from django.utils.text import slugify
from apps.common.models import UUIDModel
from apps.vendors.models import VendorProfile


class Category(UUIDModel):
    """
    Hierarchical product category (e.g. Men, Women, Traditional, Agbada, Two-Piece, Streetwear).
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    description = models.TextField(null=True, blank=True)
    image_url = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'products_category'
        verbose_name_plural = 'Categories'
        ordering = ['display_order', 'name']

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} -> {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "category"
        else:
            base_slug = self.slug

        slug = base_slug
        counter = 1
        qs = Category.objects.filter(slug=slug)
        if self.pk:
            qs = qs.exclude(pk=self.pk)

        while qs.exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
            qs = Category.objects.filter(slug=slug)
            if self.pk:
                qs = qs.exclude(pk=self.pk)

        self.slug = slug
        super().save(*args, **kwargs)


class ApprovalStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Approval'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


class ProductStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    PUBLISHED = 'PUBLISHED', 'Published'
    ARCHIVED = 'ARCHIVED', 'Archived'


class Product(UUIDModel):
    """
    Master product catalog model owned by an approved vendor.
    """
    vendor = models.ForeignKey(
        VendorProfile,
        on_delete=models.CASCADE,
        related_name='products'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products'
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField()
    base_price_kobo = models.PositiveBigIntegerField(
        help_text="Base price in Kobo (e.g. 7,500,000 Kobo = N75,000)"
    )
    preparation_time_days = models.PositiveIntegerField(
        default=3,
        help_text="Estimated preparation / tailoring SLA time in days"
    )
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )
    status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.DRAFT
    )
    is_active = models.BooleanField(default=True)
    rejection_reason = models.TextField(null=True, blank=True)

    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    review_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'products_product'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.vendor.store_name}) - {self.approval_status}"

    @property
    def base_price_naira(self) -> float:
        return round(self.base_price_kobo / 100.0, 2)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "product"
        else:
            base_slug = self.slug

        slug = base_slug
        counter = 1
        qs = Product.objects.filter(slug=slug)
        if self.pk:
            qs = qs.exclude(pk=self.pk)

        while qs.exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
            qs = Product.objects.filter(slug=slug)
            if self.pk:
                qs = qs.exclude(pk=self.pk)

        self.slug = slug
        super().save(*args, **kwargs)
