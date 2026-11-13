import logging
from django.conf import settings
from django.core.mail import send_mail
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_transactional_email(subject: str, html_message: str, recipient_list: list[str]) -> bool:
    """
    Safely sends a transactional HTML email without breaking database transactions or business logic.
    """
    if not recipient_list:
        return False

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Aso Marketplace <hello@asomarketplace.com.ng>')
    plain_message = strip_tags(html_message)

    try:
        sent = send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=False,
        )
        logger.info("Transactional email '%s' sent to %d recipient(s)", subject, sent)
        return bool(sent)
    except Exception as e:
        logger.error("Failed to send transactional email '%s': %s", subject, e)
        return False


def send_order_placed_notification(order) -> bool:
    """
    Sends order placement confirmation email to customer.
    """
    customer_email = order.customer.email
    subject = f"Order #{order.order_number} Placed — Aso Marketplace"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #111827;">Thank you for your order!</h2>
        <p>Dear {order.customer.first_name},</p>
        <p>Your order <strong>#{order.order_number}</strong> with <strong>{order.vendor.store_name}</strong> has been received.</p>
        <p><strong>Total Amount:</strong> ₦{order.total_amount_naira:,.2f}</p>
        <p>We are waiting for payment confirmation to proceed with tailoring and fulfillment.</p>
        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 20px 0;" />
        <p style="color: #6B7280; font-size: 12px;">Aso Marketplace — Connecting Nigerian Tailors with Fashion Lovers</p>
    </div>
    """
    return send_transactional_email(subject, html_content, [customer_email])


def send_payment_received_notification(order) -> bool:
    """
    Sends payment confirmation email to customer and notification to vendor.
    """
    customer_email = order.customer.email
    vendor_email = order.vendor.user.email
    
    # Customer Email
    subject_customer = f"Payment Confirmed: Order #{order.order_number} — Aso Marketplace"
    html_customer = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #059669;">Payment Confirmed!</h2>
        <p>Dear {order.customer.first_name},</p>
        <p>We have received your payment of <strong>₦{order.total_amount_naira:,.2f}</strong> for Order <strong>#{order.order_number}</strong>.</p>
        <p>The designer <strong>{order.vendor.store_name}</strong> has been notified and has 48 hours to accept and start preparing your garment.</p>
        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 20px 0;" />
        <p style="color: #6B7280; font-size: 12px;">Aso Marketplace</p>
    </div>
    """
    send_transactional_email(subject_customer, html_customer, [customer_email])

    # Vendor Email
    subject_vendor = f"New Paid Order #{order.order_number} Received! — Action Required"
    html_vendor = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #111827;">New Paid Order Received!</h2>
        <p>Hello {order.vendor.store_name},</p>
        <p>You have received a new paid order <strong>#{order.order_number}</strong>.</p>
        <p><strong>Subtotal:</strong> ₦{order.subtotal_naira:,.2f}</p>
        <p>Please log in to your vendor dashboard and accept the order within 48 hours to meet the fulfillment SLA.</p>
        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 20px 0;" />
        <p style="color: #6B7280; font-size: 12px;">Aso Marketplace</p>
    </div>
    """
    send_transactional_email(subject_vendor, html_vendor, [vendor_email])
    return True


def send_order_dispatched_notification(delivery) -> bool:
    """
    Sends delivery dispatch tracking email to customer when order is out for delivery.
    """
    order = delivery.order
    customer_email = order.customer.email
    subject = f"Your Order #{order.order_number} is Out for Delivery! 🚚"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #2563EB;">Your Package is on the Way!</h2>
        <p>Dear {order.customer.first_name},</p>
        <p>Your order <strong>#{order.order_number}</strong> from <strong>{order.vendor.store_name}</strong> has been dispatched.</p>
        <p><strong>Tracking Number:</strong> {delivery.tracking_number}</p>
        <p><strong>Carrier:</strong> {delivery.carrier_name}</p>
        <p>Our dispatch partner is delivering your order to your selected address.</p>
        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 20px 0;" />
        <p style="color: #6B7280; font-size: 12px;">Aso Marketplace</p>
    </div>
    """
    return send_transactional_email(subject, html_content, [customer_email])


def send_order_completed_notification(order) -> bool:
    """
    Sends order completion email to customer inviting them to leave a verified review.
    """
    customer_email = order.customer.email
    subject = f"Order #{order.order_number} Completed — Leave a Review ⭐"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #059669;">Order Completed!</h2>
        <p>Dear {order.customer.first_name},</p>
        <p>Your order <strong>#{order.order_number}</strong> has been marked as complete.</p>
        <p>How did <strong>{order.vendor.store_name}</strong> do? Share your feedback and leave a verified buyer review on your dashboard!</p>
        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 20px 0;" />
        <p style="color: #6B7280; font-size: 12px;">Aso Marketplace</p>
    </div>
    """
    return send_transactional_email(subject, html_content, [customer_email])


def send_payout_initiated_notification(payout_request) -> bool:
    """
    Sends payout transfer notification to vendor.
    """
    vendor = payout_request.vendor
    vendor_email = vendor.user.email
    subject = f"Payout #{payout_request.reference} Initiated — ₦{payout_request.amount_naira:,.2f}"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #111827;">Payout Processing</h2>
        <p>Hello {vendor.store_name},</p>
        <p>Your withdrawal request of <strong>₦{payout_request.amount_naira:,.2f}</strong> (Reference: {payout_request.reference}) is now processing.</p>
        <p>Funds will be credited to your registered bank account shortly.</p>
        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 20px 0;" />
        <p style="color: #6B7280; font-size: 12px;">Aso Marketplace</p>
    </div>
    """
    return send_transactional_email(subject, html_content, [vendor_email])


def send_verification_submitted_notification(vendor) -> bool:
    """Alerts the Aso verification team that a designer submitted NIN/CAC for review."""
    review_email = getattr(settings, 'VERIFICATION_REVIEW_EMAIL', '')
    if not review_email:
        return False
    subject = f"[Action needed] Verify designer: {vendor.store_name}"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #111827;">New designer verification request</h2>
        <p><strong>{vendor.store_name}</strong> ({vendor.user.email}) submitted identity details for review.</p>
        <p>NIN provided: {'Yes' if vendor.nin_number else 'No'} &middot; CAC provided: {'Yes' if vendor.cac_number else 'No'}</p>
        <p>Review and approve or reject it in Django admin &rarr; Vendor profiles &rarr; filter by "Pending Admin Review".</p>
    </div>
    """
    return send_transactional_email(subject, html_content, [review_email])


def send_verification_decision_notification(vendor) -> bool:
    """Tells the designer whether Aso approved or rejected their verification."""
    approved = vendor.is_verified
    subject = "You're now a Verified Designer on Aso" if approved else "Action needed: your Aso verification"
    if approved:
        body = ("<p>Your identity has been verified. Your storefront now shows the <strong>Verified</strong> badge "
                "and withdrawals to your bank account are unlocked.</p>")
    else:
        reason = vendor.verification_rejection_reason or 'We could not confirm the details you submitted.'
        body = (f"<p>We couldn't verify your details: {reason}</p>"
                "<p>Please update your NIN or CAC in your Designer Studio profile and save to resubmit. "
                "You can keep selling in the meantime.</p>")
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <p>Hello {vendor.store_name},</p>
        {body}
        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 20px 0;" />
        <p style="color: #6B7280; font-size: 12px;">Aso Marketplace</p>
    </div>
    """
    return send_transactional_email(subject, html_content, [vendor.user.email])


def send_password_reset_email(user) -> bool:
    """Emails a one-time link (valid for PASSWORD_RESET_TIMEOUT) to choose a new password."""
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    base = getattr(settings, 'FRONTEND_URL', 'https://asomarketplace.com.ng').rstrip('/')
    link = f"{base}/reset-password?uid={uid}&token={token}"
    name = user.first_name or 'there'
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #111827;">Reset your Aso password</h2>
        <p>Hi {name},</p>
        <p>We received a request to reset the password for your Aso account. Choose a new one here:</p>
        <p style="margin: 24px 0;">
            <a href="{link}" style="background: #064E3B; color: #ffffff; padding: 12px 20px; text-decoration: none; border-radius: 6px; font-weight: bold;">Choose a new password</a>
        </p>
        <p>This link works for 2 hours and can be used once. If you didn't ask for this, you can ignore this email; your password won't change.</p>
        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 20px 0;" />
        <p style="color: #6B7280; font-size: 12px;">Aso Marketplace</p>
    </div>
    """
    return send_transactional_email("Reset your Aso password", html_content, [user.email])


def send_product_review_notification(product, approved: bool) -> bool:
    """Tells the designer their piece is live, or what to change before it can go live."""
    vendor = product.vendor
    base = getattr(settings, 'FRONTEND_URL', 'https://asomarketplace.com.ng').rstrip('/')
    if approved:
        subject = f"Your piece is live on Aso: {product.title}"
        body = (f"<p>Good news: <strong>{product.title}</strong> has been approved and shoppers can now buy it.</p>"
                f"<p><a href=\"{base}/products/{product.slug}\">See it on Aso</a></p>")
    else:
        subject = f"Changes needed: {product.title}"
        body = (f"<p>We reviewed <strong>{product.title}</strong> and it needs a change before it can go live:</p>"
                f"<p style=\"background:#FEF3C7;padding:12px;border-radius:6px;\">{product.rejection_reason}</p>"
                f"<p>Edit the piece in your <a href=\"{base}/vendor/products\">Designer Studio</a> and save it to send it back for review.</p>")
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <p>Hello {vendor.store_name},</p>
        {body}
        <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 20px 0;" />
        <p style="color: #6B7280; font-size: 12px;">Aso Marketplace</p>
    </div>
    """
    return send_transactional_email(subject, html_content, [vendor.user.email])


def send_manual_courier_request(order, pickup_address, pickup_phone, dest_address, dest_phone) -> bool:
    """The courier API couldn't book a rider: ask the Aso team to book one by hand."""
    ops_email = getattr(settings, 'OPS_EMAIL', '') or getattr(settings, 'VERIFICATION_REVIEW_EMAIL', '')
    if not ops_email:
        return False
    snap = order.shipping_address_snapshot or {}
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #B45309;">Book a rider by hand: order #{order.order_number}</h2>
        <p>{order.vendor.store_name} marked this order ready for pickup, but no courier was booked automatically
        (Dellyman API key missing or the booking failed). Please book a rider and tell the studio the pickup time.</p>
        <p><strong>Pickup:</strong> {order.vendor.store_name}, {pickup_address} (phone {pickup_phone or 'not set'})</p>
        <p><strong>Drop-off:</strong> {snap.get('full_name', '')}, {dest_address} (phone {dest_phone or 'not set'})</p>
        <p><strong>Delivery fee charged to the shopper:</strong> ₦{order.delivery_fee_naira:,.2f}</p>
    </div>
    """
    return send_transactional_email(f"[Action needed] Book a rider: #{order.order_number}", html_content, [ops_email])


def send_dispute_opened_notification(order, reason: str) -> bool:
    """A shopper reported a problem: alert the Aso team (payment is already on hold)."""
    ops_email = getattr(settings, 'OPS_EMAIL', '') or getattr(settings, 'VERIFICATION_REVIEW_EMAIL', '')
    if not ops_email:
        return False
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #B91C1C;">Problem reported: order #{order.order_number}</h2>
        <p><strong>Designer:</strong> {order.vendor.store_name}</p>
        <p><strong>What the shopper said:</strong></p>
        <p style="background:#FEF2F2;padding:12px;border-radius:6px;">{reason}</p>
        <p>The designer's payment is on hold. Resolve it in Django admin → Orders: "Resolve dispute" releases the
        payment to the designer; "Cancel" stops it (then refund the shopper in the Paystack dashboard).</p>
    </div>
    """
    return send_transactional_email(f"[Action needed] Problem reported: #{order.order_number}", html_content, [ops_email])
