from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from apps.orders.models import Order
from apps.deliveries.models import Delivery
from apps.deliveries.serializers import DeliverySerializer, DeliveryStatusUpdateSerializer
from apps.deliveries.services import update_delivery_status


class OrderDeliveryDetailView(APIView):
    """
    GET: Retrieve delivery tracking details for an order.
    Permission: Customers can view their own orders' delivery tracking.
    Vendors can view deliveries for their own orders.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = Order.objects.select_related('vendor').get(id=order_id)
        except Order.DoesNotExist:
            return Response({
                'detail': 'Order not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Check permission: customer, vendor user, or staff
        if not (order.customer == request.user or order.vendor.user == request.user or request.user.is_staff):
            return Response({
                'detail': 'You do not have permission to view this delivery.'
            }, status=status.HTTP_403_FORBIDDEN)

        delivery = getattr(order, 'delivery', None)
        if not delivery:
            return Response({
                'detail': 'No delivery record found for this order.'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = DeliverySerializer(delivery)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)


class DeliveryStatusUpdateView(APIView):
    """
    POST: Update delivery status.
    Permission: Vendors or staff users can update delivery status.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, delivery_id):
        try:
            delivery = Delivery.objects.get(id=delivery_id)
        except Delivery.DoesNotExist:
            return Response({
                'detail': 'Delivery not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Check permissions: vendor or staff
        if delivery.order.vendor.user != request.user and not request.user.is_staff:
            return Response({
                'detail': 'You do not have permission to update this delivery.'
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = DeliveryStatusUpdateSerializer(delivery, data=request.data)
        if serializer.is_valid(raise_exception=True):
            try:
                delivery = update_delivery_status(
                    delivery,
                    serializer.validated_data['status'],
                    serializer.validated_data.get('notes')
                )
                return Response({
                    'success': True,
                    'message': 'Delivery status updated successfully.',
                    'data': DeliverySerializer(delivery).data
                }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({
                    'detail': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)