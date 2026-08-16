from django.contrib import admin
from apps.cart.models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ['id', 'variant', 'quantity', 'unit_price_kobo', 'total_price_kobo', 'created_at']
    fields = ['variant', 'quantity', 'unit_price_kobo', 'total_price_kobo', 'created_at']


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'vendor', 'item_count', 'subtotal_naira', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['user__email', 'vendor__store_name']
    readonly_fields = ['id', 'user', 'subtotal_kobo', 'subtotal_naira', 'item_count', 'created_at', 'updated_at']
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'cart', 'variant', 'quantity', 'unit_price_naira', 'total_price_naira', 'created_at']
    search_fields = ['cart__user__email', 'variant__sku', 'variant__product__title']
    readonly_fields = ['id', 'cart', 'variant', 'unit_price_kobo', 'total_price_kobo', 'created_at', 'updated_at']
