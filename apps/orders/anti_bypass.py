import re
import json
import logging
import urllib.request
import urllib.error
from django.conf import settings

logger = logging.getLogger(__name__)

ESCROW_MASK_NOTICE = "[Contact details hidden for your protection. All communications and payments are protected under Aso Escrow.]"

# Tier 1 Regex Patterns
PHONE_REGEX = re.compile(
    r'(?:\+?234[\s.-]?[789][01]\d(?:[\s.-]?\d){7}|0[789][01]\d(?:[\s.-]?\d){7})',
    re.IGNORECASE
)
PHONETIC_PHONE_REGEX = re.compile(
    r'(?:zero|o)\s+(?:eight|seven|nine)\s+(?:zero|one)\s+(?:[a-z0-9\s-]{5,30})',
    re.IGNORECASE
)
BANK_KEYWORD_REGEX = re.compile(
    r'(?:acct|account|bank|opay|kuda|gtbank|gtb|zenith|access|uba|firstbank|palmpay)',
    re.IGNORECASE
)
TEN_DIGIT_NUBAN = re.compile(r'\d{10}')
SOCIAL_URL_REGEX = re.compile(
    r'(?:https?:\/\/)?(?:www\.)?(?:instagram\.com\/|wa\.me\/|wa\.link\/|t\.me\/|tiktok\.com\/|snapchat\.com\/)[a-zA-Z0-9_.-]+',
    re.IGNORECASE
)
EMAIL_REGEX = re.compile(
    r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}',
    re.IGNORECASE
)

SUSPICIOUS_INTENT_WORDS = [
    'call', 'reach', 'dm', 'gram', 'ig', 'whatsapp', 'wa', 'outside', 'transfer',
    'pay me', 'send to my', 'my line', 'my number', 'bio', 'handle', 'opay', 'kuda', 'bank'
]


def check_heuristic_bypass(text: str):
    """
    Tier 1 Instant Deterministic Regex Shield (<5ms).
    """
    # Check Phone
    if PHONE_REGEX.search(text):
        masked = PHONE_REGEX.sub(ESCROW_MASK_NOTICE, text)
        return True, masked, "PHONE_NUMBER_DETECTED", "HEURISTIC"

    if PHONETIC_PHONE_REGEX.search(text):
        masked = PHONETIC_PHONE_REGEX.sub(ESCROW_MASK_NOTICE, text)
        return True, masked, "PHONETIC_PHONE_DETECTED", "HEURISTIC"

    # Check Email
    if EMAIL_REGEX.search(text):
        masked = EMAIL_REGEX.sub(ESCROW_MASK_NOTICE, text)
        return True, masked, "EMAIL_ADDRESS_DETECTED", "HEURISTIC"

    # Check Social & External URLs
    if SOCIAL_URL_REGEX.search(text):
        masked = SOCIAL_URL_REGEX.sub(ESCROW_MASK_NOTICE, text)
        return True, masked, "EXTERNAL_LINK_DETECTED", "HEURISTIC"

    # Check Bank Account (keyword + 10 digits)
    if BANK_KEYWORD_REGEX.search(text) and TEN_DIGIT_NUBAN.search(text):
        masked = TEN_DIGIT_NUBAN.sub(ESCROW_MASK_NOTICE, text)
        return True, masked, "BANK_ACCOUNT_DETECTED", "HEURISTIC"

    return False, text, None, None


def check_llm_nemotron_bypass(text: str):
    """
    Tier 2 Semantic LLM Guard powered by NVIDIA NIM Nemotron-30B.
    Analyzes intent, disguised phonetics, and colloquial Nigerian off-platform bypass attempts.
    """
    api_key = getattr(settings, 'NVIDIA_NIM_API_KEY', None)
    if not api_key:
        return False, text, None, None

    lower_text = text.lower()
    if not any(word in lower_text for word in SUSPICIOUS_INTENT_WORDS):
        return False, text, None, None

    base_url = getattr(settings, 'NVIDIA_NIM_BASE_URL', "https://integrate.api.nvidia.com/v1") + "/chat/completions"
    model_name = getattr(settings, 'NVIDIA_NIM_MODEL', "nvidia/nemotron-3.5-lightning-30b-a3b")

    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict security moderation filter for an African luxury bespoke fashion escrow platform (Aso). "
                    "Determine if the user's message is attempting to bypass escrow, exchange external contact information (phone, WhatsApp, Instagram, Telegram), "
                    "or arrange off-platform bank payments. "
                    "Legitimate tailoring questions (lining, color, fabric, zipper, measurements like waist, hips, bust, length) are 100% permitted. "
                    "Respond ONLY with raw JSON: {\"is_bypass\": boolean, \"reason\": string}."
                )
            },
            {
                "role": "user",
                "content": text
            }
        ],
        "temperature": 0.1,
        "max_tokens": 150,
        "chat_template_kwargs": {"enable_thinking": False}
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    req = urllib.request.Request(base_url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            raw_content = data['choices'][0]['message']['content'].strip()
            if "{" in raw_content and "}" in raw_content:
                json_str = raw_content[raw_content.find("{"):raw_content.rfind("}")+1]
                parsed = json.loads(json_str)
                if parsed.get("is_bypass"):
                    return True, ESCROW_MASK_NOTICE, parsed.get("reason", "SEMANTIC_BYPASS_DETECTED"), "LLM_NEMOTRON"
    except Exception as e:
        logger.warning(f"Tier 2 LLM check timed out or failed gracefully: {e}")
        return False, text, None, None

    return False, text, None, None


def sanitize_order_message(text: str):
    """
    Main entry point for two-tier hybrid message sanitization.
    Returns: (is_masked, sanitized_content, mask_reason, mask_tier)
    """
    clean_text = text.strip()
    if not clean_text:
        return False, clean_text, None, None

    # Tier 1: Local Heuristic
    is_masked, masked_text, reason, tier = check_heuristic_bypass(clean_text)
    if is_masked:
        return True, masked_text, reason, tier

    # Tier 2: NVIDIA NIM Nemotron LLM
    is_masked, masked_text, reason, tier = check_llm_nemotron_bypass(clean_text)
    if is_masked:
        return True, masked_text, reason, tier

    return False, clean_text, None, None
