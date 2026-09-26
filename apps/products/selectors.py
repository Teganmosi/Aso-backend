from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404

from apps.products.models import Category, Product, ApprovalStatus, ProductStatus
from apps.vendors.models import VendorStatus


def get_active_categories(parent_only=True):
    """
    Returns active category queryset. If parent_only is True, returns root categories
    with pre-fetched children.
    """
    qs = Category.objects.filter(is_active=True)
    if parent_only:
        qs = qs.filter(parent__isnull=True).prefetch_related('children')
    return qs


def get_category_by_slug(slug: str) -> Category:
    """
    Retrieves an active category by its slug.
    """
    return get_object_or_404(Category, slug=slug, is_active=True)


def _public_product_qs():
    """
    Base queryset for products visible on the public marketplace:
    - Published products (status == PUBLISHED, is_active == True)
    - Vendor not SUSPENDED
    - approval_status not REJECTED
    """
    return Product.objects.filter(
        status=ProductStatus.PUBLISHED,
        is_active=True
    ).exclude(
        vendor__status=VendorStatus.SUSPENDED
    ).exclude(
        approval_status=ApprovalStatus.REJECTED
    ).select_related('vendor', 'category').prefetch_related('media', 'variants')


def get_public_products(
    search=None,
    category_slug=None,
    collection_slug=None,
    vendor_slug=None,
    min_price=None,
    max_price=None,
    min_lead_time=None,
    max_lead_time=None,
    sort_by=None
):
    """
    Query selector for public product catalog with search, filtering, and sorting.
    Supports collection/gender root filtering, category child filtering, vendor, price, SLA lead times, and sorting.
    """
    qs = _public_product_qs()

    # Search filter across title, description, and store name
    if search:
        search_term = str(search).strip()
        if search_term:
            qs = qs.filter(
                Q(title__icontains=search_term) |
                Q(description__icontains=search_term) |
                Q(vendor__store_name__icontains=search_term)
            )

    # Collection/Gender filter (e.g. 'men', 'women', 'traditional-bridal')
    if collection_slug:
        try:
            col_cat = Category.objects.get(slug=collection_slug, is_active=True)
            col_child_ids = list(col_cat.children.filter(is_active=True).values_list('id', flat=True))
            col_cat_ids = [col_cat.id] + col_child_ids
            qs = qs.filter(category_id__in=col_cat_ids)
        except Category.DoesNotExist:
            qs = Product.objects.none()

    # Category filter (specific category or subcategory)
    if category_slug:
        try:
            category = Category.objects.get(slug=category_slug, is_active=True)
            child_ids = list(category.children.filter(is_active=True).values_list('id', flat=True))
            category_ids = [category.id] + child_ids
            qs = qs.filter(category_id__in=category_ids)
        except Category.DoesNotExist:
            qs = Product.objects.none()

    # Vendor filter (supports vendor slug or vendor UUID)
    if vendor_slug:
        import uuid
        try:
            val_uuid = uuid.UUID(str(vendor_slug))
            qs = qs.filter(Q(vendor_id=val_uuid) | Q(vendor__slug=vendor_slug))
        except (ValueError, TypeError, AttributeError):
            qs = qs.filter(vendor__slug=vendor_slug)

    # Price range filters (in Kobo)
    if min_price is not None:
        try:
            min_kobo = int(min_price)
            qs = qs.filter(base_price_kobo__gte=min_kobo)
        except (ValueError, TypeError):
            pass

    if max_price is not None:
        try:
            max_kobo = int(max_price)
            qs = qs.filter(base_price_kobo__lte=max_kobo)
        except (ValueError, TypeError):
            pass

    # Lead time / preparation SLA filters (in days)
    if min_lead_time is not None:
        try:
            min_days = int(min_lead_time)
            qs = qs.filter(preparation_time_days__gte=min_days)
        except (ValueError, TypeError):
            pass

    if max_lead_time is not None:
        try:
            max_days = int(max_lead_time)
            qs = qs.filter(preparation_time_days__lte=max_days)
        except (ValueError, TypeError):
            pass

    # Sorting
    if sort_by == 'price_asc':
        qs = qs.order_by('base_price_kobo', '-created_at')
    elif sort_by == 'price_desc':
        qs = qs.order_by('-base_price_kobo', '-created_at')
    elif sort_by == 'rating':
        qs = qs.order_by('-average_rating', '-review_count', '-created_at')
    elif sort_by == 'newest' or sort_by == '-created_at':
        qs = qs.order_by('-created_at')
    else:
        qs = qs.order_by('-created_at')

    return qs


def get_public_product_by_slug(slug: str) -> Product:
    """
    Retrieves a single public, approved, published product by slug.
    """
    return get_object_or_404(_public_product_qs(), slug=slug)


def get_public_product_by_id_or_slug(identifier: str):
    """
    Retrieves a single public, approved, published product by UUID or slug.
    Returns None when the identifier matches no visible product.
    """
    qs = _public_product_qs()

    # Try UUID lookup first (identifier may be a product id)
    try:
        UUID(str(identifier))
        product = qs.filter(id=identifier).first()
        if product is not None:
            return product
    except (ValueError, TypeError, ValidationError):
        pass

    # Fall back to slug (also covers UUID-shaped strings with no matching product)
    return qs.filter(slug=identifier).first()


def get_product_child_or_none(queryset, identifier: str):
    """
    Safe UUID lookup for product children (variants / media).
    Returns None for missing or non-UUID identifiers instead of raising
    ValidationError (which would surface as HTTP 500).
    """
    try:
        return queryset.get(id=identifier)
    except (queryset.model.DoesNotExist, ValueError, ValidationError):
        return None


def get_vendor_products(vendor_profile):
    """
    Returns all products belonging to a vendor.
    """
    return Product.objects.filter(
        vendor=vendor_profile,
        is_active=True
    ).select_related('category', 'vendor').prefetch_related('media', 'variants').order_by('-created_at')


def get_vendor_product_by_id_or_slug(vendor_profile, identifier: str) -> Product:
    """
    Retrieves a vendor's product by ID or slug.
    Catches Product.DoesNotExist, ValueError, and ValidationError for non-UUID slug strings.
    """
    qs = Product.objects.filter(vendor=vendor_profile, is_active=True).select_related('category', 'vendor').prefetch_related('media', 'variants')
    try:
        return qs.get(id=identifier)
    except (Product.DoesNotExist, ValueError, ValidationError):
        return get_object_or_404(qs, slug=identifier)
