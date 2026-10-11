"""
My Aso Fit — Intelligent Fit Estimator Engine (PRD v2.0)
Implements Hybrid Architecture:
1. Natural Language Interpretation (Regex / LLM fallback)
2. 3-Factor Anthropometric Matrix (3FAM)
3. Garment-Specific Length & Ease Rules
4. Multi-Tier Confidence Scoring
5. Priority Cascade: Explicit User > Verified Historical > Tailor Confirmed > Deterministic
"""
import re
import math
from typing import Dict, Any, Optional

# Baseline Anchor Matrix (Inches)
BASELINES = {
    'XS': {'bust': 34.0, 'shoulder': 16.5, 'waist': 28.0, 'hips': 35.0, 'sleeve': 24.0, 'top_len': 34.0, 'trouser_len': 39.0, 'thigh': 21.0, 'collar': 14.5},
    'S':  {'bust': 37.0, 'shoulder': 17.5, 'waist': 30.0, 'hips': 38.0, 'sleeve': 24.5, 'top_len': 35.0, 'trouser_len': 40.0, 'thigh': 22.5, 'collar': 15.0},
    'M':  {'bust': 40.0, 'shoulder': 18.5, 'waist': 33.0, 'hips': 41.0, 'sleeve': 25.0, 'top_len': 36.0, 'trouser_len': 41.0, 'thigh': 24.0, 'collar': 15.5},
    'L':  {'bust': 43.0, 'shoulder': 19.5, 'waist': 36.0, 'hips': 44.0, 'sleeve': 25.5, 'top_len': 37.0, 'trouser_len': 42.0, 'thigh': 25.5, 'collar': 16.5},
    'XL': {'bust': 46.0, 'shoulder': 20.5, 'waist': 39.0, 'hips': 47.0, 'sleeve': 26.0, 'top_len': 38.0, 'trouser_len': 43.0, 'thigh': 27.0, 'collar': 17.5},
    'XXL':{'bust': 49.0, 'shoulder': 21.5, 'waist': 43.0, 'hips': 51.0, 'sleeve': 26.5, 'top_len': 39.0, 'trouser_len': 44.0, 'thigh': 28.5, 'collar': 18.5},
    '3XL':{'bust': 52.0, 'shoulder': 22.5, 'waist': 47.0, 'hips': 55.0, 'sleeve': 27.0, 'top_len': 40.0, 'trouser_len': 45.0, 'thigh': 30.0, 'collar': 19.5},
}

# Morphological Build Offsets (Inches)
BUILD_OFFSETS = {
    'slim':     {'bust': -1.5, 'shoulder': -0.3, 'waist': -1.8, 'hips': -1.5, 'thigh': -1.2, 'collar': -0.4},
    'regular':  {'bust': 0.0,  'shoulder': 0.0,  'waist': 0.0,  'hips': 0.0,  'thigh': 0.0,  'collar': 0.0},
    'athletic': {'bust': 1.0,  'shoulder': 0.4,  'waist': -1.2, 'hips': 0.5,  'thigh': 0.8,  'collar': 0.3},
    'broad':    {'bust': 1.2,  'shoulder': 0.6,  'waist': -0.8, 'hips': 0.5,  'thigh': 0.8,  'collar': 0.4},
    'full':     {'bust': 2.5,  'shoulder': 0.2,  'waist': 3.0,  'hips': 3.5,  'thigh': 2.0,  'collar': 0.6},
    'curvy':    {'bust': 2.5,  'shoulder': 0.1,  'waist': 1.0,  'hips': 4.0,  'thigh': 2.2,  'collar': 0.2},
}

# Usual Size Fit Offsets (PRD Section 9)
USUAL_FIT_OFFSETS = {
    'tight':       {'bust': 1.0,  'waist': 1.2,  'hips': 1.0},
    'fitted':      {'bust': 0.0,  'waist': 0.0,  'hips': 0.0},
    'comfortable': {'bust': -0.5, 'waist': -0.5, 'hips': -0.5},
    'relaxed':     {'bust': -1.5, 'waist': -1.5, 'hips': -1.5},
}

# Garment Ease Multipliers (Body vs Garment Ease - PRD Section 10 & 17)
GARMENT_EASE = {
    'slim':    {'chest': 1.5, 'waist': 1.0, 'hips': 1.5, 'thigh': 1.0},
    'regular': {'chest': 2.5, 'waist': 2.0, 'hips': 2.5, 'thigh': 2.0},
    'relaxed': {'chest': 4.0, 'waist': 3.5, 'hips': 4.0, 'thigh': 3.0},
}


def parse_natural_language_profile(text: str) -> Dict[str, Any]:
    """
    Interprets natural language descriptions and extracts structured fit signals.
    Employs robust regex extraction with graceful fallback.
    """
    if not text or not isinstance(text, str):
        return {}

    text_lower = text.lower()
    extracted: Dict[str, Any] = {}

    # 1. Height parsing: 5'10, 5ft 10in, 6ft, 175cm
    ft_in_match = re.search(r"(\d)\s*(?:ft|'|feet)\s*(\d{1,2})?\s*(?:in|\"|inches)?", text_lower)
    if ft_in_match:
        feet = int(ft_in_match.group(1))
        inches = int(ft_in_match.group(2)) if ft_in_match.group(2) else 0
        extracted['height_inches'] = feet * 12 + inches
    else:
        cm_match = re.search(r"(\d{3})\s*cm", text_lower)
        if cm_match:
            extracted['height_inches'] = round(int(cm_match.group(1)) / 2.54, 1)

    # 2. RTW Size parsing: XS, S, M, L, XL, XXL, 3XL
    size_match = re.search(r"\b(xs|3xl|2xl|xxl|xl|small|medium|large|extra large|[sml])\b", text_lower)
    if size_match:
        s = size_match.group(1).upper()
        if s == 'SMALL': s = 'S'
        elif s == 'MEDIUM': s = 'M'
        elif s == 'LARGE': s = 'L'
        elif s in ('EXTRA LARGE', '2XL'): s = 'XXL'
        extracted['rtw_size'] = s

    # 3. Build parsing
    if any(k in text_lower for k in ['broad shoulder', 'athletic', 'gym', 'muscular', 'v-shape']):
        extracted['build'] = 'athletic'
    elif any(k in text_lower for k in ['slim', 'skinny', 'lean', 'thin']):
        extracted['build'] = 'slim'
    elif any(k in text_lower for k in ['pot belly', 'big stomach', 'belly', 'plus size', 'heavy', 'thick', 'chubby', 'full figure']):
        extracted['build'] = 'full'
    elif any(k in text_lower for k in ['curvy', 'hourglass', 'hips']):
        extracted['build'] = 'curvy'

    # 4. Garment fit preference parsing
    if any(k in text_lower for k in ['relaxed', 'loose', 'free', 'flowy', 'oversized', 'not too tight', 'comfortable']):
        extracted['garment_fit'] = 'relaxed'
    elif any(k in text_lower for k in ['tight', 'skin tight', 'body hug', 'snug']):
        extracted['garment_fit'] = 'slim'
    elif 'fitted' in text_lower or 'tailored' in text_lower:
        extracted['garment_fit'] = 'regular'

    return extracted


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
    customer = None
) -> Dict[str, Any]:
    """
    PRD v2.0 Deterministic Fit Estimation Engine with Confidence Scoring.
    """
    known_measurements = known_measurements or {}
    
    # Merge natural language signals if provided
    llm_confidence = 0.0
    if text_description:
        parsed_nlp = parse_natural_language_profile(text_description)
        if 'height_inches' in parsed_nlp: height_inches = parsed_nlp['height_inches']
        if 'rtw_size' in parsed_nlp: rtw_size = parsed_nlp['rtw_size']
        if 'build' in parsed_nlp: build = parsed_nlp['build']
        if 'garment_fit' in parsed_nlp: garment_fit = parsed_nlp['garment_fit']
        llm_confidence = 0.85

    # Sanitize and normalize inputs
    rtw_size = str(rtw_size).upper()
    if rtw_size not in BASELINES:
        rtw_size = 'M'
    
    height_inches = float(height_inches or 70.0)
    height_inches = max(54.0, min(84.0, height_inches)) # Bounded 4'6" to 7'0"
    
    build = str(build).lower()
    if build not in BUILD_OFFSETS:
        build = 'regular'

    usual_size_fit = str(usual_size_fit).lower()
    if usual_size_fit not in USUAL_FIT_OFFSETS:
        usual_size_fit = 'fitted'

    garment_fit = str(garment_fit).lower()
    if garment_fit not in GARMENT_EASE:
        garment_fit = 'regular'

    # 1. Base Anchor
    base = BASELINES[rtw_size]
    b_offset = BUILD_OFFSETS[build]
    u_offset = USUAL_FIT_OFFSETS[usual_size_fit]
    ease = GARMENT_EASE[garment_fit]

    # Height variance from 5'10" (70 in)
    delta_h = height_inches - 70.0

    # 2. Net Body Measurements
    body_chest = round(base['bust'] + b_offset['bust'] + u_offset['bust'], 1)
    body_shoulder = round(base['shoulder'] + b_offset['shoulder'] + (delta_h * 0.05), 1)
    body_waist = round(base['waist'] + b_offset['waist'] + u_offset['waist'], 1)
    body_hips = round(base['hips'] + b_offset['hips'] + u_offset['hips'], 1)
    body_sleeve = round(base['sleeve'] + (delta_h * 0.3), 1)
    body_thigh = round(base['thigh'] + b_offset['thigh'], 1)
    body_collar = round(base['collar'] + b_offset['collar'], 1)
    body_underbust = round(body_waist - 2.0, 1)

    # 3. Garment Cut Measurements (Length rules & ease)
    if style == 'modern_short':
        top_len_base = 33.0
        top_len_scale = 0.5
    elif style == 'long':
        top_len_base = 42.0
        top_len_scale = 0.75
    else: # standard
        top_len_base = 37.0
        top_len_scale = 0.60
    
    garment_top_len = round(top_len_base + (delta_h * top_len_scale), 1)
    garment_trouser_len = round(base['trouser_len'] + (delta_h * 0.70), 1)
    garment_inseam = round(garment_trouser_len - 10.0, 1)
    
    if 'gown' in category or 'corset' in category:
        garment_top_len = round(56.0 + (delta_h * 0.85), 1)
    
    garment_chest = round(body_chest + ease['chest'], 1)
    garment_waist = round(body_waist + ease['waist'], 1)
    garment_hips = round(body_hips + ease['hips'], 1)

    # 4. Assembled Raw Prediction Spec
    raw_measurements = {
        'chest_bust': body_chest,
        'shoulder': body_shoulder,
        'waist': body_waist,
        'hips': body_hips,
        'sleeve_length': body_sleeve,
        'top_length': garment_top_len,
        'trouser_length': garment_trouser_len,
        'inseam': garment_inseam,
        'thigh': body_thigh,
        'neck_collar': body_collar,
        'underbust': body_underbust,
        'shoulder_to_underbust': round(14.0 + (delta_h * 0.1), 1),
    }

    # 5. Priority Cascade (PRD Section 16: Explicit User > Historical > Estimator)
    final_measurements: Dict[str, Any] = {}
    sources: Dict[str, str] = {}
    confidences: Dict[str, float] = {}

    for key, val in raw_measurements.items():
        if key in known_measurements and known_measurements[key]:
            final_measurements[key] = float(known_measurements[key])
            sources[key] = 'user'
            confidences[key] = 1.0
        elif customer and getattr(customer, 'saved_measurements', None) and key in customer.saved_measurements:
            final_measurements[key] = float(customer.saved_measurements[key])
            sources[key] = 'historical'
            confidences[key] = 0.92
        else:
            final_measurements[key] = val
            sources[key] = 'llm_interpreted' if llm_confidence > 0 else 'deterministic'
            
            if key in ('chest_bust', 'waist'):
                confidences[key] = 0.84 if usual_size_fit != 'fitted' else 0.78
            elif key in ('shoulder', 'sleeve_length'):
                confidences[key] = 0.82
            elif key in ('top_length', 'trouser_length'):
                confidences[key] = 0.88 if delta_h != 0 else 0.80
            else:
                confidences[key] = 0.75

    SPREAD_MAP = {
        'chest_bust': 1.0,
        'shoulder': 0.5,
        'waist': 1.5,
        'hips': 1.5,
        'top_length': 1.0,
        'trouser_length': 1.0,
        'sleeve_length': 0.5,
        'neck_collar': 0.5,
        'underbust': 1.0,
        'thigh': 1.0,
        'inseam': 1.0,
        'shoulder_to_underbust': 0.5,
    }

    estimated_ranges: Dict[str, Any] = {}
    for key, val in final_measurements.items():
        delta = SPREAD_MAP.get(key, 1.0)
        try:
            target_val = float(val)
            min_v = round(target_val - delta, 1)
            max_v = round(target_val + delta, 1)
            estimated_ranges[key] = {
                'min': min_v,
                'max': max_v,
                'target': target_val,
                'bracket': f"{min_v} - {max_v}",
                'unit': 'IN',
            }
        except (ValueError, TypeError):
            pass

    avg_conf = sum(confidences.values()) / max(1, len(confidences))
    if avg_conf >= 0.85:
        overall_tier = 'high'
        tier_label = 'Strong fit estimate'
    elif avg_conf >= 0.72:
        overall_tier = 'medium'
        tier_label = 'Good starting estimate'
    else:
        overall_tier = 'low'
        tier_label = 'We recommend adding your chest and waist measurements for a better fit.'

    return {
        'version': '1.2',
        'estimated_ranges': estimated_ranges,
        'confidence_tier': overall_tier,
        'confidence_label': tier_label,
        'confidence_score': round(avg_conf, 2),
        'input_profile': {
            'rtw_size': rtw_size,
            'height_inches': height_inches,
            'build': build,
            'usual_size_fit': usual_size_fit,
            'garment_fit': garment_fit,
            'style': style,
            'category': category,
        },
        'body_measurements': {
            'chest': body_chest,
            'shoulder': body_shoulder,
            'waist': body_waist,
            'hips': body_hips,
            'underbust': body_underbust,
        },
        'garment_measurements': {
            'chest': garment_chest,
            'waist': garment_waist,
            'hips': garment_hips,
            'top_length': garment_top_len,
            'trouser_length': garment_trouser_len,
        },
        'measurements': final_measurements,
        'confidences': confidences,
        'sources': sources,
        'disclaimer': 'These are estimated measurements. For the most accurate fit, enter your actual measurements.'
    }
