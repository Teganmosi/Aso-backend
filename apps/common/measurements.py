"""
Checks for shopper measurements before they reach a designer's cut sheet.

Measurements arrive as a small JSON object from the website: numbers keyed by body part,
plus a few labels (unit, notes, where the numbers came from). We reject anything that
can't be a real body: typos such as a 400-inch waist, centimetres typed as inches, and
oversized or junk payloads. The messages are written for shoppers.
"""
from rest_framework.exceptions import ValidationError

# Body part -> (label, smallest, largest) in inches. Generous: real bodies are outside "typical".
FIELDS = {
    'chest_bust': ('Bust / chest', 24, 75),
    'underbust': ('Underbust', 20, 65),
    'waist': ('Waist', 18, 75),
    'hips': ('Hips', 24, 80),
    'shoulder': ('Shoulder width', 10, 30),
    'neck_collar': ('Neck', 10, 28),
    'sleeve_length': ('Sleeve length', 6, 40),
    'sleeve_circumference': ('Arm (bicep)', 6, 30),
    'top_length': ('Length', 10, 75),
    'trouser_length': ('Trouser length', 15, 55),
    'inseam': ('Inseam', 15, 45),
    'thigh': ('Thigh', 12, 45),
    'ankle_opening': ('Ankle opening', 6, 30),
    'shoulder_to_underbust': ('Shoulder to underbust', 6, 25),
}
TEXT_KEYS = {'notes': 1000, 'category_type': 40, 'fit_source': 40, 'height_snapshot': 20, 'size_snapshot': 10,
             'sex': 10, 'measured_on': 20}
LIST_KEYS = {'estimated_fields'}
MAX_KEYS = 40


def _num(value):
    try:
        n = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return n if n == n and n not in (float('inf'), float('-inf')) else None


def check_value(key: str, value, unit: str = 'IN') -> float:
    """One measurement. Returns the number; raises ValidationError with a shopper-friendly message."""
    label, lo, hi = FIELDS[key]
    n = _num(value)
    if n is None or n <= 0:
        raise ValidationError({'measurements': f'{label}: please enter a number.'})
    inches = n / 2.54 if unit == 'CM' else n
    if inches > hi and unit == 'IN' and lo <= inches / 2.54 <= hi:
        raise ValidationError({'measurements': f'{label}: {n:g} looks like centimetres. Switch the unit to cm, '
                                               'or enter it in inches.'})
    if not lo <= inches <= hi:
        u = 'cm' if unit == 'CM' else 'in'
        show_lo, show_hi = (round(lo * 2.54), round(hi * 2.54)) if unit == 'CM' else (lo, hi)
        raise ValidationError({'measurements': f'{label}: {n:g} {u} can\'t be right. Please measure again '
                                               f'(expected between {show_lo} and {show_hi} {u}).'})
    return n


def clean_measurements(data, *, allow_empty: bool = True) -> dict:
    """Validate a whole measurements object. Unknown keys are dropped; numbers are range-checked."""
    if data in (None, ''):
        data = {}
    if not isinstance(data, dict):
        raise ValidationError({'measurements': 'Measurements must be a list of body parts and numbers.'})
    if len(data) > MAX_KEYS:
        raise ValidationError({'measurements': 'Too many measurement fields.'})
    unit = str(data.get('unit') or 'IN').upper()
    if unit not in ('IN', 'CM'):
        raise ValidationError({'measurements': 'Unit must be inches or centimetres.'})

    clean: dict = {'unit': unit} if data else {}
    for key, value in data.items():
        if key in FIELDS:
            if value in (None, ''):
                continue
            clean[key] = f'{check_value(key, value, unit):g}'
        elif key in TEXT_KEYS:
            if value not in (None, ''):
                clean[key] = str(value)[:TEXT_KEYS[key]]
        elif key in LIST_KEYS:
            if isinstance(value, list):
                clean[key] = [str(v)[:40] for v in value if str(v) in FIELDS][:len(FIELDS)]
        elif key == 'estimated_ranges':
            if isinstance(value, dict):
                ranges = {}
                for k, r in value.items():
                    if k in FIELDS and isinstance(r, dict):
                        ranges[k] = {f: r[f] for f in ('min', 'max', 'target', 'bracket', 'unit')
                                     if f in r and isinstance(r[f], (int, float, str)) and len(str(r[f])) <= 20}
                if ranges:
                    clean[key] = ranges
        # anything else (old or unknown keys) is dropped

    # Cross-checks that catch swapped fields.
    def val(k):
        return _num(clean.get(k))
    if val('underbust') and val('chest_bust') and val('underbust') > val('chest_bust'):
        raise ValidationError({'measurements': 'Underbust can\'t be bigger than your full bust. Please check both.'})
    if val('inseam') and val('trouser_length') and val('inseam') >= val('trouser_length'):
        raise ValidationError({'measurements': 'Inseam must be shorter than the full trouser length. Please check both.'})

    if not allow_empty and not any(k in FIELDS for k in clean):
        raise ValidationError({'measurements': 'Please enter at least one measurement.'})
    return clean
