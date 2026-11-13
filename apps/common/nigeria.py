"""
One spelling per Nigerian state.

Sign-up forms stored the same state several ways ("Lagos", "Lagos State",
"lagos state "), and the delivery quote compared them as plain strings, so a
Lagos designer and a Lagos shopper were quoted as interstate. Every state value
is normalised to the canonical name below when it is saved and when it is compared.
"""

NIGERIAN_STATES = [
    'Abia', 'Adamawa', 'Akwa Ibom', 'Anambra', 'Bauchi', 'Bayelsa', 'Benue', 'Borno',
    'Cross River', 'Delta', 'Ebonyi', 'Edo', 'Ekiti', 'Enugu', 'Abuja (FCT)', 'Gombe',
    'Imo', 'Jigawa', 'Kaduna', 'Kano', 'Katsina', 'Kebbi', 'Kogi', 'Kwara',
    'Lagos', 'Nasarawa', 'Niger', 'Ogun', 'Ondo', 'Osun', 'Oyo', 'Plateau',
    'Rivers', 'Sokoto', 'Taraba', 'Yobe', 'Zamfara',
]

_FCT_ALIASES = {'fct', 'abuja', 'abuja fct', 'fct abuja', 'fct - abuja', 'abuja (fct)',
                'federal capital territory', 'fct, abuja'}
_BY_KEY = {name.lower(): name for name in NIGERIAN_STATES}


def normalize_state(value) -> str:
    """'lagos state' -> 'Lagos', 'FCT - Abuja' -> 'Abuja (FCT)'. Unknown values are kept, trimmed."""
    text = ' '.join(str(value or '').split())
    if not text:
        return ''
    key = text.lower()
    if key in _FCT_ALIASES:
        return 'Abuja (FCT)'
    if key.endswith(' state'):
        key = key[: -len(' state')].strip()
    return _BY_KEY.get(key, text)


def same_state(a, b) -> bool:
    return normalize_state(a).lower() == normalize_state(b).lower()
