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

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Aso Marketplace <notifications@aso.ng>')
    plain_message = strip_tags(html_message)

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=True
        )
        logger.info(f"Transactional email '{subject}' sent to {recipient_list}")
        return True
    except Exception as e:
        logger.error(f"Failed to send transactional email '{subject}' to {recipient_list}: {str(e)}")
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
