"""
Email verification (AUTH-02).

At sign-up we email a 6-digit code. Shoppers can browse and fill a cart straight
away; placing an order and opening a designer studio need a confirmed email, so
receipts, payout notices and "book a rider" emails reach a real inbox.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework import status
from rest_framework.response import Response

from .models import EmailVerificationCode, User

CODE_LIFETIME = timedelta(minutes=15)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5


def _hash(user: User, code: str) -> str:
    # Keyed by SECRET_KEY and the user, so a leaked hash can't be brute-forced offline
    # without the key, and one user's hash is useless for another.
    return salted_hmac('aso.email-verification', f'{user.pk}:{user.email}:{code}').hexdigest()


def verification_required() -> bool:
    return getattr(settings, 'REQUIRE_EMAIL_VERIFICATION', True)


def mark_verified(user: User) -> None:
    if user.email_verified_at is None:
        user.email_verified_at = timezone.now()
        user.save(update_fields=['email_verified_at'])
    EmailVerificationCode.objects.filter(user=user).delete()


def send_code(user: User, *, force: bool = False) -> dict:
    """
    Emails a fresh code. Returns {'sent': bool, 'retry_after': seconds}.
    Within RESEND_COOLDOWN of the last send it does nothing (unless force=True),
    so double-clicks and refresh loops don't spend email quota.
    """
    from apps.common.notifications import send_email_verification_code

    if user.email_verified:
        return {'sent': False, 'retry_after': 0, 'already_verified': True}

    now = timezone.now()
    existing = EmailVerificationCode.objects.filter(user=user).first()
    if existing and not force and now - existing.sent_at < RESEND_COOLDOWN:
        wait = int((RESEND_COOLDOWN - (now - existing.sent_at)).total_seconds()) + 1
        return {'sent': False, 'retry_after': wait}

    code = f'{secrets.randbelow(1_000_000):06d}'
    with transaction.atomic():
        EmailVerificationCode.objects.update_or_create(
            user=user,
            defaults={
                'code_hash': _hash(user, code),
                'expires_at': now + CODE_LIFETIME,
                'attempts': 0,
                'sent_at': now,
            },
        )
    sent = send_email_verification_code(user, code, minutes=int(CODE_LIFETIME.total_seconds() // 60))
    return {'sent': bool(sent), 'retry_after': int(RESEND_COOLDOWN.total_seconds())}


def check_code(user: User, code: str) -> tuple[bool, str, str]:
    """Returns (ok, error_code, message)."""
    if user.email_verified:
        return True, '', 'Your email is already confirmed.'

    code = ''.join(ch for ch in str(code or '') if ch.isdigit())
    record = EmailVerificationCode.objects.filter(user=user).first()
    if record is None:
        return False, 'code_missing', 'Request a new code and try again.'
    if timezone.now() > record.expires_at:
        return False, 'code_expired', 'That code has expired. Tap “Send a new code”.'
    if record.attempts >= MAX_ATTEMPTS:
        return False, 'too_many_attempts', 'Too many wrong tries. Tap “Send a new code”.'

    if len(code) != 6 or not constant_time_compare(record.code_hash, _hash(user, code)):
        record.attempts += 1
        record.save(update_fields=['attempts', 'updated_at'])
        left = MAX_ATTEMPTS - record.attempts
        if left <= 0:
            return False, 'too_many_attempts', 'Too many wrong tries. Tap “Send a new code”.'
        return False, 'invalid_code', f'That code isn’t right. {left} {"try" if left == 1 else "tries"} left.'

    mark_verified(user)
    return True, '', 'Thanks, your email is confirmed.'


def email_not_verified_response(user: User, action: str) -> Response | None:
    """
    None when the user may go ahead; otherwise a 403 the frontend recognises
    (error.code == 'email_not_verified') and answers with the code box.
    """
    if not verification_required() or user.email_verified:
        return None
    return Response({
        'success': False,
        'error': {
            'code': 'email_not_verified',
            'message': f'Please confirm your email before you {action}. '
                       f'Enter the 6-digit code we sent to {user.email}.',
        },
    }, status=status.HTTP_403_FORBIDDEN)
