from django.db import transaction
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
