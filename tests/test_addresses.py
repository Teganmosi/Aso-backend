from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.accounts.models import User, Address

class AddressTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='address_user@example.com',
            password='Password123!',
            first_name='Chioma',
            last_name='Ade'
        )
        self.client.force_authenticate(user=self.user)
        self.address_url = reverse('address-list')

    def test_create_address(self):
        payload = {
            'full_name': 'Chioma Ade',
            'phone_number': '08099998888',
            'street_address': '12 Victoria Island Road',
            'city': 'Lagos',
            'state': 'Lagos',
            'landmark': 'Near Eko Hotel'
        }
        response = self.client.post(self.address_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertIn('address', response.data)
        self.assertEqual(response.data['address']['city'], 'Lagos')

        # First address should automatically be default
        address = Address.objects.get(user=self.user)
        self.assertTrue(address.is_default)

    def test_list_addresses(self):
        Address.objects.create(
            user=self.user,
            full_name='Chioma Ade',
            phone_number='08099998888',
            street_address='12 Victoria Island',
            city='Lagos',
            state='Lagos'
        )
        response = self.client.get(self.address_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_is_default_toggling_logic(self):
        addr1 = Address.objects.create(
            user=self.user,
            full_name='Chioma Home',
            phone_number='08099998888',
            street_address='12 Victoria Island',
            city='Lagos',
            state='Lagos',
            is_default=True
        )
        payload2 = {
            'full_name': 'Chioma Work',
            'phone_number': '08099998888',
            'street_address': '45 Lekki Phase 1',
            'city': 'Lagos',
            'state': 'Lagos',
            'is_default': True
        }
        response = self.client.post(self.address_url, payload2, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        addr1.refresh_from_db()
        self.assertFalse(addr1.is_default)
        addr2 = Address.objects.get(id=response.data['address']['id'])
        self.assertTrue(addr2.is_default)
