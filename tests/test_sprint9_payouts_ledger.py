import hmac
import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.core.management import call_command
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, Address
from apps.vendors.models import VendorProfile, VendorStatus, BankAccount, KYCTier
from apps.products.models import Category, Product, ProductVariant, ApprovalStatus, ProductStatus
from apps.orders.models import Order, OrderItem, OrderStatus
from apps.deliveries.models import Delivery, DeliveryStatus
from apps.payments.models import PaymentRequest
from apps.payments.services import verify_and_process_webhook
from apps.payouts.models import VendorBalance, LedgerEntry, LedgerEntryType, PayoutRequest, PayoutStatus
from apps.payouts.services import (
    get_or_create_vendor_balance,
    record_pending_earning,
    reverse_pending_earning,
    complete_order,
    process_completed_orders,
    request_payout,
    process_payout,
    fail_payout,
    succeed_payout,
)
from apps.orders.services import process_vendor_sla_timeouts


class Sprint9PayoutsLedgerTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users
        self.vendor_user = User.objects.create_user(
            email='designer@lagosluxe.ng',
            password='Password123!',
            first_name='Adeola',
            last_name='Balogun',
            phone_number='+2348011223344'
        )

        self.customer = User.objects.create_user(
            email='customer@example.ng',
            password='Password123!',
            first_name='Chioma',
            last_name='Nnamdi',
            phone_number='+2348099887766'
        )

        # Vendor Profile
        self.vendor = VendorProfile.objects.create(
            user=self.vendor_user,
            store_name='Lagos Luxe Tailoring',
            slug='lagos-luxe-tailoring',
            description='Bespoke Nigerian luxury garments',
            status=VendorStatus.APPROVED,
            kyc_tier=KYCTier.TIER_1_STARTER,
            is_verified=True,
            verification_status='VERIFIED',
        )

        # Bank Account
        self.bank_account = BankAccount.objects.create(
            vendor=self.vendor,
            bank_name='Access Bank',
            account_number='0123456789',
            account_name='Adeola Balogun',
            bank_code='044'
        )

        # Address Snapshot
        self.address_snapshot = {
            'full_name': 'Chioma Nnamdi',
            'phone_number': '+2348099887766',
            'street_address': '12 Marina Road',
            'city': 'Lagos Island',
            'state': 'Lagos'
        }

        # Product & Variant
        self.category = Category.objects.create(name='Agbada', slug='agbada')
        self.product = Product.objects.create(
            vendor=self.vendor,
            category=self.category,
            title='Royal Silk Agbada',
            slug='royal-silk-agbada',
            base_price_kobo=5000000,  # ₦50,000
            status=ProductStatus.PUBLISHED,
            approval_status=ApprovalStatus.APPROVED,
            preparation_time_days=3
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            size='L',
            color='Emerald Gold',
            sku='RS-AGB-L-01',
            stock_quantity=10
        )

    def _create_paid_order(self, quantity=1, price_kobo=5000000) -> Order:
        """Helper to create an order and simulate payment webhook."""
        subtotal = price_kobo * quantity
        shipping = 200000  # ₦2,000
        total = subtotal + shipping

        order = Order.objects.create(
            order_number=f"ASO-{timezone.now().strftime('%Y%m%d%H%M%S')}-{self.vendor.id.hex[:4]}",
            customer=self.customer,
            vendor=self.vendor,
            subtotal_kobo=subtotal,
            delivery_fee_kobo=shipping,
            total_amount_kobo=total,
            order_status=OrderStatus.PENDING_PAYMENT,
            payment_expires_at=timezone.now() + timedelta(minutes=30),
            shipping_address_snapshot=self.address_snapshot
        )
        OrderItem.objects.create(
            order=order,
            variant=self.variant,
            product_title_snapshot=self.product.title,
            variant_size_snapshot=self.variant.size,
            variant_color_snapshot=self.variant.color,
            sku_snapshot=self.variant.sku,
            quantity=quantity,
            unit_price_kobo=price_kobo,
            total_price_kobo=subtotal
        )
        payment_req = PaymentRequest.objects.create(
            order=order,
            provider='PAYSTACK',
            amount_kobo=total,
            currency='NGN',
            reference=f"ASO-PAY-{order.id.hex[:10]}",
            status='PENDING'
        )

        # Simulate Paystack charge.success webhook
        payload_dict = {
            'event': 'charge.success',
            'data': {
                'reference': payment_req.reference,
                'amount': total,
                'currency': 'NGN',
                'status': 'success'
            }
        }
        raw_payload = json.dumps(payload_dict).encode('utf-8')
        signature = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode(),
            raw_payload,
            hashlib.sha512
        ).hexdigest()

        verify_and_process_webhook(raw_payload, signature)
        order.refresh_from_db()
        return order

    def test_pending_earnings_recorded_on_order_payment(self):
        """Test that Paystack payment automatically records pending earnings minus platform commission."""
        order = self._create_paid_order(quantity=1, price_kobo=5000000)  # ₦50,000
        self.assertEqual(order.order_status, OrderStatus.PAID)

        # 10% platform commission on ₦50,000 subtotal = ₦5,000. Vendor net earning = ₦45,000 (4,500,000 kobo)
        balance = get_or_create_vendor_balance(self.vendor)
        self.assertEqual(balance.pending_balance_kobo, 4500000)
        self.assertEqual(balance.available_balance_kobo, 0)
        self.assertEqual(balance.reserved_balance_kobo, 0)

        # Check ledger entry
        entry = LedgerEntry.objects.filter(order=order, entry_type=LedgerEntryType.EARNING_PENDING).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.amount_kobo, 4500000)
        self.assertEqual(entry.vendor, self.vendor)

    def test_pending_earnings_reversed_on_vendor_sla_timeout(self):
        """Test that vendor SLA timeout automatically refunds and cancels pending earnings."""
        order = self._create_paid_order(quantity=1, price_kobo=5000000)

        # Balance should have 4,500,000 kobo pending
        balance = get_or_create_vendor_balance(self.vendor)
        self.assertEqual(balance.pending_balance_kobo, 4500000)

        # Simulate SLA expiration
        order.vendor_accept_due_by = timezone.now() - timedelta(minutes=10)
        order.save(update_fields=['vendor_accept_due_by'])

        cancelled = process_vendor_sla_timeouts()
        self.assertEqual(cancelled, 1)

        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.CANCELLED)

        # Pending balance should be cleared back to 0
        balance.refresh_from_db()
        self.assertEqual(balance.pending_balance_kobo, 0)

        # Ledger should have REFUND entry
        refund_entry = LedgerEntry.objects.filter(order=order, entry_type=LedgerEntryType.REFUND).first()
        self.assertIsNotNone(refund_entry)
        self.assertEqual(refund_entry.amount_kobo, 4500000)

    def test_72_hour_escrow_protection_window_releases_available_funds(self):
        """Test that 72h after delivery, escrow funds move from pending to available."""
        order = self._create_paid_order(quantity=1, price_kobo=5000000)
        order.order_status = OrderStatus.DELIVERED
        order.save(update_fields=['order_status'])

        # Create Delivery marked DELIVERED 73 hours ago
        delivered_timestamp = timezone.now() - timedelta(hours=73)
        delivery = Delivery.objects.create(
            order=order,
            tracking_number=f"TRK-{order.id.hex[:8].upper()}",
            carrier_name='MANUAL_DISPATCH',
            status=DeliveryStatus.DELIVERED,
            delivered_at=delivered_timestamp
        )

        # Run process_completed_orders command / service
        completed_count = process_completed_orders()
        self.assertEqual(completed_count, 1)

        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.COMPLETED)

        # Balance check: pending 0, available 4,500,000 kobo
        balance = get_or_create_vendor_balance(self.vendor)
        self.assertEqual(balance.pending_balance_kobo, 0)
        self.assertEqual(balance.available_balance_kobo, 4500000)
        self.assertEqual(balance.reserved_balance_kobo, 0)

        # Ledger check
        release_entry = LedgerEntry.objects.filter(
            order=order,
            entry_type=LedgerEntryType.EARNING_RELEASE_TO_AVAILABLE
        ).first()
        self.assertIsNotNone(release_entry)
        self.assertEqual(release_entry.amount_kobo, 4500000)

    def test_management_command_process_completed_orders(self):
        """Test management command 'process_completed_orders' executes cleanly."""
        order = self._create_paid_order(quantity=1, price_kobo=5000000)
        order.order_status = OrderStatus.DELIVERED
        order.save(update_fields=['order_status'])

        Delivery.objects.create(
            order=order,
            tracking_number=f"TRK-CMD-{order.id.hex[:8].upper()}",
            status=DeliveryStatus.DELIVERED,
            delivered_at=timezone.now() - timedelta(hours=80)
        )

        call_command('process_completed_orders')
        order.refresh_from_db()
        self.assertEqual(order.order_status, OrderStatus.COMPLETED)

    def test_vendor_balance_api_view(self):
        """Test GET /api/v1/payouts/balance/ endpoint."""
        self.client.force_authenticate(user=self.vendor_user)

        # Seed some available balance
        balance = get_or_create_vendor_balance(self.vendor)
        balance.available_balance_kobo = 4500000
        balance.pending_balance_kobo = 1000000
        balance.reserved_balance_kobo = 0
        balance.save()

        response = self.client.get('/api/v1/payouts/balance/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['balance']
        self.assertEqual(data['available_balance'], 4500000)
        self.assertEqual(data['pending_balance'], 1000000)
        self.assertEqual(data['available_balance_naira'], 45000.0)

    def test_payout_withdrawal_reserves_funds_and_rejects_overdraw(self):
        """Test POST /api/v1/payouts/withdraw/ reserves funds and validates sufficiency."""
        self.client.force_authenticate(user=self.vendor_user)

        # Seed available balance of ₦45,000 (4,500,000 kobo)
        balance = get_or_create_vendor_balance(self.vendor)
        balance.available_balance_kobo = 4500000
        balance.pending_balance_kobo = 0
        balance.reserved_balance_kobo = 0
        balance.save()

        # Step 1: Successful withdrawal of ₦40,000
        withdraw_payload = {'amount_kobo': 4000000}
        response = self.client.post('/api/v1/payouts/withdraw/', data=withdraw_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        balance.refresh_from_db()
        self.assertEqual(balance.available_balance_kobo, 500000)  # ₦5,000 left
        self.assertEqual(balance.reserved_balance_kobo, 4000000)  # ₦40,000 reserved

        # Check payout request record
        payout_req = PayoutRequest.objects.filter(vendor=self.vendor).first()
        self.assertIsNotNone(payout_req)
        self.assertEqual(payout_req.amount_kobo, 4000000)
        self.assertIn(payout_req.status, [PayoutStatus.PAYOUT_RESERVED, PayoutStatus.PROCESSING])

        # Step 2: Attempting to withdraw ₦10,000 when only ₦5,000 is available
        overdraw_payload = {'amount_kobo': 1000000}
        overdraw_resp = self.client.post('/api/v1/payouts/withdraw/', data=overdraw_payload, format='json')
        self.assertEqual(overdraw_resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_payout_failure_restores_reserved_funds(self):
        """Test that fail_payout service restores reserved funds back to available balance."""
        balance = get_or_create_vendor_balance(self.vendor)
        balance.available_balance_kobo = 5000000
        balance.save()

        # Request payout of ₦50,000
        payout_req = request_payout(self.vendor, 5000000)
        balance.refresh_from_db()
        self.assertEqual(balance.available_balance_kobo, 0)
        self.assertEqual(balance.reserved_balance_kobo, 5000000)

        # Fail the payout
        fail_payout(payout_req, "Paystack bank network error")
        payout_req.refresh_from_db()
        self.assertEqual(payout_req.status, PayoutStatus.FAILED)
        self.assertEqual(payout_req.failure_reason, "Paystack bank network error")

        # Reserved funds must be restored to available
        balance.refresh_from_db()
        self.assertEqual(balance.available_balance_kobo, 5000000)
        self.assertEqual(balance.reserved_balance_kobo, 0)

    def test_payout_success_clears_reserved_funds(self):
        """Test that succeed_payout service clears reserved funds."""
        balance = get_or_create_vendor_balance(self.vendor)
        balance.available_balance_kobo = 5000000
        balance.save()

        payout_req = request_payout(self.vendor, 5000000)
        balance.refresh_from_db()
        self.assertEqual(balance.reserved_balance_kobo, 5000000)

        # Admin approves -> transfer initiated (PROCESSING); then Paystack confirms success
        payout_req = process_payout(payout_req)
        self.assertEqual(payout_req.status, PayoutStatus.PROCESSING)
        succeed_payout(payout_req)
        succeed_payout(payout_req)  # replayed webhook must be a no-op
        succeed_payout(payout_req)
        payout_req.refresh_from_db()
        self.assertEqual(payout_req.status, PayoutStatus.SUCCESSFUL)

        balance.refresh_from_db()
        self.assertEqual(balance.available_balance_kobo, 0)
        self.assertEqual(balance.reserved_balance_kobo, 0)

    def test_kyc_submission_goes_to_admin_review_and_only_admin_can_verify(self):
        """Nov 2026 policy: submitting NIN/CAC never self-verifies; an Aso admin approves."""
        from apps.vendors.models import VerificationStatus
        from apps.vendors.services import approve_verification, reject_verification

        self.vendor.is_verified = False
        self.vendor.verification_status = VerificationStatus.NOT_SUBMITTED
        self.vendor.save(update_fields=['is_verified', 'verification_status'])
        self.client.force_authenticate(user=self.vendor_user)

        response = self.client.post('/api/v1/vendors/verify-kyc/', {'nin': '12345678901'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.vendor.refresh_from_db()
        self.assertEqual(self.vendor.verification_status, VerificationStatus.PENDING_REVIEW)
        self.assertFalse(self.vendor.is_verified)
        self.assertEqual(self.vendor.kyc_tier, KYCTier.TIER_1_STARTER)

        # Invalid NIN is rejected outright
        bad = self.client.post('/api/v1/vendors/verify-kyc/', {'nin': '123'}, format='json')
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

        # Admin rejects -> designer sees reason; admin approves -> badge granted
        reject_verification(self.vendor, reviewer=None, reason='NIN name does not match account name')
        self.vendor.refresh_from_db()
        self.assertEqual(self.vendor.verification_status, VerificationStatus.REJECTED)
        self.assertIn('does not match', self.vendor.verification_rejection_reason)

        approve_verification(self.vendor, reviewer=None)
        self.vendor.refresh_from_db()
        self.assertTrue(self.vendor.is_verified)
        self.assertEqual(self.vendor.kyc_tier, KYCTier.TIER_2_VERIFIED)

        # Changing NIN after verification removes the badge and re-queues for review
        self.vendor.nin_number = '10987654321'
        self.vendor.save(update_fields=['nin_number'])
        self.vendor.refresh_from_db()
        self.assertFalse(self.vendor.is_verified)
        self.assertEqual(self.vendor.verification_status, VerificationStatus.PENDING_REVIEW)
