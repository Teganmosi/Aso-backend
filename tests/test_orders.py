from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from apps.accounts.models import User, Address
from apps.vendors.models import VendorProfile, VendorStatus
from apps.products.models import Category, Product, ProductVariant, ApprovalStatus, ProductStatus
from apps.cart.models import Cart, CartItem
from apps.orders.models import Order, OrderItem, OrderStatus
from apps.orders.services import cancel_expired_orders


class OrderEngineTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Customer User & Address
        self.customer = User.objects.create_user(
            email='customer@example.com',
            password='Password123!',
            first_name='Amina',
            last_name='Okoro',
            phone_number='+2348011111111'
        )
        self.address = Address.objects.create(
            user=self.customer,
            full_name='Amina Okoro',
            phone_number='+2348011111111',
            street_address='12 Admiralty Way, Lekki Phase 1',
            city='Lagos',
            state='Lagos',
            landmark='Near Admiralty Toll Gate'
        )

        # Other Customer User
        self.other_customer = User.objects.create_user(
            email='other@example.com',
            password='Password123!',
            first_name='Emeka',
            last_name='Sani'
        )

        # Vendor Profile ("Lagos Luxe Native")
        self.vendor_user = User.objects.create_user(
            email='vendor@example.com',
            password='Password123!',
            first_name='Tunde',
            last_name='Ade'
        )
        self.vendor = VendorProfile.objects.create(
            user=self.vendor_user,
            store_name='Lagos Luxe Native',
            slug='lagos-luxe-native',
            description='Luxury Nigerian traditional attire',
            city='Lagos',
            state='Lagos',
            status=VendorStatus.APPROVED
        )

        # Category & Product
        self.category = Category.objects.create(
            name='Traditional Attire',
            slug='traditional-attire'
        )
        self.product = Product.objects.create(
            vendor=self.vendor,
            category=self.category,
            title='Royal Silk Agbada',
            description='Handmade silk agbada set',
            base_price_kobo=7500000,  # N75,000
            approval_status=ApprovalStatus.APPROVED,
            status=ProductStatus.PUBLISHED
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size='XL',
            color='Navy',
            sku='ASO-V1-P1-XL-NAVY',
            stock_quantity=5
        )

    def test_unauthenticated_order_access_fails(self):
        response = self.client.get('/api/v1/orders/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_create_order_empty_cart_fails(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post('/api/v1/orders/', data={'address_id': str(self.address.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_order_insufficient_stock_fails(self):
        self.client.force_authenticate(user=self.customer)
        self.client.post('/api/v1/cart/items/', data={'variant_id': str(self.variant.id), 'quantity': 1}, format='json')
        
        # Deplete stock after adding to cart
        self.variant.stock_quantity = 0
        self.variant.save()

        response = self.client.post('/api/v1/orders/', data={'address_id': str(self.address.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Reset stock
        self.variant.stock_quantity = 5
        self.variant.save()

    def test_create_order_with_wrong_user_address_fails(self):
        other_address = Address.objects.create(
            user=self.other_customer,
            full_name='Emeka Sani',
            phone_number='+2348099999999',
            street_address='55 Wuse 2',
            city='Abuja',
            state='FCT'
        )
        self.client.force_authenticate(user=self.customer)
        self.client.post('/api/v1/cart/items/', data={'variant_id': str(self.variant.id), 'quantity': 1}, format='json')
        
        response = self.client.post('/api/v1/orders/', data={'address_id': str(other_address.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_order_and_atomic_stock_decrement(self):
        """
        Tests order creation from cart: stock is decremented from 5 to 4,
        order status is PENDING_PAYMENT, address & item snapshots are preserved, cart is cleared.
        """
        self.client.force_authenticate(user=self.customer)

        # 1. Add item to cart
        self.client.post('/api/v1/cart/items/', data={'variant_id': str(self.variant.id), 'quantity': 1}, format='json')

        # 2. Create order
        response = self.client.post('/api/v1/orders/', data={'address_id': str(self.address.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data['data']

        # Verify order fields
        self.assertTrue(data['order_number'].startswith('ASO-'))
        self.assertEqual(data['order_status'], OrderStatus.PENDING_PAYMENT)
        self.assertEqual(data['subtotal_kobo'], 7500000)
        self.assertEqual(data['subtotal_naira'], 75000.0)
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['variant_size_snapshot'], 'XL')

        # Check DB: variant stock decremented from 5 to 4
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 4)

        # Check DB: cart cleared
        cart = Cart.objects.get(user=self.customer)
        self.assertEqual(cart.items.count(), 0)
        self.assertIsNone(cart.vendor)

    def test_address_and_price_snapshot_immutability(self):
        """
        Modifying user's address or variant price after order creation does not change snapshotted order details.
        """
        self.client.force_authenticate(user=self.customer)
        self.client.post('/api/v1/cart/items/', data={'variant_id': str(self.variant.id), 'quantity': 1}, format='json')
        res = self.client.post('/api/v1/orders/', data={'address_id': str(self.address.id)}, format='json')
        order_id = res.data['data']['id']

        # Mutate saved address line and variant price
        self.address.street_address = 'NEW ADDRESS: 99 Victoria Island Blvd'
        self.address.save()

        self.variant.price_override_kobo = 10000000  # N100,000
        self.variant.save()

        # Retrieve order
        response = self.client.get(f'/api/v1/orders/{order_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']

        # Verify snapshot address line remains unchanged
        self.assertEqual(data['shipping_address_snapshot']['street_address'], '12 Admiralty Way, Lekki Phase 1')

        # Verify item snapshot price remains N75,000 (7500000 Kobo)
        self.assertEqual(data['items'][0]['unit_price_kobo'], 7500000)

    def test_other_customer_cannot_view_order(self):
        self.client.force_authenticate(user=self.customer)
        self.client.post('/api/v1/cart/items/', data={'variant_id': str(self.variant.id), 'quantity': 1}, format='json')
        res = self.client.post('/api/v1/orders/', data={'address_id': str(self.address.id)}, format='json')
        order_id = res.data['data']['id']

        # Authenticate as other customer
        self.client.force_authenticate(user=self.other_customer)
        response = self.client.get(f'/api/v1/orders/{order_id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_30_minute_reservation_timeout_restores_stock(self):
        """
        Tests expired order cleanup service & management command:
        Pending order exceeding 30 minutes transitions to CANCELLED and restores stock back to 5.
        """
        self.client.force_authenticate(user=self.customer)
        self.client.post('/api/v1/cart/items/', data={'variant_id': str(self.variant.id), 'quantity': 2}, format='json')
        res = self.client.post('/api/v1/orders/', data={'address_id': str(self.address.id)}, format='json')
        order_id = res.data['data']['id']

        # Stock decremented to 3
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 3)

        # Force payment_expires_at into past (35 minutes ago)
        order = Order.objects.get(id=order_id)
        order.payment_expires_at = timezone.now() - timedelta(minutes=35)
        order.save(update_fields=['payment_expires_at'])

        # Run expired order cleanup service
        cancelled_count = cancel_expired_orders()
        self.assertEqual(cancelled_count, 1)

        # Verify order status is CANCELLED
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CANCELLED)
        self.assertIn("30m timeout", order.cancellation_reason)

        # Verify variant stock restored back to 5
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)
