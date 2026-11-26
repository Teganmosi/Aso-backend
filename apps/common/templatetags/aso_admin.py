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


def _fit_stat(now, link):
    from apps.products.models import FitFeedback
    qs = FitFeedback.objects.filter(created_at__gte=now - timedelta(days=90)).exclude(fit_result='')
    total = qs.count()
    great = qs.filter(fit_result='GREAT').count()
    return {'label': 'Fit well, last 90 days',
            'value': f'{round(100 * great / total)}% of {total}' if total else 'No answers yet',
            'url': link(FitFeedback, '')}


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
            # Pieces go live without approval; this is the quick after-the-fact look.
            'label': 'New pieces, last 24 hours',
            'hint': 'Already live. Glance at them; take down anything that breaks the rules.',
            'count': Product.objects.filter(created_at__gte=now - timedelta(hours=24)).count(),
            'url': link(Product, f"created_at__gte={(timezone.localtime(now) - timedelta(days=1)).date().isoformat()}"),
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
        _fit_stat(now, link),
        {'label': 'Picked for the home page',
         'value': f"{Product.objects.filter(is_featured=True).count()} pieces · "
                  f"{VendorProfile.objects.filter(is_featured=True).count()} studios",
         'url': link(Product, 'is_featured__exact=1')},
    ]
    return {'tasks': tasks, 'stats': stats, 'all_clear': not any(t['count'] for t in tasks)}


# Top navigation: the places staff go every day. (model, label, count of things waiting)
_NAV = [
    ('orders', 'order', 'Orders'),
    ('products', 'product', 'Pieces'),
    ('vendors', 'vendorprofile', 'Designers'),
    ('payouts', 'payoutrequest', 'Payouts'),
    ('deliveries', 'delivery', 'Deliveries'),
    ('accounts', 'user', 'Shoppers & accounts'),
]
# Which nav tab a page belongs to, by app label.
_SECTION = {'orders': 'orders', 'products': 'products', 'vendors': 'vendors', 'payouts': 'payouts',
            'deliveries': 'deliveries', 'accounts': 'accounts', 'cart': 'accounts', 'auth': 'accounts'}


def _waiting_counts():
    from apps.orders.models import Order, OrderStatus
    from apps.payouts.models import PayoutRequest, PayoutStatus
    from apps.vendors.models import VendorProfile, VerificationStatus
    return {
        'orders': Order.objects.filter(order_status__in=[
            OrderStatus.PAID, OrderStatus.READY_FOR_PICKUP, OrderStatus.DISPUTED]).count(),
        'vendors': VendorProfile.objects.filter(verification_status=VerificationStatus.PENDING_REVIEW).count(),
        'payouts': PayoutRequest.objects.filter(status=PayoutStatus.PAYOUT_RESERVED).count(),
    }


@register.inclusion_tag('admin/aso_nav.html', takes_context=True)
def aso_nav(context):
    request = context.get('request')
    user = getattr(request, 'user', None)
    if not (user and user.is_active and user.is_staff):
        return {'items': []}
    path = request.path
    admin_root = reverse('admin:index')
    current = None
    if path.startswith(admin_root):
        app = path[len(admin_root):].split('/', 1)[0]
        current = _SECTION.get(app)
    try:
        counts = _waiting_counts()
    except Exception:  # never let a count break navigation
        counts = {}
    items = [{'label': 'Home', 'url': admin_root, 'active': path == admin_root}]
    for app, model, label in _NAV:
        if not user.has_perm(f'{app}.view_{model}'):
            continue
        items.append({'label': label, 'url': reverse(f'admin:{app}_{model}_changelist'),
                      'active': current == app, 'count': counts.get(app, 0)})
    return {'items': items}
