from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.accounts.models import User
from apps.vendors.models import VendorProfile, VendorStatus

class VendorTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='designer@example.com',
            password='Password123!',
            first_name='Kofi',
            last_name='Babatunde'
        )
        self.client.force_authenticate(user=self.user)
        self.register_vendor_url = reverse('vendor-register')

    def test_vendor_registration_defaults_to_pending(self):
        payload = {
            'store_name': 'Lagos Couture',
            'city': 'Lagos',
            'state': 'Lagos',
            'description': 'Bespoke native apparel and senators',
            'account_name': 'Kofi Babatunde',
            'account_number': '0123456789',
            'bank_name': 'Access Bank',
            'bank_code': '044'
        }
        response = self.client.post(self.register_vendor_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(VendorProfile.objects.filter(store_name='Lagos Couture').exists())
        
        vendor = VendorProfile.objects.get(store_name='Lagos Couture')
        self.assertEqual(vendor.status, VendorStatus.PENDING)
        self.assertFalse(vendor.is_verified)

    def test_approved_vendor_storefront_view_hides_bank_account(self):
        vendor = VendorProfile.objects.create(
            user=self.user,
            store_name='Abuja Threads',
            city='Abuja',
            state='FCT',
            status=VendorStatus.APPROVED,
            is_verified=True
        )
        detail_url = reverse('vendor-detail', kwargs={'slug': vendor.slug})

        anonymous_client = APIClient()
        response = anonymous_client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['vendor']['store_name'], 'Abuja Threads')
        self.assertNotIn('bank_account', response.data['vendor'])

    def test_pending_vendor_hidden_from_public_lookup(self):
        vendor = VendorProfile.objects.create(
            user=self.user,
            store_name='Pending Couture',
            city='Ibadan',
            state='Oyo',
            status=VendorStatus.PENDING
        )
        detail_url = reverse('vendor-detail', kwargs={'slug': vendor.slug})

        anonymous_client = APIClient()
        response = anonymous_client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_partial_bank_details_submission_fails(self):
        payload = {
            'store_name': 'Incomplete Bank Store',
            'city': 'Lagos',
            'state': 'Lagos',
            'account_name': 'Kofi Babatunde',
            'account_number': '0123456789'
            # Missing bank_name and bank_code!
        }
        response = self.client.post(self.register_vendor_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_duplicate_vendor_registration_by_same_user_fails(self):
        payload = {'store_name': 'First Store', 'city': 'Lagos', 'state': 'Lagos'}
        self.client.post(self.register_vendor_url, payload, format='json')
        
        payload2 = {'store_name': 'Second Store', 'city': 'Lagos', 'state': 'Lagos'}
        response = self.client.post(self.register_vendor_url, payload2, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_store_name_registration_fails(self):
        payload = {'store_name': 'Unique Native', 'city': 'Lagos', 'state': 'Lagos'}
        self.client.post(self.register_vendor_url, payload, format='json')

        other_user = User.objects.create_user(
            email='other_designer@example.com',
            password='Password123!',
            first_name='Emeka',
            last_name='Nnamdi'
        )
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)

        response = other_client.post(self.register_vendor_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bank_account_get_and_post_by_approved_vendor_owner(self):
        vendor = VendorProfile.objects.create(
            user=self.user,
            store_name='Approved Store',
            city='Lagos',
            state='Lagos',
            status=VendorStatus.APPROVED,
            is_verified=True
        )
        bank_url = reverse('vendor-bank-account')

        # Initial GET before bank account created
        response_get = self.client.get(bank_url)
        self.assertEqual(response_get.status_code, status.HTTP_200_OK)
        self.assertIsNone(response_get.data['bank_account'])

        # Create/Update Bank Account
        bank_payload = {
            'account_name': 'Kofi Babatunde',
            'account_number': '0123456789',
            'bank_name': 'GTBank',
            'bank_code': '058'
        }
        response_post = self.client.post(bank_url, bank_payload, format='json')
        self.assertEqual(response_post.status_code, status.HTTP_200_OK)
        self.assertEqual(response_post.data['bank_account']['bank_name'], 'GTBank')

        # Subsequent GET returns configured bank account
        response_get2 = self.client.get(bank_url)
        self.assertEqual(response_get2.status_code, status.HTTP_200_OK)
        self.assertEqual(response_get2.data['bank_account']['bank_name'], 'GTBank')

    def test_bank_account_endpoint_forbidden_for_unapproved_or_non_vendor(self):
        bank_url = reverse('vendor-bank-account')

        # User without any vendor profile
        response = self.client.get(bank_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # User with PENDING vendor profile
        VendorProfile.objects.create(
            user=self.user,
            store_name='Pending Store',
            city='Lagos',
            state='Lagos',
            status=VendorStatus.PENDING
        )
        response_pending = self.client.get(bank_url)
        self.assertEqual(response_pending.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_approval_updates_user_me_is_vendor_flag(self):
        vendor = VendorProfile.objects.create(
            user=self.user,
            store_name='Fashion House',
            city='Abuja',
            state='FCT',
            status=VendorStatus.PENDING
        )
        me_url = reverse('auth-me')

        # Before approval
        res1 = self.client.get(me_url)
        self.assertFalse(res1.data['user']['is_vendor'])

        # Admin approves application
        vendor.status = VendorStatus.APPROVED
        vendor.is_verified = True
        vendor.save()

        # After approval
        res2 = self.client.get(me_url)
        self.assertTrue(res2.data['user']['is_vendor'])
        self.assertEqual(res2.data['user']['vendor_profile']['store_name'], 'Fashion House')

