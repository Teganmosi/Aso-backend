from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from apps.orders.models import Order
from apps.orders.serializers import OrderSerializer, OrderCreateSerializer
from apps.orders.services import create_order_from_cart, accept_order, move_to_preparing, mark_ready_for_pickup


class OrderListCreateView(APIView):
    """
    GET: List all customer orders.
    POST: Create an order from active cart specifying shipping address ID.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = Order.objects.filter(
            customer=request.user
        ).select_related('vendor').prefetch_related('items').order_by('-created_at')

        serializer = OrderSerializer(orders, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        address = serializer.context['address']
        order = create_order_from_cart(user=request.user, address=address)

        order_refreshed = Order.objects.select_related('vendor').prefetch_related('items').get(id=order.id)
        return Response({
            'success': True,
            'message': 'Order created successfully.',
            'data': OrderSerializer(order_refreshed).data
        }, status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    """
    GET: Retrieve customer order detail summary.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = Order.objects.select_related('vendor').prefetch_related('items').get(
                id=order_id,
                customer=request.user
            )
        except Order.DoesNotExist:
            return Response({
                'detail': 'Order not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = OrderSerializer(order)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)



class OrderAcceptView(APIView):
    """
    POST: Accept a PAID order - transitions to VENDOR_ACCEPTED.
    Only the associated vendor can accept.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({
                'detail': 'Order not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            order = accept_order(order, request.user)
        except ValidationError as e:
            return Response({
                'detail': e.detail['detail']
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': True,
            'message': 'Order accepted successfully.',
            'data': OrderSerializer(order).data
        }, status=status.HTTP_200_OK)


class OrderPreparingView(APIView):
    """
    POST: Mark order as preparing - transitions to PREPARING.
    Only the associated vendor can mark as preparing.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({
                'detail': 'Order not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            order = move_to_preparing(order, request.user)
        except ValidationError as e:
            return Response({
                'detail': e.detail['detail']
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': True,
            'message': 'Order marked as preparing.',
            'data': OrderSerializer(order).data
        }, status=status.HTTP_200_OK)


class OrderReadyView(APIView):
    """
    POST: Mark order as ready for pickup - transitions to READY_FOR_PICKUP.
    Only the associated vendor can mark as ready.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({
                'detail': 'Order not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            order = mark_ready_for_pickup(order, request.user)
        except ValidationError as e:
            return Response({
                'detail': e.detail['detail']
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': True,
            'message': 'Order is ready for pickup.',
            'data': OrderSerializer(order).data
        }, status=status.HTTP_200_OK)
