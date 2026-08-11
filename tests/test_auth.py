from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.accounts.models import User

class AuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse('auth-register')
        self.login_url = reverse('auth-login')
        self.logout_url = reverse('auth-logout')
        self.me_url = reverse('auth-me')
        self.user_data = {
            'email': 'customer@example.com',
            'password': 'Password123!',
            'first_name': 'Amina',
            'last_name': 'Okafor',
            'phone_number': '08012345678'
        }

    def test_user_registration(self):
        response = self.client.post(self.register_url, self.user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['user']['email'], 'customer@example.com')
        self.assertTrue(User.objects.filter(email='customer@example.com').exists())

    def test_duplicate_email_registration_fails(self):
        self.client.post(self.register_url, self.user_data, format='json')
        response = self.client.post(self.register_url, self.user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_login_success(self):
        self.client.post(self.register_url, self.user_data, format='json')
        login_payload = {
            'email': 'customer@example.com',
            'password': 'Password123!'
        }
        response = self.client.post(self.login_url, login_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('sessionid', response.cookies)

    def test_duplicate_phone_registration_fails(self):
        self.client.post(self.register_url, self.user_data, format='json')
        duplicate_phone_data = self.user_data.copy()
        duplicate_phone_data['email'] = 'other@example.com'
        response = self.client.post(self.register_url, duplicate_phone_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_me_unauthenticated_fails(self):
        response = self.client.get(self.me_url)
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_logout(self):
        self.client.post(self.register_url, self.user_data, format='json')
        self.client.post(self.login_url, {
            'email': 'customer@example.com',
            'password': 'Password123!'
        }, format='json')

        logout_response = self.client.post(self.logout_url)
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)
        self.assertTrue(logout_response.data['success'])

        me_response = self.client.get(self.me_url)
        self.assertIn(me_response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
