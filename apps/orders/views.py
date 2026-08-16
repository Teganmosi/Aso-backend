from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from apps.orders.models import Order
from apps.orders.serializers import OrderSerializer, OrderCreateSerializer
from apps.orders.services import create_order_from_cart


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
