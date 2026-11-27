import html
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.utils.html import escape, strip_tags

logger = logging.getLogger(__name__)

# Brand colours (same as the logo and the site).
_INK = '#111827'
_GOLD = '#C59B27'
_GREEN = '#064E3B'
_FONT = "'Plus Jakarta Sans', 'Segoe UI', Helvetica, Arial, sans-serif"


def _site_url() -> str:
    return getattr(settings, 'FRONTEND_URL', 'https://asomarketplace.com.ng').rstrip('/')


def _banner_url() -> str:
    # The 1200x320 header banner (apps/common/static/aso_email/banner.png), served by the API's static files.
    # Must be a public PNG: mail apps can't load localhost and Gmail doesn't show SVG.
    return getattr(settings, 'EMAIL_BANNER_URL', 'https://api.asomarketplace.com.ng/static/aso_email/banner.png')


def _button(label: str, url: str) -> str:
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin: 28px 0 8px;"><tr>'
            f'<td bgcolor="{_GREEN}" style="border-radius: 8px;">'
            f'<a href="{url}" style="display: inline-block; padding: 14px 26px; font-family: {_FONT}; font-size: 15px; '
            f'font-weight: bold; color: #ffffff; text-decoration: none; border-radius: 8px;">{label}</a>'
            f'</td></tr></table>')


def _branded_email(heading: str, body_html: str, *, preheader: str = '', badge: str = '',
                   heading_color: str = _INK) -> str:
    """Wraps an email body in the Aso layout: logo header, white card, footer.
    Tables and inline styles only, so it also renders in Outlook and Gmail."""
    site = _site_url()
    badge_html = (f'<p style="margin: 0 0 16px;"><span style="display: inline-block; background: #FBF5E3; '
                  f'color: #8A6A12; border: 1px solid {_GOLD}; border-radius: 999px; padding: 6px 14px; '
                  f'font-size: 12px; font-weight: bold; letter-spacing: 1px; text-transform: uppercase;">'
                  f'{badge}</span></p>') if badge else ''
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin: 0; padding: 0; background: #F5F3EE;">
<div style="display: none; max-height: 0; overflow: hidden; opacity: 0; color: #F5F3EE;">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#F5F3EE">
<tr><td align="center" style="padding: 24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px;">
<tr><td align="center" bgcolor="{_INK}" style="background: {_INK}; padding: 0; border-radius: 12px 12px 0 0; font-size: 0; line-height: 0;">
<a href="{site}" style="text-decoration: none;"><img src="{_banner_url()}" width="600" alt="ASO MARKETPLACE" style="display: block; width: 100%; max-width: 600px; height: auto; border: 0; border-radius: 12px 12px 0 0; color: #ffffff; font-family: {_FONT}; font-size: 22px; line-height: 80px; font-weight: bold; letter-spacing: 4px; text-align: center;"></a>
</td></tr>
<tr><td height="4" bgcolor="{_GOLD}" style="background: {_GOLD}; font-size: 0; line-height: 0;">&nbsp;</td></tr>
<tr><td bgcolor="#ffffff" style="background: #ffffff; padding: 36px 32px 32px; border-radius: 0 0 12px 12px; font-family: {_FONT}; font-size: 16px; line-height: 1.6; color: #374151;">
{badge_html}<h1 style="margin: 0 0 20px; font-family: {_FONT}; font-size: 24px; line-height: 1.3; color: {heading_color};">{heading}</h1>
{body_html}
</td></tr>
<tr><td align="center" style="padding: 24px 16px; font-family: {_FONT}; font-size: 12px; line-height: 1.6; color: #6B7280;">
<strong style="color: {_INK}; letter-spacing: 2px;">ASO MARKETPLACE</strong><br>
Connecting Nigerian tailors with fashion lovers<br>
<a href="{site}" style="color: #8A6A12;">asomarketplace.com.ng</a> &nbsp;&middot;&nbsp; <a href="mailto:support@asomarketplace.com.ng" style="color: #8A6A12;">support@asomarketplace.com.ng</a>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def send_transactional_email(subject: str, html_message: str, recipient_list: list[str]) -> bool:
    """
    Safely sends a transactional HTML email without breaking database transactions or business logic.
    """
    if not recipient_list:
        return False

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Aso Marketplace <hello@asomarketplace.com.ng>')
    # Plain-text copy: drop the layout's indentation and blank lines.
    plain_text = html.unescape(strip_tags(html_message)).replace(chr(160), ' ')
    plain_lines = (line.strip() for line in plain_text.splitlines())
    plain_message = (chr(10) * 2).join(line for line in plain_lines if line and line != chr(183))

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
    html_content = _branded_email(f"Thank you for your order!", f"""
        <p>Dear {order.customer.first_name},</p>
        <p>Your order <strong>#{order.order_number}</strong> with <strong>{order.vendor.store_name}</strong> has been received.</p>
        <p><strong>Total Amount:</strong> ₦{order.total_amount_naira:,.2f}</p>
        <p>We are waiting for payment confirmation to proceed with tailoring and fulfillment.</p>
    """)
    return send_transactional_email(subject, html_content, [customer_email])


def send_payment_received_notification(order) -> bool:
    """
    Sends payment confirmation email to customer and notification to vendor.
    """
    customer_email = order.customer.email
    vendor_email = order.vendor.user.email
    
    # Customer Email
    subject_customer = f"Payment Confirmed: Order #{order.order_number} — Aso Marketplace"
    html_customer = _branded_email(f"Payment Confirmed!", f"""
        <p>Dear {order.customer.first_name},</p>
        <p>We have received your payment of <strong>₦{order.total_amount_naira:,.2f}</strong> for Order <strong>#{order.order_number}</strong>.</p>
        <p>The designer <strong>{order.vendor.store_name}</strong> has been notified and has 48 hours to accept and start preparing your garment.</p>
    """, heading_color="#059669")
    send_transactional_email(subject_customer, html_customer, [customer_email])

    # Vendor Email
    subject_vendor = f"New Paid Order #{order.order_number} Received! — Action Required"
    html_vendor = _branded_email(f"New Paid Order Received!", f"""
        <p>Hello {order.vendor.store_name},</p>
        <p>You have received a new paid order <strong>#{order.order_number}</strong>.</p>
        <p><strong>Subtotal:</strong> ₦{order.subtotal_naira:,.2f}</p>
        <p>Please log in to your vendor dashboard and accept the order within 48 hours to meet the fulfillment SLA.</p>
    """)
    send_transactional_email(subject_vendor, html_vendor, [vendor_email])
    return True


def send_order_dispatched_notification(delivery) -> bool:
    """
    Sends delivery dispatch tracking email to customer when order is out for delivery.
    """
    order = delivery.order
    customer_email = order.customer.email
    subject = f"Your Order #{order.order_number} is Out for Delivery! 🚚"
    html_content = _branded_email(f"Your Package is on the Way!", f"""
        <p>Dear {order.customer.first_name},</p>
        <p>Your order <strong>#{order.order_number}</strong> from <strong>{order.vendor.store_name}</strong> has been dispatched.</p>
        <p><strong>Tracking Number:</strong> {delivery.tracking_number}</p>
        <p><strong>Carrier:</strong> {delivery.carrier_name}</p>
        <p>Our dispatch partner is delivering your order to your selected address.</p>
    """, heading_color="#2563EB")
    return send_transactional_email(subject, html_content, [customer_email])


def send_order_completed_notification(order) -> bool:
    """
    Sends order completion email to customer inviting them to leave a verified review.
    """
    customer_email = order.customer.email
    subject = f"Order #{order.order_number} Completed — Leave a Review ⭐"
    html_content = _branded_email(f"Order Completed!", f"""
        <p>Dear {order.customer.first_name},</p>
        <p>Your order <strong>#{order.order_number}</strong> has been marked as complete.</p>
        <p>How did <strong>{order.vendor.store_name}</strong> do? Share your feedback and leave a verified buyer review on your dashboard!</p>
    """, heading_color="#059669")
    return send_transactional_email(subject, html_content, [customer_email])


def send_payout_initiated_notification(payout_request) -> bool:
    """
    Sends payout transfer notification to vendor.
    """
    vendor = payout_request.vendor
    vendor_email = vendor.user.email
    subject = f"Payout #{payout_request.reference} Initiated — ₦{payout_request.amount_naira:,.2f}"
    html_content = _branded_email(f"Payout Processing", f"""
        <p>Hello {vendor.store_name},</p>
        <p>Your withdrawal request of <strong>₦{payout_request.amount_naira:,.2f}</strong> (Reference: {payout_request.reference}) is now processing.</p>
        <p>Funds will be credited to your registered bank account shortly.</p>
    """)
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
    store = escape(vendor.store_name)
    studio = f"{_site_url()}/vendor/profile"
    if approved:
        subject = "You're now a Verified Designer on Aso"
        tick = (f'<td width="28" valign="top" style="padding: 6px 0; font-size: 16px; font-weight: bold; '
                f'color: {_GOLD};">&#10003;</td>')
        perks = ''.join(
            f'<tr>{tick}<td style="padding: 6px 0; font-size: 15px; line-height: 1.5; color: #374151;">{line}</td></tr>'
            for line in (
                'The <strong>Verified</strong> badge now shows on your storefront and your pieces.',
                'Withdrawals to your bank account are unlocked.',
                'Shoppers can see that Aso has confirmed who you are.',
            ))
        html_content = _branded_email(
            f"Congratulations, {store}!",
            f"""
        <p style="margin: 0 0 16px;">We've checked your details and confirmed your identity. You are now a
        <strong>Verified Designer</strong> on Aso.</p>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background: #FBF5E3; border-radius: 10px; margin: 20px 0 4px;">
        <tr><td style="padding: 14px 20px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0">{perks}</table>
        </td></tr></table>
        {_button('Open your Designer Studio', f'{_site_url()}/vendor/dashboard')}
        <p style="margin: 20px 0 0; font-size: 14px; color: #6B7280;">Thank you for building your studio with us.</p>
    """,
            preheader='Your Verified badge is live and withdrawals are unlocked.',
            badge='&#10003; Verified Designer')
    else:
        subject = "Action needed: your Aso verification"
        reason = escape(vendor.verification_rejection_reason or 'We could not confirm the details you submitted.')
        html_content = _branded_email(
            "We couldn't verify your details yet",
            f"""
        <p style="margin: 0 0 16px;">Hello {store},</p>
        <p style="margin: 0 0 8px;">We reviewed the NIN/CAC details you sent, but couldn't confirm them. Here's why:</p>
        <p style="margin: 0 0 16px; background: #FEF3C7; border-left: 4px solid #D97706; padding: 12px 16px; border-radius: 6px; color: #78350F;">{reason}</p>
        <p style="margin: 0;">Please update your NIN or CAC in your Designer Studio profile and save to resubmit.
        You can keep selling in the meantime.</p>
        {_button('Update your details', studio)}
    """,
            preheader='One thing to fix before we can give you the Verified badge.')
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
    html_content = _branded_email("Reset your Aso password", f"""
        <p>Hi {name},</p>
        <p>We received a request to reset the password for your Aso account. Choose a new one here:</p>
        {_button('Choose a new password', link)}
        <p>This link works for 2 hours and can be used once. If you didn't ask for this, you can ignore this email; your password won't change.</p>
    """)
    return send_transactional_email("Reset your Aso password", html_content, [user.email])


def send_email_verification_code(user, code: str, minutes: int = 15) -> bool:
    """The 6-digit sign-up code. The code is in the subject too, so it shows in phone notifications."""
    name = user.first_name or 'there'
    html_content = _branded_email("Confirm your email", f"""
        <p>Hi {name},</p>
        <p>Welcome to Aso. Enter this code to confirm your email address:</p>
        <p style="margin: 24px 0; font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #064E3B;">{code}</p>
        <p>It works for {minutes} minutes. If you didn't create an Aso account, you can ignore this email.</p>
    """)
    return send_transactional_email(f"{code} is your Aso code", html_content, [user.email])


def send_product_review_notification(product, approved: bool) -> bool:
    """Tells the designer a piece Aso took down is back live, or why it was taken down and how to fix it."""
    vendor = product.vendor
    base = getattr(settings, 'FRONTEND_URL', 'https://asomarketplace.com.ng').rstrip('/')
    if approved:
        subject = f"Your piece is live again: {product.title}"
        body = (f"<p><strong>{product.title}</strong> is back on Aso and shoppers can buy it.</p>"
                f"<p><a href=\"{base}/products/{product.slug}\">See it on Aso</a></p>")
    else:
        subject = f"We've paused a piece: {product.title}"
        body = (f"<p>We've taken <strong>{product.title}</strong> off Aso for now, because:</p>"
                f"<p style=\"background:#FEF3C7;padding:12px;border-radius:6px;\">{product.rejection_reason}</p>"
                f"<p>Fix it in your <a href=\"{base}/vendor/products\">Designer Studio</a> and save. "
                f"It goes live again straight away.</p>")
    heading = "Your piece is live again" if approved else "We've paused one of your pieces"
    html_content = _branded_email(heading, f"""
        <p>Hello {vendor.store_name},</p>
        {body}
    """)
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
