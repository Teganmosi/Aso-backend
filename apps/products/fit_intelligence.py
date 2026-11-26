"""
My Aso Fit: rough measurement estimate from a shopper's usual size, height, build and sex.

Be honest about what this is. Three or four answers cannot pin down a body: two people who
both wear "L" at the same height can differ by 4-5 inches at the waist, and size letters
differ between brands. So this produces a starting point with realistic ranges, and the
shopper is told to check with a tape measure. Orders placed with estimated numbers are
flagged to the designer, who confirms them with the shopper before cutting.

Tables are body measurements in inches, typical for ready-to-wear sizing sold in Nigeria
(men: chest-based sizing; women: roughly UK 6 = XS up to UK 22 = 3XL).
Lengths scale with height using standard body proportions.
"""
import re
from typing import Any, Dict, Optional

VERSION = '2.0'

from apps.products.sizing import MEN as MEN_TABLE, WOMEN as WOMEN_TABLE, detect_wearer  # noqa: E402

MEN = MEN_TABLE  # kept for callers that import from here

# Build adjusts circumferences (inches): slim / regular / full ("heavy or belly").
BUILD = {
    'slim':    {'chest_bust': -1.5, 'waist': -2.0, 'hips': -1.5, 'underbust': -1.0, 'thigh': -1.0, 'neck_collar': -0.5, 'sleeve_circumference': -0.75, 'shoulder': -0.25},
    'regular': {},
    'full':    {'chest_bust': 2.0, 'waist': 3.5, 'hips': 2.5, 'underbust': 2.0, 'thigh': 1.5, 'neck_collar': 0.75, 'sleeve_circumference': 1.0, 'shoulder': 0.25},
}
BUILD_ALIASES = {'athletic': 'regular', 'broad': 'regular', 'curvy': 'regular', 'heavy': 'full', 'lean': 'slim'}

# How far off a size-and-height estimate typically is (± inches). Shown to shoppers and designers.
SPREAD = {
    'chest_bust': 2.0, 'underbust': 2.0, 'waist': 3.0, 'hips': 2.5, 'shoulder': 1.0, 'neck_collar': 0.75,
    'thigh': 2.0, 'sleeve_circumference': 1.25, 'sleeve_length': 1.0, 'top_length': 2.0,
    'trouser_length': 1.5, 'inseam': 1.5, 'shoulder_to_underbust': 1.0, 'ankle_opening': 1.0,
}

LABEL = 'Rough guide. Please check with a tape measure if you can.'
DISCLAIMER = ('These numbers are a rough guide worked out from your size and height, not measurements. '
              'Bodies vary a lot within one size. Measure with a tape if you can; the designer will '
              'confirm your measurements with you before cutting.')


def _norm_size(size) -> str:
    s = str(size or 'M').strip().upper().replace(' ', '')
    s = {'SMALL': 'S', 'MEDIUM': 'M', 'LARGE': 'L', 'EXTRALARGE': 'XL', '2XL': 'XXL', 'XXXL': '3XL'}.get(s, s)
    return s if s in MEN else 'M'


def _norm_sex(sex) -> str:
    s = str(sex or '').strip().lower()
    if s in ('female', 'woman', 'women', 'f', 'w'):
        return 'female'
    if s in ('male', 'man', 'men', 'm'):
        return 'male'
    return ''


def _guess_sex(category: str) -> str:
    """Last resort when neither the shopper nor the piece says: gown/corset/boubou cuts are womenswear."""
    c = (category or '').lower()
    return detect_wearer(title=c) or ('female' if any(k in c for k in ('corset', 'gown', 'boubou', 'dress')) else 'male')


def parse_natural_language_profile(text: str) -> Dict[str, Any]:
    """Pull height, size, build and sex out of free text such as "5'10, usually L, big belly"."""
    if not text or not isinstance(text, str):
        return {}
    t = text.lower()
    out: Dict[str, Any] = {}
    ft_in = re.search(r"(\d)\s*(?:ft|'|feet)\s*(\d{1,2})?\s*(?:in|\"|inches)?", t)
    if ft_in:
        out['height_inches'] = int(ft_in.group(1)) * 12 + (int(ft_in.group(2)) if ft_in.group(2) else 0)
    else:
        cm = re.search(r"(\d{3})\s*cm", t)
        if cm:
            out['height_inches'] = round(int(cm.group(1)) / 2.54, 1)
    size = re.search(r"\b(xs|3xl|2xl|xxl|xl|small|medium|large|extra large|[sml])\b", t)
    if size:
        out['rtw_size'] = _norm_size(size.group(1))
    if any(k in t for k in ('slim', 'skinny', 'lean', 'thin')):
        out['build'] = 'slim'
    elif any(k in t for k in ('belly', 'plus size', 'heavy', 'chubby', 'big stomach', 'full figure')):
        out['build'] = 'full'
    if re.search(r"\b(woman|female|lady|she)\b", t):
        out['sex'] = 'female'
    elif re.search(r"\b(man|male|guy|he)\b", t):
        out['sex'] = 'male'
    return out


def calculate_fit_estimate(
    category: str = 'tops_senator',
    rtw_size: str = 'M',
    height_inches: float = 70.0,
    build: str = 'regular',
    usual_size_fit: str = 'fitted',
    garment_fit: str = 'regular',
    style: str = 'standard',
    known_measurements: Optional[Dict[str, Any]] = None,
    text_description: Optional[str] = None,
    customer=None,
    sex: str = '',
) -> Dict[str, Any]:
    known_measurements = known_measurements or {}
    if text_description:
        parsed = parse_natural_language_profile(text_description)
        height_inches = parsed.get('height_inches', height_inches)
        rtw_size = parsed.get('rtw_size', rtw_size)
        build = parsed.get('build', build)
        sex = sex or parsed.get('sex', '')

    size = _norm_size(rtw_size)
    sex = _norm_sex(sex) or _guess_sex(category)
    try:
        h = float(height_inches or (70.0 if sex == 'male' else 64.0))
    except (TypeError, ValueError):
        h = 70.0 if sex == 'male' else 64.0
    h = max(54.0, min(84.0, h))  # 4'6" to 7'0"
    build = BUILD_ALIASES.get(str(build).lower(), str(build).lower())
    if build not in BUILD:
        build = 'regular'

    if sex == 'male':
        t = MEN_TABLE[size]
        chest, waist, hips, shoulder, neck, thigh, bicep = (t['chest_bust'], t['waist'], t['hips'], t['shoulder'],
                                                            t['neck_collar'], t['thigh'], t['sleeve_circumference'])
        underbust = None
        # Men run ~1.5" more chest-to-underbust; not used for menswear cuts.
        sleeve = 0.357 * h            # shoulder point to wrist
        trouser = 0.59 * h            # waist to ankle (outseam)
        inseam = 0.45 * h
        top = 0.53 * h                # high shoulder to just above the knee (senator / kaftan top)
        if style == 'modern_short':
            top = 0.47 * h
        elif style == 'long':
            top = 0.60 * h
        shoulder_to_underbust = None
    else:
        t = WOMEN_TABLE[size]
        chest, underbust, waist, hips, shoulder, thigh, bicep = (t['chest_bust'], t['underbust'], t['waist'], t['hips'],
                                                                 t['shoulder'], t['thigh'], t['sleeve_circumference'])
        neck = None
        sleeve = 0.35 * h
        trouser = 0.60 * h
        inseam = 0.455 * h
        top = 0.82 * h + 2.0          # shoulder to floor in low heels: gowns, boubou, dresses
        shoulder_to_underbust = 0.21 * h

    raw = {
        'chest_bust': chest, 'waist': waist, 'hips': hips, 'shoulder': shoulder, 'thigh': thigh,
        'sleeve_circumference': bicep, 'sleeve_length': sleeve, 'top_length': top,
        'trouser_length': trouser, 'inseam': inseam, 'ankle_opening': 14.0 if sex == 'male' else 13.0,
    }
    if neck is not None:
        raw['neck_collar'] = neck
    if underbust is not None:
        raw['underbust'] = underbust
        raw['shoulder_to_underbust'] = shoulder_to_underbust
    for key, delta in BUILD[build].items():
        if key in raw:
            raw[key] += delta
    raw = {k: round(v * 2) / 2 for k, v in raw.items()}  # nearest half inch: no false precision

    measurements: Dict[str, float] = {}
    sources: Dict[str, str] = {}
    for key, val in raw.items():
        given = known_measurements.get(key)
        try:
            given = float(given) if given not in (None, '') else None
        except (TypeError, ValueError):
            given = None
        if given:
            measurements[key], sources[key] = given, 'user'
        else:
            measurements[key], sources[key] = val, 'estimate'

    ranges = {}
    for key, val in measurements.items():
        d = 0.0 if sources[key] == 'user' else SPREAD.get(key, 1.5)
        lo, hi = round(val - d, 1), round(val + d, 1)
        ranges[key] = {'min': lo, 'max': hi, 'target': val, 'bracket': f'{lo} - {hi}', 'unit': 'IN'}

    confidences = {k: (1.0 if sources[k] == 'user' else 0.5) for k in measurements}
    estimated = [k for k in measurements if sources[k] == 'estimate']
    return {
        'version': VERSION,
        'estimated_ranges': ranges,
        'confidence_tier': 'low' if estimated else 'high',
        'confidence_label': LABEL if estimated else 'Your own measurements',
        'confidence_score': round(sum(confidences.values()) / max(1, len(confidences)), 2),
        'input_profile': {
            'sex': sex, 'rtw_size': size, 'height_inches': h, 'build': build,
            'usual_size_fit': usual_size_fit, 'garment_fit': garment_fit, 'style': style, 'category': category,
        },
        'body_measurements': {k: measurements[k] for k in ('chest_bust', 'waist', 'hips', 'shoulder') if k in measurements},
        'garment_measurements': {k: measurements[k] for k in ('top_length', 'trouser_length', 'sleeve_length') if k in measurements},
        'measurements': measurements,
        'confidences': confidences,
        'sources': sources,
        'estimated_fields': estimated,
        'disclaimer': DISCLAIMER,
    }
