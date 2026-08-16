from django.db import models
from django.conf import settings
from apps.common.models import UUIDModel
from apps.vendors.models import VendorProfile
from apps.products.models import ProductVariant


class Cart(UUIDModel):
    """
    Customer shopping cart entity enforcing Single-Vendor Cart Boundary.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart'
    )
    vendor = models.ForeignKey(
        VendorProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='carts'
    )

    class Meta:
        db_table = 'cart_cart'
        verbose_name = 'Cart'
        verbose_name_plural = 'Carts'

    def __str__(self):
        vendor_name = self.vendor.store_name if self.vendor else "No Vendor"
        return f"Cart of {self.user.email} ({vendor_name})"

    @property
    def subtotal_kobo(self) -> int:
        return sum(item.total_price_kobo for item in self.items.all())

    @property
    def subtotal_naira(self) -> float:
        return round(self.subtotal_kobo / 100.0, 2)

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items.all())

    def update_vendor_status(self):
        """
        Resets cart vendor to None if there are no items remaining in the cart.
        """
        if not self.items.exists():
            if self.vendor is not None:
                self.vendor = None
                self.save(update_fields=['vendor', 'updated_at'])


class CartItem(UUIDModel):
    """
    Individual item within a customer's single-vendor shopping cart.
    """
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items'
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='cart_items'
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'cart_cartitem'
        verbose_name = 'Cart Item'
        verbose_name_plural = 'Cart Items'
        unique_together = ('cart', 'variant')
        ordering = ['created_at']

    def __str__(self):
        return f"{self.quantity}x {self.variant} in Cart {self.cart.id}"

    @property
    def unit_price_kobo(self) -> int:
        return self.variant.price_kobo

    @property
    def unit_price_naira(self) -> float:
        return self.variant.price_naira

    @property
    def total_price_kobo(self) -> int:
        return self.unit_price_kobo * self.quantity

    @property
    def total_price_naira(self) -> float:
        return round(self.total_price_kobo / 100.0, 2)
