import json
import base64
import logging
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Q
from apps.orders.models import Order
from apps.accounts.models import Address
from apps.vendors.models import VendorProfile
from apps.deliveries.models import Delivery, DeliveryStatus
from apps.deliveries.serializers import DeliverySerializer, DeliveryStatusUpdateSerializer
from apps.deliveries.services import update_delivery_status
from apps.deliveries.dellyman_client import dellyman_client

logger = logging.getLogger(__name__)


class OrderDeliveryDetailView(APIView):
    """
    GET: Retrieve delivery tracking details for an order.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = Order.objects.select_related('vendor').get(id=order_id)
        except Order.DoesNotExist:
            return Response({'detail': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not (order.customer == request.user or order.vendor.user == request.user or request.user.is_staff):
            return Response({'detail': 'You do not have permission to view this delivery.'}, status=status.HTTP_403_FORBIDDEN)

        delivery = getattr(order, 'delivery', None)
        if not delivery:
            return Response({'detail': 'No delivery record found for this order.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = DeliverySerializer(delivery)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)


class OrderWaybillView(APIView):
    """
    GET: Retrieve digital shipping waybill label (Base64 or direct binary PDF download).
    """
    permission_classes = [IsAuthenticated]
    format_kwarg = None

    def perform_content_negotiation(self, request, force=False):
        try:
            return super().perform_content_negotiation(request, force=force)
        except Exception:
            from rest_framework.renderers import JSONRenderer
            return (JSONRenderer(), 'application/json')

    def get(self, request, order_id):
        try:
            order = Order.objects.select_related('vendor', 'customer').get(id=order_id)
        except Order.DoesNotExist:
            return Response({'detail': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not (order.customer == request.user or order.vendor.user == request.user or request.user.is_staff):
            return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        delivery = getattr(order, 'delivery', None)
        if not delivery or not delivery.package_label_base64:
            return Response({'detail': 'Waybill label not available yet. Garment must be marked Ready for Pickup.'}, status=status.HTTP_404_NOT_FOUND)

        # Check if direct PDF download requested
        is_pdf_format = request.query_params.get('format') == 'pdf' or request.query_params.get('download') in ['pdf', '1', 'true']
        if is_pdf_format:
            try:
                pdf_bytes = base64.b64decode(delivery.package_label_base64)
                response = HttpResponse(pdf_bytes, content_type='application/pdf')
                response['Content-Disposition'] = f'inline; filename="waybill_{order.order_number}.pdf"'
                return response
            except Exception as e:
                logger.error(f"Error decoding waybill PDF: {e}")

        return Response({
            'success': True,
            'order_number': order.order_number,
            'tracking_id': delivery.dellyman_tracking_id or delivery.tracking_number,
            'order_code': delivery.dellyman_order_code,
            'package_label': delivery.package_label_base64
        }, status=status.HTTP_200_OK)


class DeliveryQuoteView(APIView):
    """
    POST: Calculate live dynamic shipping quote via Dellyman Logistics.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        address_id = request.data.get('address_id')
        vendor_id = request.data.get('vendor_id')

        if not address_id:
            return Response({'detail': 'address_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            dest_address = Address.objects.get(id=address_id, user=request.user)
        except Address.DoesNotExist:
            return Response({'detail': 'Address not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Default studio address in Lagos if vendor workshop address not set
        pickup_addr = "12 Admiralty Way, Lekki Phase 1, Lagos, Nigeria"
        vendor_city = "Ikeja"
        vendor_state = "Lagos"
        if vendor_id:
            try:
                vendor = VendorProfile.objects.get(id=vendor_id)
                if vendor.workshop_address:
                    pickup_addr = f"{vendor.workshop_address}, {vendor.city or 'Lagos'}, {vendor.state or 'Lagos'}, Nigeria"
                if vendor.city:
                    vendor_city = vendor.city
                if vendor.state:
                    vendor_state = vendor.state
            except VendorProfile.DoesNotExist:
                pass

        dest_addr_str = f"{dest_address.street_address}, {dest_address.city}, {dest_address.state}, Nigeria"
        if dest_address.landmark:
            dest_addr_str = f"{dest_address.street_address} (Near {dest_address.landmark}), {dest_address.city}, {dest_address.state}, Nigeria"

        # Check if intra-state or interstate
        dest_state = (dest_address.state or 'Lagos').strip()
        is_interstate = dest_state.lower() != vendor_state.lower()

        # If Dellyman API key is not configured, do NOT show a fake price (e.g. 1850).
        if not dellyman_client.api_key:
            return Response({
                'success': True,
                'has_live_quote': False,
                'delivery_fee_naira': None,
                'delivery_fee_kobo': 0,
                'eta': "Interstate Delivery (2-3 Days)" if is_interstate else "Same-Day / Next-Day Delivery",
                'carrier': "Dellyman Logistics",
                'message': "Live rate pending API configuration. Courier fee confirmed at dispatch."
            }, status=status.HTTP_200_OK)

        try:
            if is_interstate:
                quote_res = dellyman_client.get_interstate_quote(
                    pickup_state=vendor_state,
                    pickup_city=vendor_city,
                    pickup_address=pickup_addr,
                    delivery_state=dest_state,
                    delivery_city=dest_address.city or dest_state,
                    delivery_address=dest_addr_str
                )
                fare_val = quote_res.get('TotalPrice') or quote_res.get('PayableAmount')
                if fare_val and float(fare_val) > 0:
                    fare = float(fare_val)
                    return Response({
                        'success': True,
                        'has_live_quote': True,
                        'delivery_fee_naira': fare,
                        'delivery_fee_kobo': int(fare * 100),
                        'eta': "Interstate Delivery (2-3 Days)",
                        'carrier': quote_res.get('Name') or "Dellyman Interstate Express"
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({
                        'success': True,
                        'has_live_quote': False,
                        'delivery_fee_naira': None,
                        'delivery_fee_kobo': 0,
                        'eta': "Interstate Delivery (2-3 Days)",
                        'carrier': "Dellyman Interstate Express",
                        'message': "Interstate courier quote will be calculated upon dispatch."
                    }, status=status.HTTP_200_OK)
            else:
                quote_res = dellyman_client.get_quotes(
                    pickup_address=pickup_addr,
                    delivery_address=dest_addr_str
                )
                companies = quote_res.get('Companies', [])
                if companies:
                    fare_val = companies[0].get('TotalPrice') or companies[0].get('PayableAmount')
                    if fare_val and float(fare_val) > 0:
                        fare = float(fare_val)
                        return Response({
                            'success': True,
                            'has_live_quote': True,
                            'delivery_fee_naira': fare,
                            'delivery_fee_kobo': int(fare * 100),
                            'eta': "Same-Day / Next-Day Delivery",
                            'carrier': companies[0].get('Name') or "Dellyman Logistics"
                        }, status=status.HTTP_200_OK)

                return Response({
                    'success': True,
                    'has_live_quote': False,
                    'delivery_fee_naira': None,
                    'delivery_fee_kobo': 0,
                    'eta': "Same-Day / Next-Day Delivery",
                    'carrier': "Dellyman Logistics",
                    'message': "Courier quote will be calculated upon dispatch."
                }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Quote calculation error: {e}")
            return Response({
                'success': True,
                'has_live_quote': False,
                'delivery_fee_naira': None,
                'delivery_fee_kobo': 0,
                'eta': "Standard Courier Delivery",
                'carrier': "Dellyman Logistics",
                'message': "Delivery fee will be calculated upon dispatch."
            }, status=status.HTTP_200_OK)


class DellymanWebhookView(APIView):
    """
    POST: Real-time HMAC-SHA256 Webhook Receiver for Dellyman Logistics events.
    Events:
      Order.created    -> PENDING
      Order.picked     -> IN_TRANSIT (Order: OUT_FOR_DELIVERY)
      Order.delivered  -> DELIVERED (Order: DELIVERED, start 48h escrow clearance)
      Order.cancelled  -> FAILED_DELIVERY
    """
    permission_classes = [AllowAny]

    def post(self, request):
        sig_header = request.headers.get('X-Dellyman-Signature') or request.META.get('HTTP_X_DELLYMAN_SIGNATURE', '')
        
        # Verify HMAC Signature
        if not dellyman_client.verify_webhook_signature(request.body, sig_header):
            logger.warning("Dellyman webhook rejected: Invalid X-Dellyman-Signature.")
            return Response({'status': False, 'message': 'Invalid signature.'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            payload = request.data

        logger.info(f"Dellyman webhook received: {payload}")

        order_data = payload.get('order') or payload
        delly_order_id = str(order_data.get('OrderID') or '')
        delly_tracking_id = str(order_data.get('TrackingID') or '')
        delly_status = str(order_data.get('OrderStatus') or '').upper()

        if not (delly_order_id or delly_tracking_id):
            return Response({'status': False, 'message': 'Missing OrderID or TrackingID'}, status=status.HTTP_400_BAD_REQUEST)

        # Lookup Delivery
        delivery = Delivery.objects.filter(
            Q(dellyman_tracking_id=delly_tracking_id) |
            Q(dellyman_order_id=delly_order_id) |
            Q(tracking_number=delly_tracking_id)
        ).first()

        if not delivery:
            logger.warning(f"No delivery found matching Dellyman tracking #{delly_tracking_id} or order #{delly_order_id}")
            return Response({'status': True, 'message': 'Order not tracked on Aso.'}, status=status.HTTP_200_OK)

        # Map Dellyman Status to Aso Delivery Status
        if any(s in delly_status for s in ['PICKED', 'INTRANSIT', 'ASSIGNED']):
            update_delivery_status(delivery, DeliveryStatus.IN_TRANSIT, notes=f"Dellyman Status: {delly_status}")
        elif any(s in delly_status for s in ['DELIVERED', 'COMPLETED']):
            update_delivery_status(delivery, DeliveryStatus.DELIVERED, notes="Delivered by Dellyman courier.")
        elif any(s in delly_status for s in ['CANCELLED', 'REJECTED', 'FAILED']):
            update_delivery_status(delivery, DeliveryStatus.FAILED_DELIVERY, notes=f"Cancelled: {delly_status}")

        return Response({'status': True, 'message': 'Webhook processed successfully.'}, status=status.HTTP_200_OK)


class DeliveryStatusUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, delivery_id):
        try:
            delivery = Delivery.objects.get(id=delivery_id)
        except Delivery.DoesNotExist:
            return Response({'detail': 'Delivery not found.'}, status=status.HTTP_404_NOT_FOUND)

        if delivery.order.vendor.user != request.user and not request.user.is_staff:
            return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

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
                return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
