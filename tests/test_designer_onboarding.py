"""
Regression tests for designer onboarding (QA report 2026-11-10):
  * QA-09: a brand-new user (no vendor profile yet) must be able to register a studio.
  * Verification badge: a designer who has NOT submitted NIN/CAC must not be reported
    as "verification started" (the UI shows "Verification in Progress" from this flag).
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import User
from apps.vendors.models import VendorProfile, VendorStatus


def _vendor_profile_from_me(data):
    body = data.get('user', data) if isinstance(data, dict) else data
    if isinstance(body, dict) and 'data' in body and isinstance(body['data'], dict):
        body = body['data']
    return body['vendor_profile']


class DesignerOnboardingTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='newdesigner@example.com', password='Password123!',
            first_name='Ada', last_name='Okafor',
        )
        self.client.force_authenticate(user=self.user)
        self.register_url = reverse('vendor-register')
        self.me_url = reverse('auth-me')

    def _register(self, **extra):
        payload = {'store_name': 'Ada Atelier', 'city': 'Lagos', 'state': 'Lagos', **extra}
        return self.client.post(self.register_url, payload, format='json')

    def test_new_user_without_vendor_profile_can_register(self):
        response = self._register()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(VendorProfile.objects.filter(user=self.user).exists())

    def test_anonymous_user_cannot_register(self):
        self.client.force_authenticate(user=None)
        response = self._register()
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_suspended_vendor_cannot_reregister_or_edit_profile(self):
        self._register()
        VendorProfile.objects.filter(user=self.user).update(status=VendorStatus.SUSPENDED)
        self.user.refresh_from_db()
        self.assertEqual(self._register(store_name='Another').status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.patch(reverse('vendor-profile-me') if self._has_url('vendor-profile-me') else '/api/v1/vendors/profile/',
                                 {'description': 'x'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_fresh_designer_has_not_started_verification(self):
        self._register()
        vendor = VendorProfile.objects.get(user=self.user)
        self.assertFalse(vendor.has_started_verification)
        me = self.client.get(self.me_url)
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertFalse(_vendor_profile_from_me(me.data)['has_started_verification'])

    def test_designer_with_saved_nin_has_started_verification(self):
        self._register(nin_number='12345678901')
        vendor = VendorProfile.objects.get(user=self.user)
        self.assertTrue(vendor.has_started_verification)
        self.assertFalse(vendor.is_verified)
        me = self.client.get(self.me_url)
        self.assertTrue(_vendor_profile_from_me(me.data)['has_started_verification'])

    @staticmethod
    def _has_url(name):
        try:
            reverse(name)
            return True
        except Exception:
            return False
