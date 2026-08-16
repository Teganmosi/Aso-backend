from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from apps.cart.models import Cart, CartItem
from apps.cart.serializers import (
    CartSerializer,
    AddCartItemSerializer,
    UpdateCartItemSerializer
)


def get_or_create_cart(user, select_for_update: bool = False) -> Cart:
    if select_for_update:
        cart, _ = Cart.objects.select_for_update().get_or_create(user=user)
        return cart
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


class CartDetailView(APIView):
    """
    GET: Retrieve customer cart details.
    DELETE: Clear all items from the customer cart.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart = get_or_create_cart(request.user)
        # Prefetch related data for optimal query count
        cart = Cart.objects.prefetch_related(
            'items__variant__product__media',
            'items__variant__product__vendor'
        ).select_related('vendor').get(id=cart.id)
        
        serializer = CartSerializer(cart)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def delete(self, request):
        with transaction.atomic():
            cart = get_or_create_cart(request.user, select_for_update=True)
            cart.items.all().delete()
            cart.vendor = None
            cart.save(update_fields=['vendor', 'updated_at'])
        
        cart_refreshed = Cart.objects.prefetch_related(
            'items__variant__product__media',
            'items__variant__product__vendor'
        ).select_related('vendor').get(id=cart.id)
        serializer = CartSerializer(cart_refreshed)
        return Response({
            'success': True,
            'message': 'Cart cleared successfully.',
            'data': serializer.data
        }, status=status.HTTP_200_OK)


class CartItemAddView(APIView):
    """
    POST: Add a product variant to the cart, enforcing Single-Vendor Cart Boundary.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AddCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        variant = serializer.validated_data['variant']
        requested_qty = serializer.validated_data['quantity']
        variant_vendor = variant.product.vendor

        with transaction.atomic():
            cart = get_or_create_cart(request.user, select_for_update=True)

            # Single-Vendor Cart Enforcement
            if cart.vendor is not None and cart.vendor != variant_vendor and cart.items.exists():
                return Response({
                    'detail': f"Your cart already contains items from {cart.vendor.store_name}. Checkout or clear cart before adding items from another designer."
                }, status=status.HTTP_400_BAD_REQUEST)

            existing_item = cart.items.filter(variant=variant).first()
            if existing_item:
                new_qty = existing_item.quantity + requested_qty
                if new_qty > variant.stock_quantity:
                    return Response({
                        'detail': f"Cannot add {requested_qty} more units. Total quantity ({new_qty}) would exceed available stock ({variant.stock_quantity})."
                    }, status=status.HTTP_400_BAD_REQUEST)
                existing_item.quantity = new_qty
                existing_item.save(update_fields=['quantity', 'updated_at'])
            else:
                if requested_qty > variant.stock_quantity:
                    return Response({
                        'detail': f"Requested quantity ({requested_qty}) exceeds available stock ({variant.stock_quantity})."
                    }, status=status.HTTP_400_BAD_REQUEST)
                CartItem.objects.create(
                    cart=cart,
                    variant=variant,
                    quantity=requested_qty
                )

            if cart.vendor != variant_vendor:
                cart.vendor = variant_vendor
                cart.save(update_fields=['vendor', 'updated_at'])

        cart_refreshed = Cart.objects.prefetch_related(
            'items__variant__product__media',
            'items__variant__product__vendor'
        ).select_related('vendor').get(id=cart.id)

        return Response({
            'success': True,
            'message': 'Item added to cart successfully.',
            'data': CartSerializer(cart_refreshed).data
        }, status=status.HTTP_200_OK)


class CartItemDetailView(APIView):
    """
    PATCH: Update cart item quantity.
    DELETE: Remove specific item from cart.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, item_id):
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_qty = serializer.validated_data['quantity']

        with transaction.atomic():
            cart = get_or_create_cart(request.user, select_for_update=True)

            try:
                item = cart.items.select_related('variant').get(id=item_id)
            except CartItem.DoesNotExist:
                return Response({
                    'detail': 'Cart item not found.'
                }, status=status.HTTP_404_NOT_FOUND)

            if new_qty == 0:
                item.delete()
                cart.update_vendor_status()
            else:
                if new_qty > item.variant.stock_quantity:
                    return Response({
                        'detail': f"Requested quantity ({new_qty}) exceeds available stock ({item.variant.stock_quantity})."
                    }, status=status.HTTP_400_BAD_REQUEST)
                item.quantity = new_qty
                item.save(update_fields=['quantity', 'updated_at'])

        cart_refreshed = Cart.objects.prefetch_related(
            'items__variant__product__media',
            'items__variant__product__vendor'
        ).select_related('vendor').get(id=cart.id)

        return Response({
            'success': True,
            'message': 'Cart item updated successfully.',
            'data': CartSerializer(cart_refreshed).data
        }, status=status.HTTP_200_OK)

    def delete(self, request, item_id):
        with transaction.atomic():
            cart = get_or_create_cart(request.user, select_for_update=True)

            try:
                item = cart.items.get(id=item_id)
            except CartItem.DoesNotExist:
                return Response({
                    'detail': 'Cart item not found.'
                }, status=status.HTTP_404_NOT_FOUND)

            item.delete()
            cart.update_vendor_status()

        cart_refreshed = Cart.objects.prefetch_related(
            'items__variant__product__media',
            'items__variant__product__vendor'
        ).select_related('vendor').get(id=cart.id)

        return Response({
            'success': True,
            'message': 'Item removed from cart.',
            'data': CartSerializer(cart_refreshed).data
        }, status=status.HTTP_200_OK)

