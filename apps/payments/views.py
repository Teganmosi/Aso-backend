from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from apps.orders.models import Order, OrderStatus
from .models import PaymentRequest
from .serializers import PaymentRequestSerializer
from .services import initialize_payment, verify_and_process_webhook


class PaymentInitializeView(APIView):
    """
    POST: Initialize payment for an order via Paystack.
    Request body: { "order_id": "<uuid>" }
    Response: { authorization_url, reference, amount, currency }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        order_id = request.data.get('order_id')
        if not order_id:
            return Response({
                'detail': 'order_id is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Only the order customer can initialize payment
        order = get_object_or_404(Order, id=order_id, customer=request.user)

        # Validate order state: only PENDING_PAYMENT orders that haven't expired can initialize
        if order.order_status != OrderStatus.PENDING_PAYMENT:
            return Response({
                'detail': f'Cannot initialize payment for order with status "{order.get_order_status_display()}".'
            }, status=status.HTTP_400_BAD_REQUEST)

        if order.is_expired:
            return Response({
                'detail': 'Cannot initialize payment: this order has exceeded the 30-minute payment reservation window.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Initialize payment
        payment_request = initialize_payment(order)

        serializer = PaymentRequestSerializer(payment_request)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)


class PaymentWebhookView(APIView):
    """
    POST: Receive and process Paystack webhook events.
    This endpoint verifies the HMAC-SHA512 signature and processes
    charge.success/charge.failed events, transitioning order status
    from PENDING_PAYMENT → PAID or marking as FAILED.
    """
    permission_classes = []  # Paystack webhooks are not authenticated via Django

    def post(self, request):
        payload = request.body
        signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')

        # Verify and process webhook
        sig_verified, payment_request, message = \
            verify_and_process_webhook(payload, signature)

        if not sig_verified:
            return Response({
                'detail': message
            }, status=status.HTTP_400_BAD_REQUEST)

        # Return appropriate response based on processing result
        if payment_request:
            return Response({
                'success': True,
                'data': {
                    'reference': payment_request.reference,
                    'status': payment_request.status,
                    'order_status': payment_request.order.order_status
                        if payment_request.order else None,
                }
            }, status=status.HTTP_200_OK)

        return Response({
            'success': True,
            'data': {'message': message}
        }, status=status.HTTP_200_OK)