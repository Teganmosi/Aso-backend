"""
Launch QA round: the delivery fee the shopper is shown is the fee they pay, shoppers can report
a problem on a delivered order (pausing the designer payment), designers never see unpaid
checkouts, and a failed courier booking alerts the Aso team instead of pretending a rider is coming.
"""
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.cart.models import Cart, CartItem
from apps.deliveries.models import Delivery, DeliveryStatus
from apps.deliveries.services import quote_delivery
from apps.orders.models import Order, OrderStatus
from apps.orders.services import create_order_from_cart
from apps.products.models import ApprovalStatus, Category, Product, ProductStatus, ProductVariant
from apps.vendors.models import VendorProfile, VendorStatus


def _order(**kw):
    import uuid
    kw.setdefault('payment_expires_at', timezone.now() + timedelta(minutes=30))
    kw.setdefault('shipping_address_snapshot', {'full_name': 'Bee'})
    kw['order_number'] = f"{kw['order_number']}-{uuid.uuid4().hex[:6]}"
    return Order.objects.create(**kw)


class Base(TestCase):
    def setUp(self):
        self.designer = User.objects.create_user(email='studio@aso.test', password='Password123!')
        self.vendor = VendorProfile.objects.create(user=self.designer, store_name='Studio', city='Ikeja',
                                                   state='Lagos State', status=VendorStatus.APPROVED)
        self.shopper = User.objects.create_user(email='buyer@aso.test', password='Password123!', first_name='Bee')
        self.lagos = Address.objects.create(user=self.shopper, full_name='Bee', phone_number='08030000001',
                                            street_address='1 Road', city='Surulere', state='Lagos')
        self.abuja = Address.objects.create(user=self.shopper, full_name='Bee', phone_number='08030000001',
                                            street_address='2 Road', city='Wuse', state='FCT - Abuja')
        cat = Category.objects.create(name='QA Cat', description='c')
        product = Product.objects.create(vendor=self.vendor, category=cat, title='Kaftan', description='d',
                                         base_price_kobo=5000000, approval_status=ApprovalStatus.APPROVED,
                                         status=ProductStatus.PUBLISHED)
        self.variant = ProductVariant.objects.create(product=product, size='M', sku='KAF-M', stock_quantity=5)

    def fill_cart(self):
        cart, _ = Cart.objects.get_or_create(user=self.shopper, defaults={'vendor': self.vendor})
        cart.vendor = self.vendor
        cart.save()
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)


class DeliveryFeeTests(Base):
    def test_same_state_spelled_differently_is_not_interstate(self):
        self.assertFalse(quote_delivery(self.lagos, self.vendor)['is_interstate'])
        self.assertTrue(quote_delivery(self.abuja, self.vendor)['is_interstate'])

    @override_settings(DELIVERY_FLAT_FEE_SAME_STATE_NAIRA=3500, DELIVERY_FLAT_FEE_INTERSTATE_NAIRA=9000)
    def test_order_charges_the_quoted_flat_fee(self):
        with mock.patch('apps.deliveries.services.dellyman_client.api_key', ''):
            self.assertEqual(quote_delivery(self.abuja, self.vendor)['delivery_fee_kobo'], 900000)
            self.fill_cart()
            order = create_order_from_cart(self.shopper, self.lagos)
        self.assertEqual(order.delivery_fee_kobo, 350000)
        self.assertEqual(order.total_amount_kobo, 5000000 + 350000)

    def test_live_quote_is_charged(self):
        with mock.patch('apps.deliveries.services.dellyman_client.api_key', 'k'), \
             mock.patch('apps.deliveries.services.dellyman_client.get_quotes',
                        return_value={'Companies': [{'TotalPrice': 2750, 'Name': 'Bike'}]}):
            self.fill_cart()
            order = create_order_from_cart(self.shopper, self.lagos)
        self.assertEqual(order.delivery_fee_kobo, 275000)

    def test_quote_endpoint_matches(self):
        client = APIClient()
        client.force_authenticate(self.shopper)
        with override_settings(DELIVERY_FLAT_FEE_SAME_STATE_NAIRA=3500), \
             mock.patch('apps.deliveries.services.dellyman_client.api_key', ''):
            res = client.post('/api/v1/deliveries/quote/', {'address_id': str(self.lagos.id),
                                                            'vendor_id': str(self.vendor.id)}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['delivery_fee_kobo'], 350000)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', OPS_EMAIL='ops@aso.test')
class DisputeTests(Base):
    def make_order(self, status, delivered_hours_ago=1):
        order = _order(order_number=f'ASO-T-{status}', customer=self.shopper, vendor=self.vendor,
                                     order_status=status, subtotal_kobo=5000000, total_amount_kobo=5000000,
                                     shipping_address_snapshot={'full_name': 'Bee'})
        Delivery.objects.create(order=order, tracking_number=f'T-{order.order_number}', status=DeliveryStatus.DELIVERED,
                                delivered_at=timezone.now() - timedelta(hours=delivered_hours_ago))
        return order

    def test_shopper_reports_problem_on_delivered_order(self):
        order = self.make_order(OrderStatus.DELIVERED)
        client = APIClient()
        client.force_authenticate(self.shopper)
        res = client.post(f'/api/v1/orders/{order.id}/dispute/', {'reason': 'The waist is far too small.'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.DISPUTED)
        self.assertEqual(mail.outbox[0].to, ['ops@aso.test'])

    def test_window_closed_and_wrong_status_and_other_users(self):
        late = self.make_order(OrderStatus.DELIVERED, delivered_hours_ago=60)
        paid = self.make_order(OrderStatus.PAID)
        client = APIClient()
        client.force_authenticate(self.shopper)
        self.assertEqual(client.post(f'/api/v1/orders/{late.id}/dispute/', {'reason': 'Too late but wrong fit.'},
                                     format='json').status_code, 400)
        self.assertEqual(client.post(f'/api/v1/orders/{paid.id}/dispute/', {'reason': 'Not delivered yet at all.'},
                                     format='json').status_code, 400)
        client.force_authenticate(self.designer)
        fresh = self.make_order(OrderStatus.DELIVERED)
        self.assertEqual(client.post(f'/api/v1/orders/{fresh.id}/dispute/', {'reason': 'Designer trying this.'},
                                     format='json').status_code, 404)


class DesignerOrderVisibilityTests(Base):
    def test_unpaid_checkouts_hidden_from_designer(self):
        for st in (OrderStatus.PENDING_PAYMENT, OrderStatus.PAID):
            _order(order_number=f'ASO-V-{st}', customer=self.shopper, vendor=self.vendor,
                                 order_status=st, subtotal_kobo=1, total_amount_kobo=1)
        client = APIClient()
        client.force_authenticate(self.designer)
        data = client.get('/api/v1/vendors/orders/').data['data']
        self.assertEqual([o['order_status'] for o in data], [OrderStatus.PAID])


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', OPS_EMAIL='ops@aso.test')
class ManualCourierTests(Base):
    def test_failed_booking_alerts_ops_and_is_not_marked_booked(self):
        from apps.deliveries.serializers import DeliverySerializer
        from apps.deliveries.services import create_delivery_for_order
        order = _order(order_number='ASO-C-1', customer=self.shopper, vendor=self.vendor,
                                     order_status=OrderStatus.READY_FOR_PICKUP, subtotal_kobo=1, total_amount_kobo=1,
                                     shipping_address_snapshot={'full_name': 'Bee', 'phone_number': '0803',
                                                                'street_address': '1 Road', 'city': 'Surulere',
                                                                'state': 'Lagos'})
        with mock.patch('apps.deliveries.services.dellyman_client.book_order', return_value={}):
            delivery = create_delivery_for_order(order)
        self.assertFalse(DeliverySerializer(delivery).data['courier_booked'])
        self.assertTrue(any('Book a rider' in m.subject for m in mail.outbox))


class BalanceShapeTests(Base):
    def test_balance_exposes_fields_the_dashboard_reads(self):
        from apps.payouts.services import get_or_create_vendor_balance
        bal = get_or_create_vendor_balance(self.vendor)
        bal.available_balance_kobo = 16650000
        bal.save()
        client = APIClient()
        client.force_authenticate(self.designer)
        data = client.get('/api/v1/payouts/balance/').data['balance']
        for key in ('available_balance_kobo', 'available_balance_naira', 'pending_balance_naira',
                    'reserved_balance_naira', 'withdrawn_balance_naira'):
            self.assertIn(key, data)
        self.assertEqual(data['available_balance_kobo'], 16650000)
