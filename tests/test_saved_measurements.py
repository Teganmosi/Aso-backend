"""
"My Aso Fit" saved measurements (GET/PUT/PATCH /api/v1/auth/profile/measurements/).
This endpoint returned a 500 (NameError: CustomerProfile not imported) for
every shopper and had no tests.
"""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User

URL = '/api/v1/auth/profile/measurements/'


class SavedMeasurementsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email='fit@aso.test', password='Password123!')

    def test_requires_login(self):
        self.assertIn(self.client.get(URL).status_code,
                      (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_new_shopper_gets_empty_profile(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['saved_measurements'], {})

    def test_save_then_read_back(self):
        self.client.force_authenticate(user=self.user)
        measurements = {'bust': 36, 'waist': 30, 'hips': 40, 'unit': 'in'}
        res = self.client.put(URL, {'measurements': measurements}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        saved = self.client.get(URL).data['saved_measurements']
        for key, value in measurements.items():
            self.assertEqual(saved.get(key), value)

    def test_rejects_non_object(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.put(URL, {'measurements': [1, 2, 3]}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
