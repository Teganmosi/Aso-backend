"""AUTH-02: 6-digit email code at sign-up; checkout and opening a studio need a confirmed email."""
import re
from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import EmailVerificationCode, User
from apps.common.nigeria import normalize_phone

SIGNUP = {
    'email': 'Ngozi@Example.com', 'password': 'Adire-Indigo-2026', 'first_name': 'Ngozi', 'last_name': 'Eze',
    'phone_number': '0803 123 4567',
}


def _code_from_outbox(index=-1):
    message = mail.outbox[index]
    match = re.search(r'\b(\d{6})\b', message.subject)
    assert match, message.subject
    return match.group(1)


@override_settings(REQUIRE_EMAIL_VERIFICATION=True, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EmailVerificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _signup(self, **overrides):
        res = self.client.post('/api/v1/auth/register/', {**SIGNUP, **overrides}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        return res

    def test_signup_emails_a_code_and_starts_unverified(self):
        res = self._signup()
        self.assertTrue(res.data['verification_sent'])
        self.assertFalse(res.data['user']['email_verified'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['ngozi@example.com'])
        code = _code_from_outbox()
        self.assertIn(code, mail.outbox[0].alternatives[0][0])
        # Only a hash is stored.
        self.assertNotIn(code, EmailVerificationCode.objects.get().code_hash)

    def test_correct_code_confirms_email(self):
        self._signup()
        res = self.client.post('/api/v1/auth/verify-email/', {'code': _code_from_outbox()}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data['user']['email_verified'])
        user = User.objects.get(email='ngozi@example.com')
        self.assertIsNotNone(user.email_verified_at)
        self.assertFalse(EmailVerificationCode.objects.filter(user=user).exists())

    def test_code_with_spaces_is_accepted(self):
        self._signup()
        code = _code_from_outbox()
        res = self.client.post('/api/v1/auth/verify-email/', {'code': f'{code[:3]} {code[3:]}'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)

    def test_wrong_code_counts_down_then_locks(self):
        self._signup()
        good = _code_from_outbox()
        wrong = '000000' if good != '000000' else '111111'
        for left in (4, 3, 2, 1):
            res = self.client.post('/api/v1/auth/verify-email/', {'code': wrong}, format='json')
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.data['error']['code'], 'invalid_code')
            self.assertIn(f'{left} ', res.data['error']['message'])
        res = self.client.post('/api/v1/auth/verify-email/', {'code': wrong}, format='json')
        self.assertEqual(res.data['error']['code'], 'too_many_attempts')
        # Even the right code no longer works; a new one must be sent.
        res = self.client.post('/api/v1/auth/verify-email/', {'code': good}, format='json')
        self.assertEqual(res.data['error']['code'], 'too_many_attempts')

    def test_expired_code_rejected(self):
        self._signup()
        EmailVerificationCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        res = self.client.post('/api/v1/auth/verify-email/', {'code': _code_from_outbox()}, format='json')
        self.assertEqual(res.data['error']['code'], 'code_expired')

    def test_resend_waits_a_minute_then_replaces_the_code(self):
        self._signup()
        first = _code_from_outbox()
        too_soon = self.client.post('/api/v1/auth/verify-email/resend/', format='json')
        self.assertEqual(too_soon.status_code, 429)
        self.assertEqual(len(mail.outbox), 1)

        EmailVerificationCode.objects.update(sent_at=timezone.now() - timedelta(seconds=61))
        res = self.client.post('/api/v1/auth/verify-email/resend/', format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(mail.outbox), 2)
        second = _code_from_outbox()
        if first != second:
            old = self.client.post('/api/v1/auth/verify-email/', {'code': first}, format='json')
            self.assertEqual(old.status_code, 400)
        ok = self.client.post('/api/v1/auth/verify-email/', {'code': second}, format='json')
        self.assertEqual(ok.status_code, 200)

    def test_verify_needs_sign_in(self):
        res = APIClient().post('/api/v1/auth/verify-email/', {'code': '123456'}, format='json')
        self.assertIn(res.status_code, (401, 403))

    def test_unverified_user_cannot_place_order_or_open_studio(self):
        self._signup()
        order = self.client.post('/api/v1/orders/', {'address_id': '00000000-0000-0000-0000-000000000000'}, format='json')
        self.assertEqual(order.status_code, 403)
        self.assertEqual(order.data['error']['code'], 'email_not_verified')
        studio = self.client.post('/api/v1/vendors/register/', {
            'store_name': 'Eze Atelier', 'city': 'Enugu', 'state': 'Enugu',
        }, format='json')
        self.assertEqual(studio.status_code, 403)
        self.assertEqual(studio.data['error']['code'], 'email_not_verified')

    def test_verified_user_can_open_studio(self):
        self._signup()
        self.client.post('/api/v1/auth/verify-email/', {'code': _code_from_outbox()}, format='json')
        studio = self.client.post('/api/v1/vendors/register/', {
            'store_name': 'Eze Atelier', 'city': 'Enugu', 'state': 'Enugu',
        }, format='json')
        self.assertEqual(studio.status_code, 201, studio.data)

    def test_password_reset_link_also_confirms_email(self):
        user = User.objects.create_user(email='ada@aso.test', password='OldPassword123!', first_name='Ada')
        self.assertIsNone(user.email_verified_at)
        self.client.post('/api/v1/auth/password-reset/', {'email': 'ada@aso.test'}, format='json')
        body = mail.outbox[-1].alternatives[0][0]
        uid, token = re.search(r'uid=([^&"]+)&token=([^"&]+)', body).groups()
        res = self.client.post('/api/v1/auth/password-reset/confirm/',
                               {'uid': uid, 'token': token, 'new_password': 'BrandNewPass456!'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        user.refresh_from_db()
        self.assertIsNotNone(user.email_verified_at)

    @override_settings(REQUIRE_EMAIL_VERIFICATION=False)
    def test_kill_switch_skips_the_code(self):
        res = self._signup()
        self.assertTrue(res.data['user']['email_verified'])
        self.assertFalse(res.data['verification_sent'])
        self.assertEqual(mail.outbox, [])


class SignupValidationTests(TestCase):
    def test_phone_is_stored_in_one_format(self):
        res = APIClient().post('/api/v1/auth/register/', SIGNUP, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['user']['phone_number'], '+2348031234567')

    def test_same_number_in_another_format_is_a_duplicate(self):
        User.objects.create_user(email='old@aso.test', password='x', phone_number='08031234567')
        res = APIClient().post('/api/v1/auth/register/', {**SIGNUP, 'phone_number': '+234 803 123 4567'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('already on another Aso account', res.data['error']['message'])

    def test_non_nigerian_number_rejected(self):
        res = APIClient().post('/api/v1/auth/register/', {**SIGNUP, 'phone_number': '12345'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Nigerian mobile number', res.data['error']['message'])

    def test_weak_password_rejected_with_reason(self):
        res = APIClient().post('/api/v1/auth/register/', {**SIGNUP, 'password': 'password123'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('too common', res.data['error']['message'])

    def test_profile_phone_update_normalises(self):
        user = User.objects.create_user(email='p@aso.test', password='x')
        client = APIClient()
        client.force_authenticate(user)
        res = client.patch('/api/v1/auth/me/', {'phone_number': '0905 555 1234'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['user']['phone_number'], '+2349055551234')
        bad = client.patch('/api/v1/auth/me/', {'phone_number': 'call me'}, format='json')
        self.assertEqual(bad.status_code, 400)


class NormalizePhoneTests(TestCase):
    def test_formats(self):
        for raw in ('08031234567', '8031234567', '2348031234567', '+234 803 123 4567', '0803-123-4567'):
            self.assertEqual(normalize_phone(raw), '+2348031234567', raw)
        for raw in ('', '12345', '01234567890', '+44 7911 123456'):
            self.assertIsNone(normalize_phone(raw), raw)
