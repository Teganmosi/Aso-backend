"""
Small display helpers for the Django admin: naira amounts, coloured status badges and
thumbnails. Amounts are stored in kobo; staff were reading "10000000" and approving payouts.
"""
from django.utils.html import format_html

# Badge colour per status value (shared across models). Anything unknown is grey.
_TONES = {
    'good': {'APPROVED', 'PUBLISHED', 'VERIFIED', 'SUCCESSFUL', 'COMPLETED', 'DELIVERED', 'PAID_OUT', 'AVAILABLE'},
    'action': {'PENDING', 'PENDING_REVIEW', 'PAYOUT_RESERVED', 'PAID', 'READY_FOR_PICKUP'},
    'progress': {'VENDOR_ACCEPTED', 'PREPARING', 'PICKED_UP', 'OUT_FOR_DELIVERY', 'PROCESSING', 'IN_TRANSIT'},
    'bad': {'REJECTED', 'FAILED', 'CANCELLED', 'REFUNDED', 'DISPUTED', 'SUSPENDED'},
}


def naira(kobo) -> str:
    if kobo is None:
        return '—'
    return f'₦{kobo / 100:,.0f}' if kobo % 100 == 0 else f'₦{kobo / 100:,.2f}'


def badge(value, label=None):
    value = str(value or '')
    tone = next((t for t, values in _TONES.items() if value in values), 'neutral')
    return format_html('<span class="aso-badge aso-badge--{}">{}</span>', tone, label or value.replace('_', ' ').title())


def thumb(url, size=56):
    if not url:
        return format_html('<span class="aso-thumb aso-thumb--empty" style="width:{0}px;height:{0}px">—</span>', size)
    return format_html('<img class="aso-thumb" src="{}" width="{}" height="{}" alt="" loading="lazy">', url, size, size)
