from django.utils import timezone
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
        queryset = Order.objects.filter(customer=request.user)
        status_param = request.query_params.get('status')
        if status_param:
            status_param = status_param.upper()
            if status_param == 'PROCESSING':
                queryset = queryset.filter(order_status__in=['PAID', 'VENDOR_ACCEPTED', 'PREPARING'])
            elif status_param == 'IN_TRANSIT':
                queryset = queryset.filter(order_status__in=['PICKED_UP', 'OUT_FOR_DELIVERY'])
            elif status_param == 'COMPLETED':
                queryset = queryset.filter(order_status__in=['DELIVERED', 'COMPLETED'])
            elif status_param != 'ALL':
                queryset = queryset.filter(order_status=status_param)

        orders = queryset.select_related('vendor').prefetch_related('items').order_by('-created_at')

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


from apps.orders.models import OrderMessage, MessageType
from apps.orders.serializers import (
    OrderMessageSerializer,
    OrderMessageCreateSerializer,
    OrderActionRequestSerializer,
    OrderActionResolveSerializer
)
from apps.orders.anti_bypass import sanitize_order_message


class OrderMessageListCreateView(APIView):
    """
    GET: List all messages for this order with anti-bypass audit tracking.
    POST: Send a message through the 2-tier hybrid anti-bypass security shield.
    """
    permission_classes = [IsAuthenticated]

    def get_order_for_user(self, order_id, user):
        try:
            order = Order.objects.select_related('customer', 'vendor__user').get(id=order_id)
        except Order.DoesNotExist:
            return None, Response({'success': False, 'message': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

        is_customer = order.customer_id == user.id
        is_vendor = hasattr(order, 'vendor') and order.vendor.user_id == user.id
        if not (is_customer or is_vendor or user.is_staff):
            return None, Response({'success': False, 'message': 'Access forbidden.'}, status=status.HTTP_403_FORBIDDEN)

        return order, None

    def get(self, request, order_id):
        order, err_resp = self.get_order_for_user(order_id, request.user)
        if err_resp:
            return err_resp

        # Mark unread messages sent by the counterparty as read
        OrderMessage.objects.filter(order=order, read_at__isnull=True).exclude(sender=request.user).update(
            read_at=timezone.now()
        )

        messages = order.messages.select_related('sender').order_by('created_at')
        serializer = OrderMessageSerializer(messages, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request, order_id):
        order, err_resp = self.get_order_for_user(order_id, request.user)
        if err_resp:
            return err_resp

        serializer = OrderMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        raw_text = serializer.validated_data['content']

        # Pass through Two-Tier Hybrid Anti-Bypass Shield (Heuristic Regex + Nemotron LLM)
        is_masked, sanitized_text, reason, tier = sanitize_order_message(raw_text)

        msg = OrderMessage.objects.create(
            order=order,
            sender=request.user,
            message_type=MessageType.TEXT,
            content=sanitized_text,
            original_content=raw_text,
            is_masked=is_masked,
            mask_reason=reason,
            mask_tier=tier
        )

        out_serializer = OrderMessageSerializer(msg)
        return Response({
            'success': True,
            'message': 'Message sent successfully.',
            'data': out_serializer.data
        }, status=status.HTTP_201_CREATED)


class OrderActionRequestView(APIView):
    """
    Designer 1-tap structured action request (e.g. Request Waist Re-check).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        try:
            order = Order.objects.select_related('vendor__user').prefetch_related('items').get(id=order_id)
        except Order.DoesNotExist:
            return Response({'success': False, 'message': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

        is_vendor = hasattr(order, 'vendor') and order.vendor.user_id == request.user.id
        if not (is_vendor or request.user.is_staff):
            return Response({'success': False, 'message': 'Only the assigned designer can dispatch action requests.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = OrderActionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        measurement_key = serializer.validated_data['measurement_key']
        label = serializer.validated_data['label']
        prompt = serializer.validated_data.get('prompt') or f"Designer requested verification of {label}."

        first_item = order.items.first()
        cur_val = ''
        unit = 'IN'
        if first_item and isinstance(first_item.custom_measurements, dict):
            cur_val = first_item.custom_measurements.get(measurement_key, '')
            unit = first_item.custom_measurements.get('unit', 'IN')

        action_msg = OrderMessage.objects.create(
            order=order,
            sender=request.user,
            message_type=MessageType.ACTION_REQUEST,
            content=prompt,
            original_content=prompt,
            action_type='RECHECK_MEASUREMENT',
            action_payload={
                'measurement_key': measurement_key,
                'label': label,
                'current_value': cur_val,
                'unit': unit,
                'status': 'PENDING'
            }
        )

        out_serializer = OrderMessageSerializer(action_msg)
        return Response({
            'success': True,
            'message': 'Action request dispatched to customer.',
            'data': out_serializer.data
        }, status=status.HTTP_201_CREATED)


class OrderActionResolveView(APIView):
    """
    Customer 1-tap measurement update and live cut sheet synchronization.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        try:
            order = Order.objects.select_related('customer').prefetch_related('items').get(id=order_id)
        except Order.DoesNotExist:
            return Response({'success': False, 'message': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

        if order.customer_id != request.user.id and not request.user.is_staff:
            return Response({'success': False, 'message': 'Only the customer can update order measurements.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = OrderActionResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message_id = serializer.validated_data['message_id']
        measurement_key = serializer.validated_data['measurement_key']
        new_val = serializer.validated_data['new_value'].strip()

        try:
            action_msg = OrderMessage.objects.get(id=message_id, order=order)
        except OrderMessage.DoesNotExist:
            return Response({'success': False, 'message': 'Action message not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Update action message payload
        if isinstance(action_msg.action_payload, dict):
            action_msg.action_payload['status'] = 'RESOLVED'
            action_msg.action_payload['resolved_value'] = new_val
            action_msg.save(update_fields=['action_payload'])

        # Update order item custom cut sheet
        first_item = order.items.first()
        if first_item:
            meas = dict(first_item.custom_measurements or {})
            meas[measurement_key] = new_val
            first_item.custom_measurements = meas
            first_item.save(update_fields=['custom_measurements'])

        # Post system audit log
        label = (action_msg.action_payload or {}).get('label', measurement_key)
        audit_msg = OrderMessage.objects.create(
            order=order,
            sender=request.user,
            message_type=MessageType.SYSTEM_AUDIT,
            content=f"Customer updated {label} to {new_val}. Atelier cut sheet updated automatically.",
            original_content=f"Customer updated {label} to {new_val}."
        )

        return Response({
            'success': True,
            'message': 'Measurement confirmed and cut sheet updated.',
            'data': OrderMessageSerializer(audit_msg).data
        }, status=status.HTTP_200_OK)
