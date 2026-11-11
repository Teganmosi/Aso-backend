from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.core.management import call_command
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, Address
from apps.vendors.models import VendorProfile, VendorStatus
from apps.products.models import Category, Product, ProductVariant, ApprovalStatus, ProductStatus
from apps.orders.models import Order, OrderStatus
from apps.deliveries.models import Delivery, DeliveryStatus
from apps.orders.services import process_vendor_sla_timeouts


class Sprint8OrdersDeliveriesTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users
        self.customer = User.objects.create_user(
            email='customer@example.com',
            password='Password123!',
            first_name='Amina',
            last_name='Okoro',
            phone_number='+2348011111111'
        )

        self.other_customer = User.objects.create_user(
            email='other@example.com',
            password='Password123!',
            first_name='Tomi',
            last_name='Alabi',
            phone_number='+2348022222222'
        )

        self.vendor_user = User.objects.create_user(
            email='vendor@example.com',
            password='Password123!',
            first_name='Tunde',
            last_name='Ade',
            phone_number='+2348033333333'
        )

        self.other_vendor_user = User.objects.create_user(
            email='other_vendor@example.com',
            password='Password123!',
            first_name='Zara',
            last_name='Aba',
            phone_number='+2348044444444'
        )

        self.staff_user = User.objects.create_superuser(
            email='staff@example.com',
            password='Password123!',
            first_name='Staff',
            last_name='User'
        )

        # Vendor Profiles
        self.vendor = VendorProfile.objects.create(
            user=self.vendor_user,
            store_name='Lagos Luxe Native',
            slug='lagos-luxe-native',
            description='Luxury Nigerian traditional attire',
            city='Lagos',
            state='Lagos',
            status=VendorStatus.APPROVED
        )

        self.other_vendor = VendorProfile.objects.create(
            user=self.other_vendor_user,
            store_name='Zara Designs',
            slug='zara-designs',
            description='Modern bespoke tailoring',
            city='Abuja',
            state='FCT',
            status=VendorStatus.APPROVED
        )

        # Product & Variant
        self.category = Category.objects.create(
            name='Traditional Attire',
            slug='traditional-attire'
        )
        self.product = Product.objects.create(
            vendor=self.vendor,
            category=self.category,
            title='Royal Silk Agbada',
            description='Handmade silk agbada set',
            base_price_kobo=7500000,
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

        # Address
        self.address_snapshot = {
            'full_name': 'Amina Okoro',
            'phone_number': '+2348011111111',
            'street_address': '12 Admiralty Way, Lekki Phase 1',
            'city': 'Lagos',
            'state': 'Lagos',
            'landmark': 'Near Admiralty Toll Gate'
        }

        # Create base PAID order
        self.order = Order.objects.create(
            order_number='ASO-20260816-ABC123',
            customer=self.customer,
            vendor=self.vendor,
            order_status=OrderStatus.PAID,
            subtotal_kobo=7500000,
            total_amount_kobo=7500000,
            payment_expires_at=timezone.now() + timedelta(minutes=30),
            vendor_accept_due_by=timezone.now() + timedelta(hours=48),
            shipping_address_snapshot=self.address_snapshot
        )

    def test_vendor_view_orders_list(self):
        """Test that vendor can see their orders and other vendors cannot."""
        # Authenticated as vendor
        self.client.force_authenticate(user=self.vendor_user)
        response = self.client.get('/api/v1/vendors/orders/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['id'], str(self.order.id))

        # Authenticated as other vendor
        self.client.force_authenticate(user=self.other_vendor_user)
        response = self.client.get('/api/v1/vendors/orders/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 0)

        # Authenticated as customer
        self.client.force_authenticate(user=self.customer)
        response = self.client.get('/api/v1/vendors/orders/')
        # SEC-01: customers (no vendor profile) are forbidden from the studio orders API.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendor_view_order_detail(self):
        """Test that vendor can view details of their order, but not others."""
        # Authenticated as vendor
        self.client.force_authenticate(user=self.vendor_user)
        response = self.client.get(f'/api/v1/vendors/orders/{self.order.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['order_number'], self.order.order_number)

        # Authenticated as other vendor
        self.client.force_authenticate(user=self.other_vendor_user)
        response = self.client.get(f'/api/v1/vendors/orders/{self.order.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_order_acceptance_flow(self):
        """Test full accept -> preparing -> ready workflow for vendor."""
        # 1. Accept Order
        self.client.force_authenticate(user=self.vendor_user)
        response = self.client.post(f'/api/v1/orders/{self.order.id}/accept/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.VENDOR_ACCEPTED)
        self.assertIsNotNone(self.order.vendor_accepted_at)

        # Attempt to accept again - should fail
        response = self.client.post(f'/api/v1/orders/{self.order.id}/accept/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Other vendor cannot accept
        self.client.force_authenticate(user=self.other_vendor_user)
        self.order.order_status = OrderStatus.PAID
        self.order.vendor_accepted_at = None
        self.order.save()
        response = self.client.post(f'/api/v1/orders/{self.order.id}/accept/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST) # Raises ownership validation error

        # 2. Transition to Preparing
        self.client.force_authenticate(user=self.vendor_user)
        self.order.order_status = OrderStatus.VENDOR_ACCEPTED
        self.order.save()
        response = self.client.post(f'/api/v1/orders/{self.order.id}/preparing/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.PREPARING)
        self.assertIsNotNone(self.order.prepared_at)

        # 3. Transition to Ready for Pickup
        response = self.client.post(f'/api/v1/orders/{self.order.id}/ready/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.READY_FOR_PICKUP)
        self.assertIsNotNone(self.order.ready_for_pickup_at)

        # Verify Delivery record was created
        delivery = Delivery.objects.get(order=self.order)
        self.assertEqual(delivery.status, DeliveryStatus.PENDING)
        self.assertTrue(delivery.tracking_number.startswith('ASO-DEL-'))

    def test_delivery_status_sync_and_permissions(self):
        """Test that delivery updates sync with order status and permissions are enforced."""
        # Create delivery for order
        self.order.order_status = OrderStatus.READY_FOR_PICKUP
        self.order.save()
        delivery = Delivery.objects.create(
            order=self.order,
            tracking_number='ASO-DEL-MOCK-12345',
            status=DeliveryStatus.PENDING
        )

        # Customer attempts to update status - should fail
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            f'/api/v1/deliveries/{delivery.id}/update-status/',
            data={'status': DeliveryStatus.PICKED_UP, 'notes': 'Picked up'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Vendor attempts to update status - should succeed
        self.client.force_authenticate(user=self.vendor_user)
        response = self.client.post(
            f'/api/v1/deliveries/{delivery.id}/update-status/',
            data={'status': DeliveryStatus.PICKED_UP, 'notes': 'Package picked up by rider'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        delivery.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(delivery.status, DeliveryStatus.PICKED_UP)
        self.assertEqual(self.order.order_status, OrderStatus.PICKED_UP)
        self.assertIsNotNone(delivery.picked_up_at)

        # Vendor transitions to IN_TRANSIT (Out for Delivery)
        response = self.client.post(
            f'/api/v1/deliveries/{delivery.id}/update-status/',
            data={'status': DeliveryStatus.IN_TRANSIT, 'notes': 'Out for delivery'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        delivery.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(delivery.status, DeliveryStatus.IN_TRANSIT)
        self.assertEqual(self.order.order_status, OrderStatus.OUT_FOR_DELIVERY)
        self.assertIsNotNone(delivery.dispatched_at)

        # Staff user transitions to DELIVERED
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(
            f'/api/v1/deliveries/{delivery.id}/update-status/',
            data={'status': DeliveryStatus.DELIVERED, 'notes': 'Delivered successfully'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        delivery.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(delivery.status, DeliveryStatus.DELIVERED)
        self.assertEqual(self.order.order_status, OrderStatus.DELIVERED)
        self.assertIsNotNone(delivery.delivered_at)

        # Attempt to transition from DELIVERED back to PENDING - should fail (forbidden transition)
        response = self.client.post(
            f'/api/v1/deliveries/{delivery.id}/update-status/',
            data={'status': DeliveryStatus.PENDING, 'notes': 'Rollback status'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot transition delivery status", response.data['error']['details']['status'][0])

    def test_delivery_tracking_view_permissions(self):
        """Test retrieving order delivery details permissions (customer, vendor, staff, unauthorized)."""
        delivery = Delivery.objects.create(
            order=self.order,
            tracking_number='ASO-DEL-MOCK-12345',
            status=DeliveryStatus.PENDING
        )

        # 1. Customer who owns the order can view
        self.client.force_authenticate(user=self.customer)
        response = self.client.get(f'/api/v1/orders/{self.order.id}/delivery/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['tracking_number'], delivery.tracking_number)

        # 2. Vendor of the order can view
        self.client.force_authenticate(user=self.vendor_user)
        response = self.client.get(f'/api/v1/orders/{self.order.id}/delivery/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 3. Staff can view
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(f'/api/v1/orders/{self.order.id}/delivery/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 4. Another customer cannot view
        self.client.force_authenticate(user=self.other_customer)
        response = self.client.get(f'/api/v1/orders/{self.order.id}/delivery/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 5. Another vendor cannot view
        self.client.force_authenticate(user=self.other_vendor_user)
        response = self.client.get(f'/api/v1/orders/{self.order.id}/delivery/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendor_sla_timeout_cancellation_and_stock_restoration(self):
        """Test process_vendor_sla_timeouts cancels expired PAID orders and restores stock."""
        # Create an OrderItem to simulate stock reservation
        from apps.orders.models import OrderItem
        OrderItem.objects.create(
            order=self.order,
            variant=self.variant,
            product_title_snapshot=self.product.title,
            variant_size_snapshot=self.variant.size,
            sku_snapshot=self.variant.sku,
            unit_price_kobo=self.product.base_price_kobo,
            quantity=2,
            total_price_kobo=self.product.base_price_kobo * 2
        )

        # Check initial variant stock (it was set to 5 in setUp, let's pretend 2 units were decremented during order)
        self.variant.stock_quantity = 3
        self.variant.save()

        # Update SLA to the past
        self.order.vendor_accept_due_by = timezone.now() - timedelta(minutes=1)
        self.order.save()

        # Run command
        call_command('check_vendor_sla_timeouts')

        self.order.refresh_from_db()
        self.variant.refresh_from_db()

        # Order must be cancelled
        self.assertEqual(self.order.order_status, OrderStatus.CANCELLED)
        self.assertIn("Vendor SLA Timeout", self.order.cancellation_reason)

        # Stock must be restored: 3 + 2 = 5
        self.assertEqual(self.variant.stock_quantity, 5)

    def test_vendor_sla_does_not_cancel_unexpired_or_accepted(self):
        """Test SLA task does not affect valid active or already accepted orders."""
        # Active paid order within SLA (not expired)
        self.order.vendor_accept_due_by = timezone.now() + timedelta(hours=2)
        self.order.save()

        process_vendor_sla_timeouts()
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.PAID)

        # Expired but already accepted order
        self.order.order_status = OrderStatus.VENDOR_ACCEPTED
        self.order.vendor_accepted_at = timezone.now() - timedelta(hours=1)
        self.order.vendor_accept_due_by = timezone.now() - timedelta(minutes=10)
        self.order.save()

        process_vendor_sla_timeouts()
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.VENDOR_ACCEPTED)
