"""Forgot-password flow, readable validation errors and sign-in rate limiting."""
import re

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   FRONTEND_URL='https://asomarketplace.com.ng')
class PasswordResetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email='ada@aso.test', password='OldPassword123!', first_name='Ada')

    def _link(self):
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].alternatives[0][0]
        m = re.search(r'/reset-password\?uid=([^&"]+)&token=([^"&]+)', body)
        self.assertIsNotNone(m, body)
        self.assertIn('https://asomarketplace.com.ng/reset-password', body)
        return m.group(1), m.group(2)

    def test_request_sends_email_with_link(self):
        res = self.client.post('/api/v1/auth/password-reset/', {'email': 'ADA@aso.test'}, format='json')
        self.assertEqual(res.status_code, 200)
        self._link()

    def test_unknown_email_gets_same_answer_and_no_email(self):
        known = self.client.post('/api/v1/auth/password-reset/', {'email': 'ada@aso.test'}, format='json')
        mail.outbox.clear()
        unknown = self.client.post('/api/v1/auth/password-reset/', {'email': 'nobody@aso.test'}, format='json')
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.data['message'], known.data['message'])
        self.assertEqual(mail.outbox, [])

    def test_confirm_changes_password_and_link_works_once(self):
        self.client.post('/api/v1/auth/password-reset/', {'email': 'ada@aso.test'}, format='json')
        uid, token = self._link()
        payload = {'uid': uid, 'token': token, 'new_password': 'BrandNewPass456!'}
        res = self.client.post('/api/v1/auth/password-reset/confirm/', payload, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPass456!'))
        again = self.client.post('/api/v1/auth/password-reset/confirm/', payload, format='json')
        self.assertEqual(again.status_code, 400)
        login = self.client.post('/api/v1/auth/login/', {'email': 'ada@aso.test', 'password': 'BrandNewPass456!'}, format='json')
        self.assertEqual(login.status_code, 200)

    def test_bad_token_and_weak_password_rejected(self):
        self.client.post('/api/v1/auth/password-reset/', {'email': 'ada@aso.test'}, format='json')
        uid, token = self._link()
        bad = self.client.post('/api/v1/auth/password-reset/confirm/',
                               {'uid': uid, 'token': 'nope', 'new_password': 'BrandNewPass456!'}, format='json')
        self.assertEqual(bad.status_code, 400)
        self.assertIn('expired', bad.data['error']['message'])
        weak = self.client.post('/api/v1/auth/password-reset/confirm/',
                                {'uid': uid, 'token': token, 'new_password': 'short'}, format='json')
        self.assertEqual(weak.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPassword123!'))


class ReadableErrorTests(TestCase):
    def test_duplicate_email_message_names_the_problem(self):
        User.objects.create_user(email='taken@aso.test', password='Password123!')
        res = APIClient().post('/api/v1/auth/register/', {
            'email': 'taken@aso.test', 'password': 'Password123!', 'first_name': 'A', 'last_name': 'B',
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data['error']['message'], 'Email: A user with this email address already exists.')

    def test_wrong_password_message(self):
        res = APIClient().post('/api/v1/auth/login/', {'email': 'x@aso.test', 'password': 'wrong'}, format='json')
        self.assertEqual(res.data['error']['message'], 'Invalid email or password.')


class LoginRateLimitTests(TestCase):
    def test_eleventh_attempt_in_a_minute_is_blocked(self):
        client = APIClient()
        for _ in range(10):
            self.assertEqual(client.post('/api/v1/auth/login/', {'email': 'x@aso.test', 'password': 'bad'},
                                         format='json').status_code, 400)
        self.assertEqual(client.post('/api/v1/auth/login/', {'email': 'x@aso.test', 'password': 'bad'},
                                     format='json').status_code, 429)
