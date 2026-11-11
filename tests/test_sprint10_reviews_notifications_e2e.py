import hmac
import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.core import mail
from django.core.management import call_command
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, Address
from apps.vendors.models import VendorProfile, VendorStatus, BankAccount, KYCTier
from apps.products.models import Category, Product, ProductVariant, ProductMedia, Review, ApprovalStatus, ProductStatus
from apps.orders.models import Order, OrderItem, OrderStatus
from apps.deliveries.models import Delivery, DeliveryStatus
from apps.deliveries.services import create_delivery_for_order, update_delivery_status
from apps.payments.models import PaymentRequest
from apps.payments.services import verify_and_process_webhook
from apps.payouts.models import VendorBalance, LedgerEntry, LedgerEntryType, PayoutRequest, PayoutStatus
from apps.payouts.services import get_or_create_vendor_balance, complete_order, process_completed_orders, request_payout
from apps.common.notifications import (
    send_order_placed_notification,
    send_payment_received_notification,
    send_order_dispatched_notification,
    send_order_completed_notification,
    send_payout_initiated_notification
)


class Sprint10ReviewsAndNotificationsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users
        self.vendor_user = User.objects.create_user(
            email='seyi@lagoscouture.ng',
            password='Password123!',
            first_name='Seyi',
            last_name='Tinubu',
            phone_number='+2348011223399'
        )

        self.customer = User.objects.create_user(
            email='kemi@customer.ng',
            password='Password123!',
            first_name='Kemi',
            last_name='Adebayo',
            phone_number='+2348099887711'
        )

        self.other_customer = User.objects.create_user(
            email='tunde@other.ng',
            password='Password123!',
            first_name='Tunde',
            last_name='Bakare',
            phone_number='+2348099887722'
        )

        # Vendor Profile
        self.vendor = VendorProfile.objects.create(
            user=self.vendor_user,
            store_name='Lagos Couture House',
            slug='lagos-couture-house',
            description='Premium Nigerian Bespoke & Ready-to-wear',
            status=VendorStatus.APPROVED,
            kyc_tier=KYCTier.TIER_2_VERIFIED,
            is_verified=True
        )

        # Category & Product
        self.category = Category.objects.create(name='Aso Oke', slug='aso-oke')
        self.product = Product.objects.create(
            vendor=self.vendor,
            category=self.category,
            title='Royal Aso Oke Set',
            slug='royal-aso-oke-set',
            base_price_kobo=6000000,  # ₦60,000
            status=ProductStatus.PUBLISHED,
            approval_status=ApprovalStatus.APPROVED,
            preparation_time_days=4
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size='M',
            color='Burgundy & Gold',
            sku='ASO-OKE-M-01',
            stock_quantity=10
        )

        # Create base COMPLETED order with OrderItem
        self.completed_order = Order.objects.create(
            order_number='ASO-COMPLETED-001',
            customer=self.customer,
            vendor=self.vendor,
            subtotal_kobo=6000000,
            delivery_fee_kobo=200000,
            total_amount_kobo=6200000,
            order_status=OrderStatus.COMPLETED,
            payment_expires_at=timezone.now() + timedelta(minutes=30),
            shipping_address_snapshot={
                'full_name': 'Kemi Adebayo',
                'phone_number': '+2348099887711',
                'street_address': '5 Glover Road, Ikoyi',
                'city': 'Lagos',
                'state': 'Lagos'
            }
        )
        self.completed_item = OrderItem.objects.create(
            order=self.completed_order,
            variant=self.variant,
            product_title_snapshot=self.product.title,
            variant_size_snapshot=self.variant.size,
            variant_color_snapshot=self.variant.color,
            sku_snapshot=self.variant.sku,
            quantity=1,
            unit_price_kobo=6000000,
            total_price_kobo=6000000
        )

    def test_verified_buyer_can_post_review_and_aggregates_update(self):
        """Test that a verified customer can review a completed item and product/vendor ratings update."""
        self.client.force_authenticate(user=self.customer)

        review_payload = {
            'order_item_id': str(self.completed_item.id),
            'rating': 5,
            'comment': 'Stunning tailoring! The craftsmanship on this Aso Oke is world-class.'
        }
        url = f'/api/v1/products/{self.product.id}/reviews/'
        response = self.client.post(url, data=review_payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data['review']
        self.assertEqual(data['rating'], 5)
        self.assertEqual(data['comment'], review_payload['comment'])
        self.assertTrue(data['is_verified_purchase'])
        self.assertEqual(data['customer_name'], 'Kemi A.')

        # Verify Product rating aggregation
        self.product.refresh_from_db()
        self.assertEqual(self.product.average_rating, Decimal('5.00'))
        self.assertEqual(self.product.review_count, 1)

        # Verify VendorProfile rating aggregation
        self.vendor.refresh_from_db()
        self.assertEqual(self.vendor.average_rating, Decimal('5.00'))
        self.assertEqual(self.vendor.review_count, 1)

    def test_reject_duplicate_review_on_same_order_item(self):
        """Test that submitting a second review on the same order item is rejected."""
        self.client.force_authenticate(user=self.customer)

        # First review
        Review.objects.create(
            order_item=self.completed_item,
            product=self.product,
            vendor=self.vendor,
            customer=self.customer,
            rating=5,
            comment='First review.'
        )

        review_payload = {
            'order_item_id': str(self.completed_item.id),
            'rating': 4,
            'comment': 'Second review attempt.'
        }
        url = f'/api/v1/products/{self.product.id}/reviews/'
        response = self.client.post(url, data=review_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already reviewed", str(response.data))

    def test_reject_review_if_order_not_completed(self):
        """Test that reviews cannot be left for uncompleted orders (e.g. PAID or IN_TRANSIT)."""
        self.client.force_authenticate(user=self.customer)

        uncompleted_order = Order.objects.create(
            order_number='ASO-PAID-002',
            customer=self.customer,
            vendor=self.vendor,
            subtotal_kobo=6000000,
            delivery_fee_kobo=200000,
            total_amount_kobo=6200000,
            order_status=OrderStatus.PAID,
            payment_expires_at=timezone.now() + timedelta(minutes=30),
            shipping_address_snapshot={}
        )
        uncompleted_item = OrderItem.objects.create(
            order=uncompleted_order,
            variant=self.variant,
            product_title_snapshot=self.product.title,
            variant_size_snapshot=self.variant.size,
            sku_snapshot=self.variant.sku,
            quantity=1,
            unit_price_kobo=6000000,
            total_price_kobo=6000000
        )

        payload = {
            'order_item_id': str(uncompleted_item.id),
            'rating': 5,
            'comment': 'Item not received yet.'
        }
        url = f'/api/v1/products/{self.product.id}/reviews/'
        response = self.client.post(url, data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("completed orders", str(response.data))

    def test_reject_review_by_different_user(self):
        """Test that user cannot review an order item belonging to another customer."""
        self.client.force_authenticate(user=self.other_customer)

        payload = {
            'order_item_id': str(self.completed_item.id),
            'rating': 5,
            'comment': 'Attempting unauthorized review.'
        }
        url = f'/api/v1/products/{self.product.id}/reviews/'
        response = self.client.post(url, data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("only review items you purchased", str(response.data))

    def test_public_product_and_vendor_review_endpoints(self):
        """Test GET review endpoints on product and vendor routes."""
        Review.objects.create(
            order_item=self.completed_item,
            product=self.product,
            vendor=self.vendor,
            customer=self.customer,
            rating=5,
            comment='Top tier garment quality.'
        )
        self.product.average_rating = Decimal('5.00')
        self.product.review_count = 1
        self.product.save()

        self.vendor.average_rating = Decimal('5.00')
        self.vendor.review_count = 1
        self.vendor.save()

        # Product reviews endpoint
        resp_product = self.client.get(f'/api/v1/products/{self.product.id}/reviews/')
        self.assertEqual(resp_product.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_product.data['count'], 1)
        self.assertEqual(resp_product.data['average_rating'], 5.0)
        self.assertEqual(len(resp_product.data['reviews']), 1)

        # Vendor reviews endpoint
        resp_vendor = self.client.get(f'/api/v1/vendors/{self.vendor.slug}/reviews/')
        self.assertEqual(resp_vendor.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_vendor.data['count'], 1)
        self.assertEqual(resp_vendor.data['average_rating'], 5.0)
        self.assertEqual(len(resp_vendor.data['reviews']), 1)

    def test_transactional_notification_emails(self):
        """Test that transactional emails generate and deliver HTML messages into outbox."""
        mail.outbox = []

        # 1. Order Placed Email
        send_order_placed_notification(self.completed_order)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Order #ASO-COMPLETED-001 Placed", mail.outbox[0].subject)
        self.assertIn(self.customer.email, mail.outbox[0].to)

        # 2. Payment Received Email
        send_payment_received_notification(self.completed_order)
        self.assertEqual(len(mail.outbox), 3)  # 1 customer + 1 vendor

        # 3. Order Dispatched Email
        delivery = Delivery.objects.create(
            order=self.completed_order,
            tracking_number='ASO-DEL-TEST-001',
            carrier_name='MANUAL_DISPATCH',
            status=DeliveryStatus.IN_TRANSIT
        )
        send_order_dispatched_notification(delivery)
        self.assertEqual(len(mail.outbox), 4)
        self.assertIn("Out for Delivery", mail.outbox[3].subject)

        # 4. Order Completed Email
        send_order_completed_notification(self.completed_order)
        self.assertEqual(len(mail.outbox), 5)
        self.assertIn("Leave a Review", mail.outbox[4].subject)

        # 5. Payout Initiated Email
        bank_account = BankAccount.objects.create(
            vendor=self.vendor,
            bank_name='GTBank',
            account_number='0123456789',
            account_name='Seyi Tinubu',
            bank_code='058'
        )
        payout_req = PayoutRequest.objects.create(
            vendor=self.vendor,
            amount_kobo=5000000,
            status=PayoutStatus.PROCESSING,
            reference='ASO-PAY-20260831-TEST01',
            bank_account=bank_account
        )
        send_payout_initiated_notification(payout_req)
        self.assertEqual(len(mail.outbox), 6)
        self.assertIn("Payout #ASO-PAY-20260831-TEST01 Initiated", mail.outbox[5].subject)

    def test_complete_end_to_end_marketplace_lifecycle(self):
        """
        Complete End-to-End Walkthrough:
        1. Customer registration & address configuration
        2. Designer storefront creation & KYC verification
        3. Product publication
        4. Customer cart addition & checkout
        5. Paystack webhook payment execution
        6. Vendor SLA acceptance & ready for pickup
        7. Dispatch coordination & delivery confirmation
        8. 72-hour escrow customer protection release
        9. Customer verified review
        10. Designer payout withdrawal
        """
        mail.outbox = []

        # 1. Customer User
        customer = User.objects.create_user(
            email='e2e_buyer@marketplace.ng',
            password='Password123!',
            first_name='Zainab',
            last_name='Aliyu',
            phone_number='+2348022334455'
        )
        address = Address.objects.create(
            user=customer,
            full_name='Zainab Aliyu',
            phone_number='+2348022334455',
            street_address='14 Victoria Garden City',
            city='Lekki',
            state='Lagos',
            is_default=True
        )

        # 2. Designer Setup
        designer_user = User.objects.create_user(
            email='e2e_designer@marketplace.ng',
            password='Password123!',
            first_name='Femi',
            last_name='Kuti',
            phone_number='+2348033445566'
        )
        designer_profile = VendorProfile.objects.create(
            user=designer_user,
            store_name='Femi Kuti Bespoke',
            slug='femi-kuti-bespoke',
            status=VendorStatus.APPROVED,
            kyc_tier=KYCTier.TIER_2_VERIFIED,
            is_verified=True
        )
        bank_account = BankAccount.objects.create(
            vendor=designer_profile,
            bank_name='Zenith Bank',
            account_number='2001122334',
            account_name='Femi Kuti',
            bank_code='057'
        )

        # 3. Product Catalog
        product = Product.objects.create(
            vendor=designer_profile,
            category=self.category,
            title='Imperial Emerald Senator',
            slug='imperial-emerald-senator',
            base_price_kobo=5000000,  # ₦50,000
            status=ProductStatus.PUBLISHED,
            approval_status=ApprovalStatus.APPROVED,
            preparation_time_days=3
        )
        variant = ProductVariant.objects.create(
            product=product,
            size='L',
            color='Emerald',
            sku='E2E-SEN-L-01',
            stock_quantity=5
        )

        # 4. Checkout Order
        order = Order.objects.create(
            order_number='ASO-E2E-ORD-100',
            customer=customer,
            vendor=designer_profile,
            subtotal_kobo=5000000,
            delivery_fee_kobo=200000,
            total_amount_kobo=5200000,
            order_status=OrderStatus.PENDING_PAYMENT,
            payment_expires_at=timezone.now() + timedelta(minutes=30),
            shipping_address_snapshot={
                'full_name': 'Zainab Aliyu',
                'phone_number': '+2348022334455',
                'street_address': '14 Victoria Garden City',
                'city': 'Lekki',
                'state': 'Lagos'
            }
        )
        order_item = OrderItem.objects.create(
            order=order,
            variant=variant,
            product_title_snapshot=product.title,
            variant_size_snapshot=variant.size,
            variant_color_snapshot=variant.color,
            sku_snapshot=variant.sku,
            quantity=1,
            unit_price_kobo=5000000,
            total_price_kobo=5000000
        )
        payment_req = PaymentRequest.objects.create(
            order=order,
            provider='PAYSTACK',
            amount_kobo=5200000,
            currency='NGN',
            reference=f"ASO-E2E-PAY-{order.id.hex[:8]}",
            status='PENDING'
        )

        # 5. Paystack Webhook Confirmation
        raw_payload = json.dumps({
            'event': 'charge.success',
            'data': {
                'reference': payment_req.reference,
                'amount': 5200000,
                'currency': 'NGN',
                'status': 'success'
            }
        }).encode('utf-8')
        signature = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), raw_payload, hashlib.sha512).hexdigest()
        verify_and_process_webhook(raw_payload, signature)

        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.PAID)
        self.assertIsNotNone(order.vendor_accept_due_by)

        # Check pending balance (₦50,000 subtotal - 10% commission = ₦45,000 = 4,500,000 kobo)
        vendor_balance = get_or_create_vendor_balance(designer_profile)
        self.assertEqual(vendor_balance.pending_balance_kobo, 4500000)
        self.assertEqual(vendor_balance.available_balance_kobo, 0)

        # 6. Vendor Order Lifecycle: Accept & Ready
        self.client.force_authenticate(user=designer_user)
        accept_resp = self.client.post(f'/api/v1/orders/{order.id}/accept/')
        self.assertEqual(accept_resp.status_code, status.HTTP_200_OK)

        ready_resp = self.client.post(f'/api/v1/orders/{order.id}/ready/')
        self.assertEqual(ready_resp.status_code, status.HTTP_200_OK)

        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.READY_FOR_PICKUP)

        # 7. Delivery Dispatch Coordination
        delivery = Delivery.objects.get(order=order)
        self.client.force_authenticate(user=designer_user)
        update_delivery_status(delivery, DeliveryStatus.IN_TRANSIT)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.OUT_FOR_DELIVERY)

        update_delivery_status(delivery, DeliveryStatus.DELIVERED)
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.DELIVERED)

        # 8. 72-Hour Escrow Protection Auto-Completion
        delivery.delivered_at = timezone.now() - timedelta(hours=73)
        delivery.save(update_fields=['delivered_at'])

        call_command('process_completed_orders')
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.COMPLETED)

        vendor_balance.refresh_from_db()
        self.assertEqual(vendor_balance.pending_balance_kobo, 0)
        self.assertEqual(vendor_balance.available_balance_kobo, 4500000)

        # 9. Verified Review Submission
        self.client.force_authenticate(user=customer)
        review_resp = self.client.post(
            f'/api/v1/products/{product.id}/reviews/',
            data={
                'order_item_id': str(order_item.id),
                'rating': 5,
                'comment': 'Exceptional fit and luxurious fabric! Exceeded expectations.'
            },
            format='json'
        )
        self.assertEqual(review_resp.status_code, status.HTTP_201_CREATED)

        product.refresh_from_db()
        designer_profile.refresh_from_db()
        self.assertEqual(product.average_rating, Decimal('5.00'))
        self.assertEqual(designer_profile.average_rating, Decimal('5.00'))

        # 10. Designer Payout Withdrawal
        self.client.force_authenticate(user=designer_user)
        withdraw_resp = self.client.post(
            '/api/v1/payouts/withdraw/',
            data={'amount_kobo': 4500000},
            format='json'
        )
        self.assertEqual(withdraw_resp.status_code, status.HTTP_201_CREATED)

        vendor_balance.refresh_from_db()
        self.assertEqual(vendor_balance.available_balance_kobo, 0)
        self.assertEqual(vendor_balance.reserved_balance_kobo, 4500000)

        payout = PayoutRequest.objects.get(vendor=designer_profile)
        self.assertEqual(payout.amount_kobo, 4500000)
        self.assertIn(payout.status, [PayoutStatus.PAYOUT_RESERVED, PayoutStatus.PROCESSING])
