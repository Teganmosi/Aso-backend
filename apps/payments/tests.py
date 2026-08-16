import hmac
import hashlib
import json
import uuid
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.orders.models import Order, OrderStatus
from apps.accounts.models import User
from apps.vendors.models import VendorProfile
from apps.payments.models import PaymentProvider, PaymentRequest, PaymentWebhookLog
from apps.payments.services import (
    verify_paystack_signature,
    initialize_payment,
    verify_and_process_webhook,
)

PAYSTACK_SECRET_KEY = 'sk_test_mock_paystack_secret_key_12345'


class PaymentProviderModelTest(TestCase):
    """Test PaymentProvider model fields and behaviors."""

    def setUp(self):
        self.provider_data = {
            'name': 'PAYSTACK',
            'display_name': 'Paystack',
            'secret_key': PAYSTACK_SECRET_KEY,
            'public_key': 'pk_test_mock_paystack_public_key',
        }

    def test_create_payment_provider(self):
        """Test creating a PaymentProvider instance."""
        provider = PaymentProvider.objects.create(**self.provider_data)
        self.assertIsNotNone(provider.id)
        self.assertEqual(provider.name, 'PAYSTACK')
        self.assertTrue(provider.is_active)
        self.assertIsNotNone(provider.created_at)
        self.assertIsNotNone(provider.updated_at)

    def test_provider_str_representation(self):
        """Test __str__ method."""
        provider = PaymentProvider.objects.create(**self.provider_data)
        expected = "PAYSTACK (Paystack)"
        self.assertEqual(str(provider), expected)


class PaymentRequestModelTest(TestCase):
    """Test PaymentRequest model fields and behaviors."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@customer.com',
            password='testpass123',
            first_name='Test',
            last_name='Customer',
            phone_number='08012345678',
        )

        self.vendor_user = User.objects.create_user(
            email='vendor@store.com',
            password='testpass123',
            first_name='Vendor',
            last_name='User',
            phone_number='08087654321',
        )

        self.vendor = VendorProfile.objects.create(
            user=self.vendor_user,
            store_name='Test Designer Store',
            slug='test-designer-store',
            description='Test vendor storefront description',
            city='Lagos',
            state='Lagos',
            status='APPROVED',
        )

        self.order = Order.objects.create(
            order_number='ASO-20260816-ABC123',
            customer=self.user,
            vendor=self.vendor,
            order_status=OrderStatus.PENDING_PAYMENT,
            subtotal_kobo=1000000,  # ₦10,000
            total_amount_kobo=1000000,
            payment_expires_at=timezone.now() + timezone.timedelta(minutes=30),
            shipping_address_snapshot={'address': '123 Victoria Island, Lagos'},
        )

    def test_create_payment_request(self):
        """Test creating a PaymentRequest instance."""
        payment_request = PaymentRequest.objects.create(
            order=self.order,
            provider='PAYSTACK',
            reference='ASO-TEST-REF-12345',
            amount_kobo=1000000,
            currency='NGN',
            status='PENDING',
        )
        self.assertIsNotNone(payment_request.id)
        self.assertEqual(payment_request.order, self.order)
        self.assertEqual(payment_request.amount_kobo, 1000000)
        self.assertEqual(payment_request.currency, 'NGN')
        self.assertEqual(payment_request.status, 'PENDING')

    def test_payment_request_str(self):
        """Test __str__ method."""
        payment_request = PaymentRequest.objects.create(
            order=self.order,
            reference='ASO-TEST-REF',
            amount_kobo=1000000,
            currency='NGN',
        )
        expected = f"Payment Request ASO-TEST-REF for Order {self.order.order_number}"
        self.assertEqual(str(payment_request), expected)

    def test_reference_unique_constraint(self):
        """Test that reference field has unique constraint."""
        PaymentRequest.objects.create(
            order=self.order,
            reference='UNIQUE-REF-001',
            amount_kobo=1000000,
            currency='NGN',
        )
        with self.assertRaises(Exception):
            PaymentRequest.objects.create(
                order=self.order,
                reference='UNIQUE-REF-001',  # Duplicate reference
                amount_kobo=500000,
                currency='NGN',
            )


class PaymentWebhookLogModelTest(TestCase):
    """Test PaymentWebhookLog model fields and behaviors."""

    def test_create_webhook_log(self):
        """Test creating a PaymentWebhookLog instance."""
        payload = {'event': 'charge.success', 'data': {'reference': 'WH-REF-12345'}}
        webhook_log = PaymentWebhookLog.objects.create(
            reference='WH-REF-12345',
            event='charge.success',
            payload=payload,
            signature_verified=True,
        )
        self.assertIsNotNone(webhook_log.id)
        self.assertEqual(webhook_log.reference, 'WH-REF-12345')
        self.assertEqual(webhook_log.event, 'charge.success')
        self.assertTrue(webhook_log.signature_verified)
        self.assertFalse(webhook_log.processed)
        self.assertIsNotNone(webhook_log.created_at)

    def test_webhook_log_str_representation(self):
        """Test __str__ method."""
        webhook_log = PaymentWebhookLog.objects.create(
            reference='STR-TEST-REF',
            event='charge.failed',
            payload={},
        )
        expected = "Webhook charge.failed for reference STR-TEST-REF"
        self.assertEqual(str(webhook_log), expected)

    def test_unique_together_reference_event(self):
        """Test that (reference, event) uniqueness constraint works."""
        PaymentWebhookLog.objects.create(
            reference='UNIQUE-WH-REF',
            event='charge.success',
            payload={},
        )
        # Creating another log with same reference but different event should succeed
        webhook_log2 = PaymentWebhookLog.objects.create(
            reference='UNIQUE-WH-REF',
            event='charge.failed',
            payload={},
        )
        self.assertIsNotNone(webhook_log2.id)

        # Creating another log with same reference AND same event should fail
        with self.assertRaises(Exception):
            PaymentWebhookLog.objects.create(
                reference='UNIQUE-WH-REF',
                event='charge.success',
                payload={},
            )


@override_settings(PAYSTACK_SECRET_KEY=PAYSTACK_SECRET_KEY)
class SignatureVerificationTest(TestCase):
    """Test Paystack HMAC-SHA512 signature verification."""

    def test_valid_signature(self):
        """Test that a valid signature is accepted."""
        payload = b'{"test": "payload", "reference": "ASO-12345"}'
        expected_signature = hmac.new(
            PAYSTACK_SECRET_KEY.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()

        is_valid = verify_paystack_signature(payload, expected_signature)
        self.assertTrue(is_valid)

    def test_invalid_signature(self):
        """Test that an invalid signature is rejected."""
        payload = b'{"test": "payload"}'
        fake_signature = 'invalid_signature_hex_string_that_does_not_match'
        is_valid = verify_paystack_signature(payload, fake_signature)
        self.assertFalse(is_valid)

    def test_tampered_payload_fails(self):
        """Test that signature fails if payload is tampered with."""
        original_payload = b'{"amount": 1000}'
        tampered_payload = b'{"amount": 5000}'
        sig = hmac.new(
            PAYSTACK_SECRET_KEY.encode('utf-8'),
            original_payload,
            hashlib.sha512
        ).hexdigest()

        is_valid = verify_paystack_signature(tampered_payload, sig)
        self.assertFalse(is_valid)


@override_settings(PAYSTACK_SECRET_KEY=PAYSTACK_SECRET_KEY)
class PaymentInitializationTest(TestCase):
    """Test payment initialization endpoint logic and service."""

    def setUp(self):
        self.client = APIClient()

        self.customer = User.objects.create_user(
            email='customer@example.com',
            password='password123',
            first_name='Chioma',
            last_name='Adeyemi',
            phone_number='08011112222',
        )

        self.other_customer = User.objects.create_user(
            email='other@example.com',
            password='password123',
            first_name='Tunde',
            last_name='Bakare',
            phone_number='08033334444',
        )

        self.vendor_user = User.objects.create_user(
            email='vendor@aso.ng',
            password='password123',
            first_name='Lagos',
            last_name='Luxe',
            phone_number='08055556666',
        )

        self.vendor = VendorProfile.objects.create(
            user=self.vendor_user,
            store_name='Lagos Luxe Native',
            slug='lagos-luxe-native',
            description='Premium African bespoke tailoring',
            city='Lagos',
            state='Lagos',
            status='APPROVED',
        )

        self.order = Order.objects.create(
            order_number='ASO-20260816-PAY001',
            customer=self.customer,
            vendor=self.vendor,
            order_status=OrderStatus.PENDING_PAYMENT,
            subtotal_kobo=7500000,  # ₦75,000
            total_amount_kobo=7500000,
            payment_expires_at=timezone.now() + timezone.timedelta(minutes=30),
            shipping_address_snapshot={'city': 'Lagos', 'state': 'Lagos'},
        )

    def test_service_initialize_payment_creates_request(self):
        """Test initialize_payment service creates a PaymentRequest."""
        payment_request = initialize_payment(self.order)
        self.assertIsNotNone(payment_request)
        self.assertEqual(payment_request.order, self.order)
        self.assertEqual(payment_request.amount_kobo, 7500000)
        self.assertEqual(payment_request.currency, 'NGN')
        self.assertEqual(payment_request.status, 'PENDING')
        self.assertTrue(payment_request.reference.startswith(f"ASO-{self.order.order_number}"))
        self.assertTrue(payment_request.authorization_url.startswith('https://checkout.paystack.com/'))

    def test_api_initialize_payment_unauthenticated_fails(self):
        """Test that unauthenticated requests to initialize endpoint are rejected."""
        url = reverse('payment-initialize')
        response = self.client.post(url, {'order_id': str(self.order.id)}, format='json')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_api_initialize_payment_success(self):
        """Test authenticated customer initializing payment for their order."""
        self.client.force_authenticate(user=self.customer)
        url = reverse('payment-initialize')
        response = self.client.post(url, {'order_id': str(self.order.id)}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        data = response.data['data']
        self.assertEqual(str(data['order']), str(self.order.id))
        self.assertEqual(data['amount_kobo'], 7500000)
        self.assertEqual(data['currency'], 'NGN')
        self.assertIn('authorization_url', data)
        self.assertIn('reference', data)

    def test_api_initialize_payment_wrong_user_forbidden(self):
        """Test customer cannot initialize payment for another user's order."""
        self.client.force_authenticate(user=self.other_customer)
        url = reverse('payment-initialize')
        response = self.client.post(url, {'order_id': str(self.order.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_initialize_payment_already_paid_fails(self):
        """Test cannot initialize payment on an already PAID order."""
        self.order.order_status = OrderStatus.PAID
        self.order.save(update_fields=['order_status'])

        self.client.force_authenticate(user=self.customer)
        url = reverse('payment-initialize')
        response = self.client.post(url, {'order_id': str(self.order.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot initialize payment', response.data['detail'])

    def test_api_initialize_payment_expired_order_fails(self):
        """Test cannot initialize payment on an expired order."""
        self.order.payment_expires_at = timezone.now() - timezone.timedelta(minutes=5)
        self.order.save(update_fields=['payment_expires_at'])

        self.client.force_authenticate(user=self.customer)
        url = reverse('payment-initialize')
        response = self.client.post(url, {'order_id': str(self.order.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('reservation window', response.data['detail'])


@override_settings(PAYSTACK_SECRET_KEY=PAYSTACK_SECRET_KEY)
class WebhookProcessingTest(TestCase):
    """Test Paystack webhook signature verification, order transition, and idempotency."""

    def setUp(self):
        self.client = APIClient()

        self.customer = User.objects.create_user(
            email='customer@example.com',
            password='password123',
            first_name='Folake',
            last_name='Kuti',
            phone_number='08022223333',
        )

        self.vendor_user = User.objects.create_user(
            email='designer@aso.ng',
            password='password123',
            first_name='Abuja',
            last_name='Atelier',
            phone_number='08044445555',
        )

        self.vendor = VendorProfile.objects.create(
            user=self.vendor_user,
            store_name='Abuja Atelier',
            slug='abuja-atelier',
            description='Authentic northern & southern traditional wear',
            city='Abuja',
            state='FCT',
            status='APPROVED',
        )

        self.order = Order.objects.create(
            order_number='ASO-20260816-WHK001',
            customer=self.customer,
            vendor=self.vendor,
            order_status=OrderStatus.PENDING_PAYMENT,
            subtotal_kobo=5000000,  # ₦50,000
            total_amount_kobo=5000000,
            payment_expires_at=timezone.now() + timezone.timedelta(minutes=30),
            shipping_address_snapshot={'city': 'Abuja', 'state': 'FCT'},
        )

        self.payment_request = PaymentRequest.objects.create(
            order=self.order,
            reference='WH-TEST-REF-50000',
            amount_kobo=5000000,
            currency='NGN',
            status='PENDING',
        )

    def _generate_signature(self, payload_bytes: bytes) -> str:
        return hmac.new(
            PAYSTACK_SECRET_KEY.encode('utf-8'),
            payload_bytes,
            hashlib.sha512
        ).hexdigest()

    def test_charge_success_transitions_order_to_paid(self):
        """Test charge.success transitions order from PENDING_PAYMENT to PAID."""
        payload_data = {
            'event': 'charge.success',
            'data': {
                'reference': self.payment_request.reference,
                'amount': 5000000,
                'currency': 'NGN',
                'status': 'success',
            }
        }
        payload_bytes = json.dumps(payload_data).encode('utf-8')
        signature = self._generate_signature(payload_bytes)

        sig_verified, pr, message = verify_and_process_webhook(payload_bytes, signature)

        self.assertTrue(sig_verified)
        self.assertIsNotNone(pr)
        self.assertEqual(pr.status, 'SUCCESS')

        # Verify Order status mutated to PAID
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.PAID)

        # Verify PaymentWebhookLog record created
        log = PaymentWebhookLog.objects.get(reference=self.payment_request.reference, event='charge.success')
        self.assertTrue(log.signature_verified)
        self.assertTrue(log.processed)

    def test_webhook_idempotency_duplicate_request(self):
        """Test that resending the same webhook event is fully idempotent without duplicate operations."""
        payload_data = {
            'event': 'charge.success',
            'data': {
                'reference': self.payment_request.reference,
                'amount': 5000000,
                'currency': 'NGN',
                'status': 'success',
            }
        }
        payload_bytes = json.dumps(payload_data).encode('utf-8')
        signature = self._generate_signature(payload_bytes)

        # First call
        sig_verified1, pr1, msg1 = verify_and_process_webhook(payload_bytes, signature)
        self.assertTrue(sig_verified1)
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.PAID)

        # Second call (replay)
        sig_verified2, pr2, msg2 = verify_and_process_webhook(payload_bytes, signature)
        self.assertTrue(sig_verified2)
        self.assertIn('idempotent', msg2.lower())

        # Ensure only 1 log row exists for this reference and event
        log_count = PaymentWebhookLog.objects.filter(
            reference=self.payment_request.reference,
            event='charge.success'
        ).count()
        self.assertEqual(log_count, 1)

    def test_charge_success_amount_mismatch_rejected(self):
        """Test charge.success with amount tampering is rejected and order remains PENDING_PAYMENT."""
        payload_data = {
            'event': 'charge.success',
            'data': {
                'reference': self.payment_request.reference,
                'amount': 1000,  # 10 Naira instead of 50,000 Naira
                'currency': 'NGN',
                'status': 'success',
            }
        }
        payload_bytes = json.dumps(payload_data).encode('utf-8')
        signature = self._generate_signature(payload_bytes)

        sig_verified, pr, message = verify_and_process_webhook(payload_bytes, signature)

        self.assertTrue(sig_verified)
        self.assertIn('amount mismatch', message.lower())

        # Order must remain PENDING_PAYMENT
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.PENDING_PAYMENT)

    def test_charge_success_currency_mismatch_rejected(self):
        """Test charge.success with wrong currency is rejected."""
        payload_data = {
            'event': 'charge.success',
            'data': {
                'reference': self.payment_request.reference,
                'amount': 5000000,
                'currency': 'USD',  # USD instead of NGN
                'status': 'success',
            }
        }
        payload_bytes = json.dumps(payload_data).encode('utf-8')
        signature = self._generate_signature(payload_bytes)

        sig_verified, pr, message = verify_and_process_webhook(payload_bytes, signature)

        self.assertTrue(sig_verified)
        self.assertIn('currency mismatch', message.lower())

        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.PENDING_PAYMENT)

    def test_charge_failed_updates_payment_request(self):
        """Test charge.failed marks payment request as FAILED."""
        payload_data = {
            'event': 'charge.failed',
            'data': {
                'reference': self.payment_request.reference,
                'amount': 5000000,
                'currency': 'NGN',
            }
        }
        payload_bytes = json.dumps(payload_data).encode('utf-8')
        signature = self._generate_signature(payload_bytes)

        sig_verified, pr, message = verify_and_process_webhook(payload_bytes, signature)

        self.assertTrue(sig_verified)
        self.payment_request.refresh_from_db()
        self.assertEqual(self.payment_request.status, 'FAILED')

    def test_api_webhook_endpoint_success(self):
        """Test HTTP POST /api/v1/payments/webhook/paystack/ end-to-end."""
        payload_data = {
            'event': 'charge.success',
            'data': {
                'reference': self.payment_request.reference,
                'amount': 5000000,
                'currency': 'NGN',
            }
        }
        payload_bytes = json.dumps(payload_data).encode('utf-8')
        signature = self._generate_signature(payload_bytes)

        url = reverse('payment-webhook-paystack')
        response = self.client.post(
            url,
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, OrderStatus.PAID)

    def test_api_webhook_invalid_signature_returns_400(self):
        """Test HTTP POST /api/v1/payments/webhook/paystack/ with bad signature returns 400."""
        payload_data = {
            'event': 'charge.success',
            'data': {'reference': self.payment_request.reference}
        }
        url = reverse('payment-webhook-paystack')
        response = self.client.post(
            url,
            data=payload_data,
            format='json',
            HTTP_X_PAYSTACK_SIGNATURE='bogus_invalid_signature',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)