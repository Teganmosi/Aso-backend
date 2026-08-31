from decimal import Decimal
from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import ValidationError
from apps.products.models import Product, Category, ApprovalStatus, ProductStatus



@transaction.atomic
def create_product(vendor_profile, validated_data: dict) -> Product:
    """
    Creates a new product for an approved vendor.
    Initial approval status defaults to PENDING.
    """
    category_id = validated_data.pop('category_id')
    category = Category.objects.get(id=category_id)

    status = validated_data.pop('status', ProductStatus.DRAFT)

    product = Product.objects.create(
        vendor=vendor_profile,
        category=category,
        approval_status=ApprovalStatus.PENDING,
        status=status,
        **validated_data
    )
    return product


@transaction.atomic
def update_product(product: Product, validated_data: dict) -> Product:
    """
    Updates an existing product.
    Resets approval_status to PENDING if core details change.
    """
    if 'category_id' in validated_data:
        category_id = validated_data.pop('category_id')
        product.category = Category.objects.get(id=category_id)

    requires_reapproval = False
    reapproval_fields = ['title', 'description', 'base_price_kobo']
    for field in reapproval_fields:
        if field in validated_data and getattr(product, field) != validated_data[field]:
            requires_reapproval = True

    for attr, value in validated_data.items():
        setattr(product, attr, value)

    if requires_reapproval:
        product.approval_status = ApprovalStatus.PENDING

    product.save()
    return product


@transaction.atomic
def approve_product(product: Product) -> Product:
    """
    Approves a product for public display and marks status as PUBLISHED.
    """
    product.approval_status = ApprovalStatus.APPROVED
    product.status = ProductStatus.PUBLISHED
    product.rejection_reason = None
    product.save(update_fields=['approval_status', 'status', 'rejection_reason'])
    return product


@transaction.atomic
def reject_product(product: Product, reason: str = None) -> Product:
    """
    Rejects a product with an optional reason.
    """
    product.approval_status = ApprovalStatus.REJECTED
    if reason:
        product.rejection_reason = reason
    product.save(update_fields=['approval_status', 'rejection_reason'])
    return product


@transaction.atomic
def delete_product(product: Product) -> None:
    """
    Soft deletes a product.
    """
    product.is_active = False
    product.save(update_fields=['is_active'])


from apps.products.models import ProductVariant, ProductMedia


@transaction.atomic
def create_product_variant(product: Product, validated_data: dict) -> ProductVariant:
    """
    Creates a new variant (size, color, stock) for a product.
    Rejects duplicate size/color combinations on the same product.
    """
    size = str(validated_data.get('size') or '').strip()
    color = validated_data.get('color')
    if ProductVariant.objects.filter(product=product, size=size, color=color).exists():
        raise ValidationError("A variant with this size and color already exists for this product.")

    variant = ProductVariant.objects.create(
        product=product,
        **validated_data
    )
    return variant


@transaction.atomic
def update_product_variant(variant: ProductVariant, validated_data: dict) -> ProductVariant:
    """
    Updates an existing product variant.
    Enforces the same (product, size, color) uniqueness constraint as creation
    whenever size or color is being changed.
    """
    if 'size' in validated_data or 'color' in validated_data:
        new_size = validated_data.get('size', variant.size)
        new_color = validated_data.get('color', variant.color)
        conflict = ProductVariant.objects.filter(
            product=variant.product,
            size=new_size,
            color=new_color
        ).exclude(pk=variant.pk)
        if conflict.exists():
            raise ValidationError("A variant with this size and color already exists for this product.")

    for attr, value in validated_data.items():
        setattr(variant, attr, value)
    variant.save()
    return variant


@transaction.atomic
def delete_product_variant(variant: ProductVariant) -> None:
    """
    Deactivates or deletes a product variant.
    """
    variant.delete()


@transaction.atomic
def attach_product_media(product: Product, validated_data: dict) -> ProductMedia:
    """
    Attaches a media asset (photo/video) to a product.
    If is_primary is True, unsets is_primary on existing media items.
    Enforces the vendor ownership boundary on internal storage URLs.
    """
    url = str(validated_data.get('url', ''))
    storage_base = getattr(settings, 'ASO_STORAGE_PUBLIC_BASE', '')
    if storage_base and url.startswith(storage_base):
        # Internal storage asset -> must belong to this vendor's namespace
        vendor_prefix = f"/vendors/{product.vendor_id}/"
        if vendor_prefix not in url:
            raise ValidationError("You can only attach media from your own vendor storage path.")

    is_primary = validated_data.get('is_primary', False)
    if is_primary:
        ProductMedia.objects.filter(product=product, is_primary=True).update(is_primary=False)
    elif not ProductMedia.objects.filter(product=product, is_primary=True).exists():
        validated_data['is_primary'] = True

    media = ProductMedia.objects.create(
        product=product,
        **validated_data
    )
    return media


@transaction.atomic
def delete_product_media(media: ProductMedia) -> None:
    """
    Deletes a product media item.
    """
    media.delete()


@transaction.atomic
def create_verified_review(customer, product: Product, order_item_id, rating: int, comment: str) -> 'Review':
    """
    Creates a verified buyer review linked to an individual completed OrderItem.
    Synchronously recalculates rating metrics on Product and VendorProfile.
    """
    from apps.orders.models import OrderItem, OrderStatus
    from apps.products.models import Review
    from django.db.models import Avg

    if not (1 <= rating <= 5):
        raise ValidationError({"rating": "Rating must be an integer between 1 and 5."})

    try:
        order_item = OrderItem.objects.select_related('order', 'variant__product').get(id=order_item_id)
    except OrderItem.DoesNotExist:
        raise ValidationError({"order_item_id": "Order item not found."})

    # Validate buyer ownership
    if order_item.order.customer_id != customer.id:
        raise ValidationError({"detail": "You can only review items you purchased."})

    # Validate order completion
    if order_item.order.order_status != OrderStatus.COMPLETED:
        raise ValidationError({"detail": "You can only review products from completed orders."})

    # Validate product association
    if order_item.variant and order_item.variant.product_id != product.id:
        raise ValidationError({"detail": "Order item does not belong to this product."})

    # Validate duplicate review
    if Review.objects.filter(order_item=order_item).exists():
        raise ValidationError({"detail": "You have already reviewed this purchased item."})

    # Create review
    review = Review.objects.create(
        order_item=order_item,
        product=product,
        vendor=product.vendor,
        customer=customer,
        rating=rating,
        comment=comment,
        is_verified_purchase=True
    )

    # Synchronously update Product aggregate rating
    product_reviews = Review.objects.filter(product=product)
    product_avg = product_reviews.aggregate(avg=Avg('rating'))['avg'] or 0.0
    product.average_rating = round(Decimal(str(product_avg)), 2)
    product.review_count = product_reviews.count()
    product.save(update_fields=['average_rating', 'review_count'])

    # Synchronously update VendorProfile aggregate rating
    vendor = product.vendor
    vendor_reviews = Review.objects.filter(vendor=vendor)
    vendor_avg = vendor_reviews.aggregate(avg=Avg('rating'))['avg'] or 0.0
    vendor.average_rating = round(Decimal(str(vendor_avg)), 2)
    vendor.review_count = vendor_reviews.count()
    vendor.save(update_fields=['average_rating', 'review_count'])

    return review


