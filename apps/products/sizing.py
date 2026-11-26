"""
One source of truth for sizes on Aso: who a piece is for, what kind of cut it is, and the
typical body measurements behind each size label. Used by the size guide, the rough
measurement estimate and the "fill in typical numbers" button designers see.

Body measurements are in inches. Women's sizes follow UK/Nigerian sizing (XS = UK 6 up to
3XL = UK 22); men's follow chest sizing. These are typical bodies for each size, not any one
designer's pattern: a designer's own chart always takes priority.
"""
from __future__ import annotations

import re

# Size -> typical body measurements (inches)
WOMEN = {
    'XS':  {'chest_bust': 32.0, 'underbust': 27.0, 'waist': 25.0, 'hips': 35.0, 'shoulder': 14.25, 'thigh': 20.5, 'sleeve_circumference': 10.0},
    'S':   {'chest_bust': 34.5, 'underbust': 29.0, 'waist': 27.5, 'hips': 37.5, 'shoulder': 14.75, 'thigh': 22.0, 'sleeve_circumference': 10.75},
    'M':   {'chest_bust': 37.0, 'underbust': 31.5, 'waist': 30.0, 'hips': 40.5, 'shoulder': 15.25, 'thigh': 23.5, 'sleeve_circumference': 11.5},
    'L':   {'chest_bust': 40.0, 'underbust': 34.0, 'waist': 33.0, 'hips': 43.5, 'shoulder': 15.75, 'thigh': 25.0, 'sleeve_circumference': 12.5},
    'XL':  {'chest_bust': 43.0, 'underbust': 37.0, 'waist': 36.5, 'hips': 47.0, 'shoulder': 16.25, 'thigh': 27.0, 'sleeve_circumference': 13.75},
    'XXL': {'chest_bust': 46.0, 'underbust': 40.0, 'waist': 40.0, 'hips': 50.0, 'shoulder': 16.75, 'thigh': 28.5, 'sleeve_circumference': 15.0},
    '3XL': {'chest_bust': 49.0, 'underbust': 43.0, 'waist': 43.5, 'hips': 53.0, 'shoulder': 17.25, 'thigh': 30.0, 'sleeve_circumference': 16.25},
}
MEN = {
    'XS':  {'chest_bust': 34.0, 'waist': 28.0, 'hips': 34.0, 'shoulder': 16.5, 'neck_collar': 14.0, 'thigh': 20.0, 'sleeve_circumference': 11.5},
    'S':   {'chest_bust': 37.0, 'waist': 30.5, 'hips': 37.0, 'shoulder': 17.0, 'neck_collar': 14.75, 'thigh': 21.5, 'sleeve_circumference': 12.25},
    'M':   {'chest_bust': 40.0, 'waist': 33.0, 'hips': 40.0, 'shoulder': 18.0, 'neck_collar': 15.5, 'thigh': 23.0, 'sleeve_circumference': 13.0},
    'L':   {'chest_bust': 43.0, 'waist': 36.0, 'hips': 43.0, 'shoulder': 19.0, 'neck_collar': 16.25, 'thigh': 24.5, 'sleeve_circumference': 14.0},
    'XL':  {'chest_bust': 46.0, 'waist': 39.5, 'hips': 46.0, 'shoulder': 20.0, 'neck_collar': 17.0, 'thigh': 26.0, 'sleeve_circumference': 15.0},
    'XXL': {'chest_bust': 49.0, 'waist': 43.0, 'hips': 49.0, 'shoulder': 21.0, 'neck_collar': 18.0, 'thigh': 27.5, 'sleeve_circumference': 16.0},
    '3XL': {'chest_bust': 52.0, 'waist': 46.5, 'hips': 52.0, 'shoulder': 22.0, 'neck_collar': 19.0, 'thigh': 29.0, 'sleeve_circumference': 17.0},
}
LETTERS = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL']
WOMEN_UK = {'XS': '6', 'S': '8–10', 'M': '12', 'L': '14–16', 'XL': '18', 'XXL': '20', '3XL': '22'}
# UK dress size -> letter (women)
UK_TO_LETTER = {6: 'XS', 8: 'S', 10: 'S', 12: 'M', 14: 'L', 16: 'L', 18: 'XL', 20: 'XXL', 22: '3XL', 24: '3XL'}

# Words that say who a piece is for. Checked against title, then category names.
_FEMALE = re.compile(r"\b(women'?s?|woman|ladies|lady|female|her|bride|bridal gown|gown|dress|iro|buba|boubou|bubu|"
                     r"corset|skirt|blouse|aso[- ]?ebi|abaya|kimono|jumpsuit|maxi|wrapper|gele|bodice|bustier)\b")
_MALE = re.compile(r"\b(men'?s?|man|male|gents?|his|groom|agbada|senator|dashiki|jalabiya|buba and sokoto|sokoto|"
                   r"fila|tunic|kaftan suit)\b")


def detect_wearer(title: str = '', category_name: str = '', category_slug: str = '', parent_name: str = '') -> str | None:
    """'female', 'male' or None (can't tell: ask the shopper). Department wins, then title words."""
    for dept in (parent_name, category_name, category_slug):
        d = (dept or '').strip().lower()
        if d in ('women', 'womens', "women's", 'ladies'):
            return 'female'
        if d in ('men', 'mens', "men's"):
            return 'male'
    t = (title or '').lower()
    # "Women's agbada" is a woman's piece: explicit words beat garment words.
    if re.search(r"\b(women'?s?|ladies|female|her)\b", t):
        return 'female'
    if re.search(r"\b(men'?s?|gents?|male|his|groom)\b", t):
        return 'male'
    f, m = bool(_FEMALE.search(t)), bool(_MALE.search(t))
    if f != m:
        return 'female' if f else 'male'
    c = f'{category_name} {category_slug}'.lower()
    f, m = bool(_FEMALE.search(c)), bool(_MALE.search(c))
    if f != m:
        return 'female' if f else 'male'
    return None


def wearer_for_product(product) -> str | None:
    cat = getattr(product, 'category', None)
    parent = getattr(cat, 'parent', None) if cat else None
    return detect_wearer(product.title or '', getattr(cat, 'name', '') or '', getattr(cat, 'slug', '') or '',
                         getattr(parent, 'name', '') or '')


def cut_for_text(text: str, category: str = '') -> str:
    """
    corset_gown | boubou | trousers | tops_senator | full_set (same names the website uses).
    The piece's own name wins; the category ("Agbada & Grand Native Sets") only decides when the
    name says nothing, so an "Adire Gown" filed there is still a gown.
    """
    return _cut(text) or _cut(category) or 'full_set'


def _cut(text: str) -> str | None:
    t = (text or '').lower()
    if re.search(r'agbada|kaftan|caftan|dashiki|jalabiya|senator|tunic|shirt', t):
        return 'tops_senator'
    if re.search(r'\bsuit\b|blazer|two-piece|2-piece|co-ord|tuxedo|pantsuit', t):
        return 'full_set'
    if re.search(r'boubou|bubu|abaya|rich auntie', t):
        return 'boubou'
    if re.search(r'trouser|\bpants?\b|palazzo|shorts|jogger', t):
        return 'trousers'
    if re.search(r'corset|boned|gown|dress|skirt|aso ebi|\biro\b|buba', t):
        return 'corset_gown'
    return None


# Which body measurements matter for choosing a size, per cut (in table order).
CUT_COLUMNS = {
    'corset_gown': ['chest_bust', 'underbust', 'waist', 'hips'],
    'boubou': ['chest_bust', 'hips'],
    'trousers': ['waist', 'hips'],
    'tops_senator': ['chest_bust', 'waist', 'neck_collar'],
    'full_set': ['chest_bust', 'waist', 'hips'],
}
COLUMN_LABELS = {'chest_bust': 'Bust / chest', 'underbust': 'Underbust', 'waist': 'Waist', 'hips': 'Hips',
                 'neck_collar': 'Neck'}


def letter_for(size: str, wearer: str | None) -> str | None:
    """Map a size label a designer used ('M', 'Medium', 'UK 12', '12', '2XL') to a table row."""
    s = str(size or '').strip().upper().replace(' ', '')
    s = {'SMALL': 'S', 'MEDIUM': 'M', 'LARGE': 'L', 'EXTRALARGE': 'XL', 'XXXL': '3XL', '2XL': 'XXL',
         'XXS': 'XS'}.get(s, s)
    if s in LETTERS:
        return s
    m = re.fullmatch(r'(?:UK)?(\d{1,2})', s)
    if m:
        n = int(m.group(1))
        if wearer != 'male' and n in UK_TO_LETTER:
            return UK_TO_LETTER[n]
        if wearer == 'male' and 32 <= n <= 56:  # men's chest sizes ("40")
            return min(MEN, key=lambda k: abs(MEN[k]['chest_bust'] - n))
    return None


def _fmt(v: float) -> str:
    return f'{v:g}'


def typical_rows(sizes, wearer: str | None, cut: str) -> list[dict]:
    """Size-guide rows (ranges as text, inches and cm) for the sizes a piece is sold in."""
    table = MEN if wearer == 'male' else WOMEN
    cols = [c for c in CUT_COLUMNS.get(cut, CUT_COLUMNS['full_set']) if c in table['M']]
    rows = []
    mapped = [(size, letter_for(size, wearer)) for size in sizes]
    # Smallest to largest, whatever order the sizes were stored in.
    mapped = sorted((m for m in mapped if m[1]), key=lambda m: LETTERS.index(m[1]))
    for size, letter in mapped:
        i = LETTERS.index(letter)
        row = {'size': str(size)}
        if wearer != 'male':
            row['uk_size'] = WOMEN_UK[letter]
        for col in cols:
            v = table[letter][col]
            # Half-way to the neighbouring sizes, so the ranges meet without gaps.
            lo = (v + table[LETTERS[i - 1]][col]) / 2 if i > 0 else v - (table['S'][col] - table['XS'][col]) / 2
            hi = (v + table[LETTERS[i + 1]][col]) / 2 if i < len(LETTERS) - 1 else v + (table['3XL'][col] - table['XXL'][col]) / 2
            lo, hi = round(lo * 2) / 2, round(hi * 2) / 2
            key = {'chest_bust': 'bust', 'hips': 'hip'}.get(col, col)
            row[key] = f'{_fmt(lo)}-{_fmt(hi)}'
            row[f'{key}_cm'] = f'{round(lo * 2.54)}-{round(hi * 2.54)}'
        rows.append(row)
    return rows


def generic_size_chart(product, sizes=None) -> dict:
    wearer = wearer_for_product(product)
    cut = cut_for_text(product.title, getattr(product.category, 'name', ''))
    if sizes is None:
        sizes = [v.size for v in product.variants.all() if v.is_active]
    rows = typical_rows(sizes, wearer, cut)
    stretch = (product.size_chart or {}).get('stretch') if isinstance(product.size_chart, dict) else None
    return {
        'is_generic': True,
        'wearer': wearer,
        'cut': cut,
        'columns': [COLUMN_LABELS[c] for c in CUT_COLUMNS.get(cut, [])],
        'stretch': stretch or None,
        'unit_default': 'IN',
        'body_measurements': rows,
        'garment_measurements': {},
    }


# ---- Designer-entered size charts ---------------------------------------------------------

# Chart column -> limits key in apps.common.measurements.FIELDS
_CHART_COLUMNS = {'bust': 'chest_bust', 'underbust': 'underbust', 'waist': 'waist', 'hip': 'hips',
                  'neck_collar': 'neck_collar'}
_CHART_SETTINGS = {'stretch': ('NON', 'SLIGHT', 'MEDIUM', 'HIGH'), 'unit_default': ('IN', 'CM')}
_CHART_FREE_TEXT = {'garment_type': 30, 'sizing_system': 20}


def _parse_range(text) -> tuple[float, float] | None:
    m = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(?:[-–to]+\s*(\d+(?:\.\d+)?))?\s*', str(text))
    if not m:
        return None
    lo = float(m.group(1))
    hi = float(m.group(2)) if m.group(2) else lo
    return lo, hi


def clean_designer_chart(data) -> dict:
    """
    Check a size chart a designer typed in. Numbers are inches, one number or a range ("36-38").
    Returns the chart with cm columns filled in; raises ValueError with a message for the designer.
    """
    from apps.common.measurements import FIELDS

    if data in (None, ''):
        return {}
    if not isinstance(data, dict):
        raise ValueError('The size chart must be a table.')
    clean: dict = {}
    for key, allowed in _CHART_SETTINGS.items():
        if data.get(key) in allowed:
            clean[key] = data[key]
    for key, n in _CHART_FREE_TEXT.items():
        if data.get(key):
            clean[key] = str(data[key])[:n]
    if 'allows_custom_tailoring' in data:
        clean['allows_custom_tailoring'] = bool(data['allows_custom_tailoring'])

    rows = data.get('body_measurements') or []
    if not isinstance(rows, list) or len(rows) > 20:
        raise ValueError('The size chart can have up to 20 sizes.')
    out_rows, lengths = [], []
    for row in rows:
        if not isinstance(row, dict) or not str(row.get('size', '')).strip():
            continue
        size = str(row['size']).strip()[:20]
        out = {'size': size}
        for col, field in _CHART_COLUMNS.items():
            raw = row.get(col)
            if raw in (None, ''):
                continue
            rng = _parse_range(raw)
            label, lo_lim, hi_lim = FIELDS[field]
            if not rng:
                raise ValueError(f'Size {size}, {label.lower()}: enter a number or a range like 36-38 (inches).')
            lo, hi = rng
            if lo > hi:
                raise ValueError(f'Size {size}, {label.lower()}: the first number should be the smaller one.')
            if lo < lo_lim or hi > hi_lim:
                raise ValueError(f'Size {size}, {label.lower()}: {raw} doesn\'t look right in inches '
                                 f'(expected {lo_lim}-{hi_lim}). If you measured in cm, divide by 2.54.')
            out[col] = f'{lo:g}' if lo == hi else f'{lo:g}-{hi:g}'
            out[f'{col}_cm'] = f'{round(lo * 2.54)}' if lo == hi else f'{round(lo * 2.54)}-{round(hi * 2.54)}'
        length = row.get('length')
        if length not in (None, ''):
            rng = _parse_range(length)
            if not rng or not 10 <= rng[0] <= rng[1] <= 75:
                raise ValueError(f'Size {size}, garment length: enter inches, e.g. 56 (expected 10-75).')
            lengths.append({'size': size, 'length': f'{rng[0]:g}' if rng[0] == rng[1] else f'{rng[0]:g}-{rng[1]:g}',
                            'length_cm': f'{round(rng[0] * 2.54)}' if rng[0] == rng[1]
                            else f'{round(rng[0] * 2.54)}-{round(rng[1] * 2.54)}'})
        if len(out) > 1:
            out_rows.append(out)
    if out_rows:
        clean['body_measurements'] = out_rows
    if lengths:
        clean['garment_measurements'] = {'tops': lengths}
    return clean
