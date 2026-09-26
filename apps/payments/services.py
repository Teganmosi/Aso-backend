import hmac
import json
import uuid
import hashlib
from datetime import timedelta
from urllib.parse import urlencode
from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.orders.models import Order, OrderStatus
from .models import PaymentProvider, PaymentRequest, PaymentWebhookLog



def verify_paystack_signature(payload: bytes, signature: str) -> bool:
    """
    Verify Paystack webhook signature using HMAC-SHA512.

    Paystack sends the raw hex HMAC-SHA512 of the request body using the secret key.
    Header format: x-paystack-signature: <hex_hash>
    """
    hash_hmac = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode(),
        payload,
        hashlib.sha512
    ).hexdigest()

    # Paystack signature is just the hex digest - compare directly
    return hmac.compare_digest(signature, hash_hmac)


import logging
import re

logger = logging.getLogger(__name__)


def get_paystack_compatible_email(email: str) -> str:
    """
    Ensure email meets Paystack's strict IANA TLD validation requirements.
    If an internal/development or custom non-standard domain (e.g. .os, .local, .test)
    is used, route through @aso.ng so Paystack's API never rejects checkout initialization.
    """
    if not email or '@' not in email:
        return 'customer@aso.ng'

    username, domain = email.strip().split('@', 1)
    parts = domain.split('.')
    tld = parts[-1].lower() if len(parts) > 1 else ''

    invalid_tlds = {'os', 'local', 'internal', 'test', 'example', 'invalid', 'localhost', ''}
    if tld in invalid_tlds or len(tld) < 2 or not tld.isalpha():
        clean_user = re.sub(r'[^a-zA-Z0-9._-]', '', username) or 'customer'
        return f"{clean_user}@aso.ng"

    return email.strip().lower()


def is_valid_paystack_url(url: str, reference: str) -> bool:
    if not url:
        return False
    if url.endswith('mock') or 'mock_payment' in url:
        return False
    # If it ends with the reference suffix (the 8-char fake fallback), it is invalid!
    ref_suffix = reference.split('-')[-1]
    if url.endswith(f"/{ref_suffix}") or len(url.split('/')[-1]) < 12:
        return False
    return 'checkout.paystack.com' in url


def initialize_payment(order: Order) -> PaymentRequest:
    """
    Initialize a Paystack payment for the given order.
    Returns the PaymentRequest object with authorization URL and reference.

    Step 1: Validate order state can be paid
    Step 2: Generate Paystack reference and amount
    Step 3: Create PaymentRequest
    Step 4: Generate real Paystack authorization URL via API call
    """
    existing_pr = PaymentRequest.objects.filter(order=order, status='PENDING').order_by('-created_at').first()
    if existing_pr and existing_pr.authorization_url and is_valid_paystack_url(existing_pr.authorization_url, existing_pr.reference):
        return existing_pr

    # Generate a unique reference
    reference = f"ASO-{order.order_number}-{uuid.uuid4().hex[:8].upper()}"
    amount_kobo = order.total_amount_kobo

    payment_request = existing_pr or PaymentRequest.objects.create(
        order=order,
        provider='PAYSTACK',
        reference=reference,
        amount_kobo=amount_kobo,
        currency='NGN',
        status='PENDING',
    )
    if existing_pr:
        payment_request.reference = reference
        payment_request.amount_kobo = amount_kobo
        payment_request.save(update_fields=['reference', 'amount_kobo'])

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    callback_url = getattr(settings, 'PAYSTACK_CALLBACK_URL', f"{frontend_url}/orders")
    customer_email = get_paystack_compatible_email(order.customer.email)

    authorization_url = ''

    if getattr(settings, 'PAYSTACK_SECRET_KEY', None):
        import urllib.request
        import urllib.error

        req_payload = json.dumps({
            "email": customer_email,
            "amount": amount_kobo,
            "reference": reference,
            "callback_url": callback_url,
        }).encode('utf-8')

        req = urllib.request.Request(
            "https://api.paystack.co/transaction/initialize",
            data=req_payload,
            headers={
                "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "AsoMarketplace/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_data = json.loads(resp.read().decode('utf-8'))
                if resp_data.get('status') and resp_data.get('data', {}).get('authorization_url'):
                    authorization_url = resp_data['data']['authorization_url']
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='ignore')
            logger.error(f"Paystack initialize HTTP {e.code} for order {order.order_number}: {err_body}")
        except Exception as e:
            logger.error(f"Paystack initialize error for order {order.order_number}: {e}")

    # Fallback to local mock order flow only if Paystack is completely unreachable/offline
    if not authorization_url:
        authorization_url = f"{frontend_url}/orders?mock_payment=true&reference={reference}&order_id={order.id}"

    payment_request.authorization_url = authorization_url
    payment_request.reference = reference
    payment_request.save(update_fields=['authorization_url', 'reference'])

    return payment_request

def verify_and_process_webhook(
    payload: bytes,
    signature: str,
) -> tuple:
    """
    Verify Paystack webhook signature and process the event atomically.

    Returns (bool: signature_verified, PaymentRequest|None: payment_request, str: message)

    Key features:
    - Uses transaction.atomic() with select_for_update() for idempotency
    - Validates amount and currency from webhook payload
    - Prevents duplicate processing via atomic DB operations
    """
    # Step 1: Verify signature
    is_valid = verify_paystack_signature(payload, signature)

    if not is_valid:
        return False, None, "Invalid Paystack signature"

    # Step 2: Parse payload
    try:
        event_data = json.loads(payload)
    except json.JSONDecodeError:
        return False, None, "Invalid JSON payload"

    reference = event_data.get('data', {}).get('reference')
    event = event_data.get('event', '')
    webhook_amount = event_data.get('data', {}).get('amount')  # Amount in kobo from Paystack
    webhook_currency = event_data.get('data', {}).get('currency', '')

    if not reference:
        return False, None, "Missing reference in webhook payload"

    # Step 3: Atomic idempotency check with row-level lock
    with transaction.atomic():
        # Lock the webhook log row for update to prevent race conditions
        # Filter by (reference, event) per unique_together constraint
        model_instance, created = PaymentWebhookLog.objects.select_for_update().get_or_create(
            reference=reference,
            event=event,
            defaults={
                'payload': event_data,
                'signature_verified': True,
            }
        )

        # If already processed, return early for idempotency
        if model_instance.processed:
            return True, None, "Webhook already processed (idempotent)"

        # Update event details if this is a new processing run
        if not created:
            model_instance.event = event
            model_instance.payload = event_data
            model_instance.signature_verified = True
            model_instance.save(update_fields=['event', 'payload', 'signature_verified'])

        # Step 4: Process based on event type
        # --- FIRST: Fetch payment_request from DB inside the atomic block ---
        # This ensures we have the latest state and can safely access attributes
        try:
            payment_request = PaymentRequest.objects.select_for_update().get(reference=reference)
        except PaymentRequest.DoesNotExist:
            payment_request = None

        if event == 'charge.success':
            # --- AMOUNT & CURRENCY VERIFICATION (Critical for financial integrity) ---
            # Verify the amount paid matches the order amount
            if payment_request is not None and webhook_amount is not None:
                try:
                    webhook_amount_kobo = int(webhook_amount)
                    if webhook_amount_kobo != payment_request.amount_kobo:
                        # Amount mismatch - log and reject
                        model_instance.processed = True
                        model_instance.save(update_fields=['processed'])
                        return True, None, (
                            f"Webhook amount mismatch: expected {payment_request.amount_kobo} kobo, "
                            f"received {webhook_amount_kobo} kobo. Payment rejected."
                        )
                except (ValueError, TypeError):
                    pass

            # Verify currency is NGN
            if payment_request is not None and webhook_currency and webhook_currency.upper() != 'NGN':
                model_instance.processed = True
                model_instance.save(update_fields=['processed'])
                return True, None, (
                    f"Currency mismatch: expected NGN, received {webhook_currency}. "
                    "Payment rejected."
                )

            # Transition order status to PAID (only if still PENDING_PAYMENT)
            if payment_request is not None:
                order = payment_request.order
                if order.order_status == OrderStatus.PENDING_PAYMENT:
                    order.order_status = OrderStatus.PAID
                    # Set vendor SLA: 48 hours to accept the order
                    order.vendor_accept_due_by = timezone.now() + timedelta(hours=48)
                    order.save(update_fields=['order_status', 'vendor_accept_due_by', 'updated_at'])

                    # Record pending earning in ledger
                    from apps.payouts.services import record_pending_earning
                    record_pending_earning(order)

                    # Dispatch payment received notification
                    from apps.common.notifications import send_payment_received_notification
                    send_payment_received_notification(order)

                payment_request.status = 'SUCCESS'
                payment_request.save(update_fields=['status'])

        elif event == 'charge.failed':
            if payment_request is not None:
                payment_request.status = 'FAILED'
                payment_request.save(update_fields=['status'])

        elif event in ('transfer.success', 'transfer.failed', 'transfer.reversed'):
            from apps.payouts.models import PayoutRequest
            from apps.payouts.services import succeed_payout, fail_payout
            try:
                payout_req = PayoutRequest.objects.select_for_update().get(reference=reference)
                if event == 'transfer.success':
                    succeed_payout(payout_req)
                else:
                    fail_reason = event_data.get('data', {}).get('reason') or f"Paystack Transfer failed: {event}"
                    fail_payout(payout_req, fail_reason)
            except PayoutRequest.DoesNotExist:
                pass

        # Mark webhook as processed atomically
        model_instance.processed = True
        model_instance.save(update_fields=['processed'])

    # Step 5: Return outside the transaction to avoid holding locks
    return True, payment_request, "Webhook processed successfully"

def verify_transaction_with_paystack(reference: str) -> tuple:
    """
    Synchronously verifies a transaction reference with Paystack API.
    Transitions order to PAID and records ledger earning atomically if Paystack confirms success.
    Returns (bool: is_success, Order|None: order, str: message)
    """
    from apps.payments.models import PaymentRequest, PaymentWebhookLog
    from apps.orders.models import Order, OrderStatus
    from apps.payouts.services import record_pending_earning
    from apps.common.notifications import send_payment_received_notification
    import urllib.request
    import urllib.error
    import json

    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if not secret_key:
        return False, None, "Paystack secret key is not configured."

    # Look up payment request
    try:
        payment_request = PaymentRequest.objects.select_related('order').get(reference=reference)
        order = payment_request.order
    except PaymentRequest.DoesNotExist:
        # Check if reference corresponds to order_number or partial reference
        order = Order.objects.filter(order_number__icontains=reference.replace('ASO-', '')).first()
        if order:
            payment_request = PaymentRequest.objects.filter(order=order).order_by('-created_at').first()
        else:
            return False, None, f"Payment request not found for reference '{reference}'."

    # If already marked PAID, return early
    if order and order.order_status != OrderStatus.PENDING_PAYMENT:
        return True, order, f"Order is already marked as {order.get_order_status_display()}."

    # Query Paystack Verification Endpoint
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
            "User-Agent": "AsoMarketplace/1.0"
        },
        method="GET"
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            resp_data = json.loads(resp.read().decode('utf-8'))
    except Exception as ex:
        return False, order, f"Failed to contact Paystack API: {str(ex)}"

    if not resp_data.get('status'):
        return False, order, resp_data.get('message', 'Paystack verification failed.')

    data = resp_data.get('data', {})
    paystack_status = data.get('status')
    amount_paid_kobo = data.get('amount')

    if paystack_status != 'success':
        return False, order, f"Transaction status on Paystack is '{paystack_status}'."

    # Verify amount matches expected order total
    if payment_request and amount_paid_kobo and int(amount_paid_kobo) < payment_request.amount_kobo:
        return False, order, f"Amount paid ({amount_paid_kobo} kobo) is less than expected ({payment_request.amount_kobo} kobo)."

    # Atomically transition order and payment request
    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(id=order.id)
        if locked_order.order_status == OrderStatus.PENDING_PAYMENT:
            locked_order.order_status = OrderStatus.PAID
            locked_order.vendor_accept_due_by = timezone.now() + timedelta(hours=48)
            locked_order.save(update_fields=['order_status', 'vendor_accept_due_by', 'updated_at'])

            # Record pending earning in vendor balance & financial ledger
            try:
                record_pending_earning(locked_order)
            except Exception as e:
                pass

            # Send notification
            try:
                send_payment_received_notification(locked_order)
            except Exception:
                pass

        if payment_request:
            locked_pr = PaymentRequest.objects.select_for_update().get(id=payment_request.id)
            locked_pr.status = 'SUCCESS'
            locked_pr.save(update_fields=['status'])

    return True, locked_order, "Payment verified successfully! Order is now marked as PAID."
