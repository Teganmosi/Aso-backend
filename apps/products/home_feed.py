"""
What the home page shows: a small, fair selection instead of the whole catalogue.

"Curated for you" (HOME_PIECES pieces) and "Featured designers" (HOME_DESIGNERS studios):
  1. Hand-picks first: anything Aso ticked "Show on home page" in the admin. If more are
     ticked than there are slots, they take turns (the order changes each day).
  2. The rest is filled automatically from live pieces that have a photo:
       * at most PER_DESIGNER pieces from any one designer, so nobody floods the page,
       * a few slots kept for designers who joined in the last NEW_DAYS days,
       * the mix changes once a day, so returning shoppers see something new.

The selection depends only on the date, so every visitor sees the same page for the day,
and it can be cached. It reads a bounded pool (POOL_SIZE newest pieces), so its cost stays
flat however big the catalogue gets.
"""
from __future__ import annotations

import random
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Min, Q
from django.utils import timezone

from apps.products.selectors import _public_product_qs
from apps.vendors.models import VendorProfile, VendorStatus

HOME_PIECES = 12
HOME_DESIGNERS = 8
PER_DESIGNER = 2
NEW_DAYS = 30
NEW_PIECE_SLOTS = 3
NEW_DESIGNER_SLOTS = 2
POOL_SIZE = 400
CACHE_SECONDS = 600


def _today():
    return timezone.localdate()


def cache_key(day=None) -> str:
    return f'aso_home_feed_v1_{(day or _today()).isoformat()}'


def invalidate_home_feed() -> None:
    try:
        cache.delete(cache_key())
    except Exception:
        pass


def _daily_rng(salt: str) -> random.Random:
    return random.Random(f'{_today().isoformat()}:{salt}')


def select_home_pieces(limit: int = HOME_PIECES):
    rng = _daily_rng('pieces')
    with_photo = _public_product_qs().filter(media__isnull=False).distinct()

    picks = list(with_photo.filter(is_featured=True).order_by('-updated_at')[:200])
    rng.shuffle(picks)
    chosen = picks[:limit]
    if len(chosen) >= limit:
        return chosen

    taken = {p.id for p in chosen}
    pool = [p for p in with_photo.filter(is_featured=False).order_by('-created_at')[:POOL_SIZE]
            if p.id not in taken]
    rng.shuffle(pool)
    new_since = timezone.now() - timedelta(days=NEW_DAYS)
    newcomers = [p for p in pool if p.vendor.created_at >= new_since]

    per_designer: dict = {}

    def add(p) -> bool:
        if len(chosen) >= limit or p.id in taken or per_designer.get(p.vendor_id, 0) >= PER_DESIGNER:
            return False
        chosen.append(p)
        taken.add(p.id)
        per_designer[p.vendor_id] = per_designer.get(p.vendor_id, 0) + 1
        return True

    added_new = 0
    for p in newcomers:
        if added_new >= NEW_PIECE_SLOTS:
            break
        added_new += add(p)
    for p in pool:
        add(p)
    # Very few designers so far: relax the per-designer limit rather than show an empty row.
    if len(chosen) < limit:
        for p in pool:
            if len(chosen) >= limit:
                break
            if p.id not in taken:
                chosen.append(p)
                taken.add(p.id)

    hand = chosen[:len(picks[:limit])]
    auto = chosen[len(hand):]
    rng.shuffle(auto)  # newcomers mixed in, not stacked together
    return hand + auto


def public_designers_qs():
    """Approved studios with at least one live piece (same rule as the designers directory)."""
    live = Q(products__status='PUBLISHED', products__is_active=True, products__approval_status='APPROVED')
    return VendorProfile.objects.select_related('user').filter(status=VendorStatus.APPROVED).annotate(
        annotated_product_count=Count('products', filter=live, distinct=True),
        annotated_starting_price=Min('products__base_price_kobo', filter=live),
    ).filter(annotated_product_count__gt=0)


def select_home_designers(limit: int = HOME_DESIGNERS):
    rng = _daily_rng('designers')
    base = public_designers_qs()

    picks = list(base.filter(is_featured=True)[:100])
    rng.shuffle(picks)
    chosen = picks[:limit]
    if len(chosen) >= limit:
        return chosen

    taken = {v.id for v in chosen}
    pool = [v for v in base.filter(is_featured=False).order_by('-created_at')[:POOL_SIZE] if v.id not in taken]
    rng.shuffle(pool)
    new_since = timezone.now() - timedelta(days=NEW_DAYS)
    newcomers = [v for v in pool if v.created_at >= new_since][:NEW_DESIGNER_SLOTS]
    # Studios that set up a logo or banner look finished; they go before bare ones.
    rest = sorted((v for v in pool if v not in newcomers), key=lambda v: not (v.logo_url or v.banner_url))
    auto = (newcomers + rest)[:limit - len(chosen)]
    rng.shuffle(auto)
    return chosen + auto


def build_home_feed() -> dict:
    from apps.products.serializers import ProductListSerializer
    from apps.vendors.serializers import PublicVendorProfileSerializer

    key = cache_key()
    cached = cache.get(key)
    if cached is not None:
        return cached
    pieces = select_home_pieces()
    designers = select_home_designers()
    data = {
        'success': True,
        'pieces': ProductListSerializer(pieces, many=True).data,
        'designers': PublicVendorProfileSerializer(designers, many=True).data,
        'categories_with_pieces': categories_with_pieces(),
    }
    cache.set(key, data, timeout=CACHE_SECONDS)
    return data


def categories_with_pieces() -> list[str]:
    """Which home-page category pills have at least one live piece (pills with none are hidden)."""
    from apps.products.selectors import PILL_KEYWORDS, filter_by_pill
    base = _public_product_qs()
    return [slug for slug in PILL_KEYWORDS if filter_by_pill(base, slug).exists()]
