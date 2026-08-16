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


class MediaType(models.TextChoices):
    IMAGE = 'IMAGE', 'Image'
    VIDEO = 'VIDEO', 'Video'


class ProductVariant(UUIDModel):
    """
    Product variant representing specific size, color, SKU, and inventory stock level.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    size = models.CharField(max_length=50, help_text="Size e.g. S, M, L, XL, XXL, Custom")
    color = models.CharField(max_length=50, null=True, blank=True, help_text="Color e.g. Navy Blue, Gold, Black")
    sku = models.CharField(max_length=100, unique=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    price_override_kobo = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        help_text="Optional price override in Kobo if variant price differs from base_price_kobo"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'products_productvariant'
        ordering = ['size', 'color']

    def __str__(self):
        color_str = f" / {self.color}" if self.color else ""
        return f"{self.product.title} - {self.size}{color_str} (Stock: {self.stock_quantity})"

    @property
    def price_kobo(self) -> int:
        if self.price_override_kobo is not None:
            return self.price_override_kobo
        return self.product.base_price_kobo

    @property
    def price_naira(self) -> float:
        return round(self.price_kobo / 100.0, 2)

    def save(self, *args, **kwargs):
        if not self.sku:
            v_code = str(self.product.vendor.id)[:6].upper()
            p_code = str(self.product.id)[:6].upper()
            size_code = slugify(self.size).upper() or "SZ"
            color_code = slugify(self.color or "DEF").upper()
            base_sku = f"ASO-{v_code}-{p_code}-{size_code}-{color_code}"
            
            sku = base_sku
            counter = 1
            qs = ProductVariant.objects.filter(sku=sku)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            while qs.exists():
                sku = f"{base_sku}-{counter}"
                counter += 1
                qs = ProductVariant.objects.filter(sku=sku)
                if self.pk:
                    qs = qs.exclude(pk=self.pk)
            self.sku = sku
        super().save(*args, **kwargs)


class ProductMedia(UUIDModel):
    """
    Product media attachment (photos, lookbook images, short videos).
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='media'
    )
    media_type = models.CharField(
        max_length=10,
        choices=MediaType.choices,
        default=MediaType.IMAGE
    )
    url = models.TextField(help_text="Public S3/R2 CDN URL of the asset")
    thumbnail_url = models.TextField(null=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False, help_text="Designates primary thumbnail image")

    class Meta:
        db_table = 'products_productmedia'
        ordering = ['display_order', '-is_primary', 'created_at']

    def __str__(self):
        return f"{self.media_type} for {self.product.title} (Order: {self.display_order})"

