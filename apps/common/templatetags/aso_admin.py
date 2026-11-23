"""
The "Needs your attention" panel on the admin home page: what staff must act on today,
each linking straight to the filtered list.
"""
from datetime import timedelta

from django import template
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from apps.common.admin_display import naira

register = template.Library()


@register.inclusion_tag('admin/aso_dashboard.html', takes_context=True)
def aso_dashboard(context):
    from apps.orders.models import Order, OrderStatus
    from apps.payouts.models import PayoutRequest, PayoutStatus
    from apps.products.models import ApprovalStatus, Product
    from apps.vendors.models import VendorProfile, VerificationStatus

    now = timezone.now()

    def link(model, query):
        return f"{reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_changelist')}?{query}"

    paid = Order.objects.filter(order_status=OrderStatus.PAID)
    late = paid.filter(vendor_accept_due_by__lt=now + timedelta(hours=12)).count()
    payouts = PayoutRequest.objects.filter(status=PayoutStatus.PAYOUT_RESERVED)
    payout_total = payouts.aggregate(s=Sum('amount_kobo'))['s'] or 0

    tasks = [
        {
            'label': 'Pieces waiting for review',
            'hint': 'Designers expect an answer within a day.',
            'count': Product.objects.filter(approval_status=ApprovalStatus.PENDING).count(),
            'url': link(Product, 'approval_status__exact=PENDING'),
        },
        {
            'label': 'New orders not accepted',
            'hint': f'{late} due within 12 hours. Nudge the designer on WhatsApp.' if late else 'Designers have 48 hours to accept.',
            'count': paid.count(),
            'url': link(Order, 'order_status__exact=PAID'),
            'urgent': late > 0,
        },
        {
            'label': 'Ready, waiting for a rider',
            'hint': 'Book the rider, then mark it in transit.',
            'count': Order.objects.filter(order_status=OrderStatus.READY_FOR_PICKUP).count(),
            'url': link(Order, 'order_status__exact=READY_FOR_PICKUP'),
        },
        {
            'label': 'Problems reported',
            'hint': 'Call the shopper and the designer.',
            'count': Order.objects.filter(order_status=OrderStatus.DISPUTED).count(),
            'url': link(Order, 'order_status__exact=DISPUTED'),
            'urgent': True,
        },
        {
            'label': 'Payouts to approve',
            'hint': f'{naira(payout_total)} in total. Check the bank details first.' if payout_total else 'Check the bank details first.',
            'count': payouts.count(),
            'url': link(PayoutRequest, 'status__exact=PAYOUT_RESERVED'),
        },
        {
            'label': 'Identity checks (NIN/CAC)',
            'hint': 'Approve or reject with a reason.',
            'count': VendorProfile.objects.filter(verification_status=VerificationStatus.PENDING_REVIEW).count(),
            'url': link(VendorProfile, 'verification_status__exact=PENDING_REVIEW'),
        },
    ]
    for t in tasks:
        t['urgent'] = bool(t.get('urgent') and t['count'])

    week = Order.objects.filter(created_at__gte=now - timedelta(days=7)).exclude(
        order_status__in=[OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED, OrderStatus.REFUNDED])
    stats = [
        {'label': 'Paid orders, last 7 days', 'value': week.count()},
        {'label': 'Sales, last 7 days', 'value': naira(week.aggregate(s=Sum('total_amount_kobo'))['s'] or 0)},
        {'label': 'Live pieces', 'value': Product.objects.filter(approval_status=ApprovalStatus.APPROVED, is_active=True).count()},
        {'label': 'Designers', 'value': VendorProfile.objects.count()},
    ]
    return {'tasks': tasks, 'stats': stats, 'all_clear': not any(t['count'] for t in tasks)}
