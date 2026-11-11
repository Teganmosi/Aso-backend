"""
QA Verification Suite - Sprint 2: Designer Storefronts & KYC Onboarding.

Covers the sprint.md verification guide flow plus adversarial edge cases:
- Full application -> admin approval -> public storefront lifecycle
- CSRF enforcement on session-authenticated vendor registration
- KYC field validation, bank account validation & atomicity
- Admin bulk actions (approve / reject / KYC tier promotion)
- Security: sensitive field leakage, permission boundaries
- Slug generation & collision handling
"""
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.vendors.models import VendorProfile, BankAccount, VendorStatus, KYCTier
from apps.vendors.serializers import VendorProfileSerializer
from apps.vendors.services import register_vendor_service


class VendorQABase(TestCase):
    """Shared fixtures for Sprint 2 QA tests."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='qa.designer@example.com',
            password='Password123!',
            first_name='Ada',
            last_name='Okonkwo',
        )
        self.client.force_authenticate(user=self.user)
        self.register_url = reverse('vendor-register')
        self.bank_url = reverse('vendor-bank-account')
        self.me_url = reverse('auth-me')

    def make_vendor(self, user=None, store_name='QA Store', status_value=VendorStatus.APPROVED, **extra):
        return VendorProfile.objects.create(
            user=user or self.user,
            store_name=store_name,
            city='Lagos',
            state='Lagos',
            status=status_value,
            **extra,
        )


class SprintGuideFlowTests(VendorQABase):
    """End-to-end walkthrough exactly as written in sprint.md Sprint 2 guide."""

    def test_full_application_to_public_storefront_flow(self):
        """Nov 2026 policy: storefronts go live immediately; the Verified badge is granted
        only after an Aso admin reviews the designer's NIN/CAC."""
        # Step 1: Designer applies for a storefront ("Lagos Luxe Native") with a NIN
        payload = {
            'store_name': 'Lagos Luxe Native',
            'city': 'Lagos',
            'state': 'Lagos',
            'description': 'Premium native attire for the modern Lagosian.',
            'instagram_handle': '@lagosluxenative',
            'workshop_address': '22 Adeola Odeku Street, Victoria Island',
            'landmark': 'Beside Civic Center',
            'nin_number': '12345678901',
        }
        res = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data['success'])
        self.assertEqual(res.data['vendor']['status'], 'APPROVED')
        self.assertEqual(res.data['vendor']['slug'], 'lagos-luxe-native')

        vendor = VendorProfile.objects.get(slug='lagos-luxe-native')
        self.assertEqual(vendor.status, VendorStatus.APPROVED)
        self.assertFalse(vendor.is_verified)
        self.assertEqual(vendor.verification_status, 'PENDING_REVIEW')

        # /me/ reflects a live studio awaiting identity review
        me = self.client.get(self.me_url).data
        self.assertTrue(me['user']['is_vendor'])
        self.assertEqual(me['user']['vendor_profile']['verification_status'], 'PENDING_REVIEW')
        self.assertFalse(me['user']['vendor_profile']['is_verified'])

        # Step 2: Public storefront is live but carries no Verified badge yet
        public_url = reverse('vendor-detail', kwargs={'slug': 'lagos-luxe-native'})
        public = APIClient().get(public_url)
        self.assertEqual(public.status_code, status.HTTP_200_OK)
        body = public.data['vendor']
        self.assertEqual(body['store_name'], 'Lagos Luxe Native')
        self.assertEqual(body['instagram_handle'], '@lagosluxenative')
        self.assertFalse(body['is_verified'])
        self.assertTrue(body['has_started_verification'])

        # Step 3: Staff approves the identity verification via Django Admin action
        # (admin is a plain Django view -> needs a real session login, not DRF force_authenticate)
        admin_user = User.objects.create_superuser(email='admin@example.com', password='AdminPass123!')
        admin_client = APIClient()
        admin_client.force_login(admin_user)
        admin_res = admin_client.post(
            '/admin/vendors/vendorprofile/',
            {'action': 'approve_identity_verification', ACTION_CHECKBOX_NAME: [str(vendor.pk)]},
        )
        self.assertIn(admin_res.status_code, (status.HTTP_200_OK, status.HTTP_302_FOUND))

        vendor.refresh_from_db()
        self.assertTrue(vendor.is_verified)
        self.assertEqual(vendor.verification_status, 'VERIFIED')
        self.assertEqual(vendor.verification_reviewed_by, admin_user)
        self.assertEqual(vendor.kyc_tier, KYCTier.TIER_2_VERIFIED)

        # Step 4: Public storefront now shows the Verified badge
        public = APIClient().get(public_url)
        self.assertTrue(public.data['vendor']['is_verified'])

    def test_admin_reject_action_hides_storefront_and_keeps_is_vendor_false(self):
        vendor = self.make_vendor(status_value=VendorStatus.PENDING, store_name='Reject Me Couture')

        admin_user = User.objects.create_superuser(email='admin2@example.com', password='AdminPass123!')
        admin_client = APIClient()
        admin_client.force_login(admin_user)
        admin_client.post(
            '/admin/vendors/vendorprofile/',
            {'action': 'reject_vendors', ACTION_CHECKBOX_NAME: [str(vendor.pk)]},
        )

        vendor.refresh_from_db()
        self.assertEqual(vendor.status, VendorStatus.REJECTED)

        # is_vendor stays False for rejected vendors
        me = self.client.get(self.me_url).data
        self.assertFalse(me['user']['is_vendor'])

        # Public lookup returns 404
        public = APIClient().get(reverse('vendor-detail', kwargs={'slug': vendor.slug}))
        self.assertEqual(public.status_code, status.HTTP_404_NOT_FOUND)

    def test_storefront_approval_never_grants_badge_and_identity_review_requires_nin_or_cac(self):
        plain_vendor = self.make_vendor(status_value=VendorStatus.PENDING, store_name='Plain Starter')
        other_user = User.objects.create_user(
            email='nin.designer@example.com', password='Password123!',
            first_name='Nin', last_name='Designer',
        )
        nin_vendor = self.make_vendor(user=other_user, status_value=VendorStatus.PENDING,
                                      store_name='NIN Designer', nin_number='12345678901')
        self.assertEqual(nin_vendor.verification_status, 'PENDING_REVIEW')

        admin_user = User.objects.create_superuser(email='admin3@example.com', password='AdminPass123!')
        admin_client = APIClient()
        admin_client.force_login(admin_user)
        ids = [str(plain_vendor.pk), str(nin_vendor.pk)]

        # Approving the storefront does NOT grant the Verified badge
        admin_client.post('/admin/vendors/vendorprofile/', {'action': 'approve_vendors', ACTION_CHECKBOX_NAME: ids})
        plain_vendor.refresh_from_db(); nin_vendor.refresh_from_db()
        self.assertEqual(plain_vendor.status, VendorStatus.APPROVED)
        self.assertFalse(plain_vendor.is_verified)
        self.assertFalse(nin_vendor.is_verified)

        # Identity approval: only the designer who submitted a NIN is verified
        admin_client.post('/admin/vendors/vendorprofile/',
                          {'action': 'approve_identity_verification', ACTION_CHECKBOX_NAME: ids})
        plain_vendor.refresh_from_db(); nin_vendor.refresh_from_db()
        self.assertFalse(plain_vendor.is_verified)
        self.assertEqual(plain_vendor.kyc_tier, KYCTier.TIER_1_STARTER)
        self.assertTrue(nin_vendor.is_verified)
        self.assertEqual(nin_vendor.kyc_tier, KYCTier.TIER_2_VERIFIED)


class RegistrationValidationTests(VendorQABase):
    def test_unauthenticated_vendor_registration_rejected(self):
        res = APIClient().post(self.register_url, {'store_name': 'X', 'city': 'Y', 'state': 'Z'}, format='json')
        self.assertIn(res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertFalse(res.data['success'])

    def test_missing_required_fields_rejected(self):
        for payload in (
            {},
            {'store_name': 'No City Store'},
            {'store_name': 'No State Store', 'city': 'Lagos'},
            {'city': 'Lagos', 'state': 'Lagos'},
        ):
            res = self.client.post(self.register_url, payload, format='json')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg='payload=%s' % payload)
            self.assertFalse(res.data['success'])

    def test_duplicate_store_name_case_insensitive_rejected(self):
        self.client.post(self.register_url, {'store_name': 'Eko Threads', 'city': 'Lagos', 'state': 'Lagos'}, format='json')
        other = User.objects.create_user(email='other@example.com', password='Password123!', first_name='B', last_name='C')
        other_client = APIClient()
        other_client.force_authenticate(user=other)
        res = other_client.post(self.register_url, {'store_name': 'eko THREADS', 'city': 'Lagos', 'state': 'Lagos'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(VendorProfile.objects.filter(store_name__iexact='eko threads').count(), 1)

    def test_invalid_account_number_variants_rejected(self):
        for bad_number in ('123456789', '01234567890', '012345abcd', '012345678a'):
            payload = {
                'store_name': 'Bad Bank ' + bad_number,
                'city': 'Lagos',
                'state': 'Lagos',
                'account_name': 'Ada Okonkwo',
                'account_number': bad_number,
                'bank_name': 'GTBank',
                'bank_code': '058',
            }
            res = self.client.post(self.register_url, payload, format='json')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg='account_number=' + bad_number)

    def test_invalid_nin_variants_rejected(self):
        for bad_nin in ('1234567890', '123456789012', '1234567890a'):
            payload = {'store_name': 'NIN ' + bad_nin + ' Store', 'city': 'Lagos', 'state': 'Lagos', 'nin_number': bad_nin}
            res = self.client.post(self.register_url, payload, format='json')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg='nin=' + bad_nin)

    def test_slug_auto_generated_from_store_name(self):
        self.client.post(self.register_url, {'store_name': "Ada's Adire House", 'city': 'Abeokuta', 'state': 'Ogun'}, format='json')
        vendor = VendorProfile.objects.get(store_name="Ada's Adire House")
        self.assertEqual(vendor.slug, 'adas-adire-house')

    def test_full_registration_creates_linked_bank_account(self):
        payload = {
            'store_name': 'Banked At Signup',
            'city': 'Lagos',
            'state': 'Lagos',
            'account_name': 'Ada Okonkwo',
            'account_number': '0123456789',
            'bank_name': 'Access Bank',
            'bank_code': '044',
        }
        res = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        vendor = VendorProfile.objects.get(store_name='Banked At Signup')
        self.assertTrue(hasattr(vendor, 'bank_account'))
        self.assertEqual(vendor.bank_account.bank_name, 'Access Bank')
        self.assertEqual(vendor.bank_account.account_number, '0123456789')
        # Registration response echoes bank details for the owner
        self.assertEqual(res.data['vendor']['bank_account']['bank_name'], 'Access Bank')

    def test_store_name_collision_producing_identical_slugs_is_handled(self):
        """
        QA REGRESSION (formerly bug probe, fixed 2026-08-11):
        "Kofi's Store" and "Kofis Store" are distinct store names (both pass the
        store_name uniqueness check) but slugify() maps both to 'kofis-store'.
        Previously this raised IntegrityError -> HTTP 500. The fix auto-suffixes
        the slug (kofis-store-1) so the second applicant registers cleanly.
        """
        first = register_vendor_service(user=self.user, store_name="Kofi's Store", city='Lagos', state='Lagos')
        self.assertEqual(first.slug, 'kofis-store')

        other_user = User.objects.create_user(email='other2@example.com', password='Password123!', first_name='K', last_name='O')
        try:
            second = register_vendor_service(user=other_user, store_name='Kofis Store', city='Lagos', state='Lagos')
        except IntegrityError:
            self.fail('Slug collision still raises IntegrityError -> HTTP 500 to the applicant.')

        # Must succeed with a distinct, non-colliding slug
        self.assertEqual(second.slug, 'kofis-store-1')
        self.assertEqual(VendorProfile.objects.filter(slug='kofis-store').count(), 1)

    def test_repeated_slug_collisions_increment_suffix(self):
        """Three colliding store names get -1 and -2 suffixes without crashing."""
        u1 = User.objects.create_user(email='c1@example.com', password='Password123!', first_name='C', last_name='One')
        u2 = User.objects.create_user(email='c2@example.com', password='Password123!', first_name='C', last_name='Two')
        register_vendor_service(user=self.user, store_name='Eko  Threads', city='Lagos', state='Lagos')
        v1 = register_vendor_service(user=u1, store_name='Eko Threads', city='Lagos', state='Lagos')
        v2 = register_vendor_service(user=u2, store_name='Eko-Threads', city='Lagos', state='Lagos')
        self.assertEqual(v1.slug, 'eko-threads-1')
        self.assertEqual(v2.slug, 'eko-threads-2')

    def test_slug_save_update_keeps_own_slug(self):
        """Saving an existing vendor without slug changes must not re-suffix itself."""
        vendor = register_vendor_service(user=self.user, store_name='Stable Styles', city='Lagos', state='Lagos')
        original_slug = vendor.slug
        vendor.city = 'Abuja'
        vendor.save()
        vendor.refresh_from_db()
        self.assertEqual(vendor.slug, original_slug)


class PublicStorefrontSecurityTests(VendorQABase):
    def test_public_serializer_never_leaks_sensitive_fields(self):
        vendor = self.make_vendor(
            store_name='Secretive Styles',
            nin_number='12345678901',
            cac_number='RC999999',
        )
        BankAccount.objects.create(
            vendor=vendor,
            account_name='Ada Okonkwo',
            account_number='0123456789',
            bank_name='GTBank',
            bank_code='058',
            recipient_code='RCP_SECRET_123',
        )
        res = APIClient().get(reverse('vendor-detail', kwargs={'slug': vendor.slug}))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = res.data['vendor']
        for sensitive in ('bank_account', 'nin_number', 'cac_number', 'recipient_code', 'user', 'email'):
            self.assertNotIn(sensitive, body)

    def test_nonexistent_storefront_slug_returns_404(self):
        res = APIClient().get(reverse('vendor-detail', kwargs={'slug': 'no-such-store'}))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(res.data['success'])

    def test_private_profile_serializer_contains_owner_fields_but_me_summary_is_safe(self):
        vendor = self.make_vendor(store_name='Owner Eyes Only', nin_number='12345678901')
        me = self.client.get(self.me_url).data
        # /me/ profile summary must not leak NIN
        self.assertNotIn('nin_number', me['user']['vendor_profile'])
        # The private serializer (used in the registration response) includes NIN for the owner
        self.assertIn('nin_number', VendorProfileSerializer(vendor).data)


class BankAccountPermissionTests(VendorQABase):
    def test_suspended_vendor_blocked_from_bank_account_endpoint(self):
        self.make_vendor(store_name='Suspended Styles', status_value=VendorStatus.SUSPENDED)
        res_get = self.client.get(self.bank_url)
        self.assertEqual(res_get.status_code, status.HTTP_403_FORBIDDEN)
        res_post = self.client.post(self.bank_url, {
            'account_name': 'Ada Okonkwo', 'account_number': '0123456789',
            'bank_name': 'GTBank', 'bank_code': '058',
        }, format='json')
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)

    def test_rejected_vendor_blocked_from_bank_account_endpoint(self):
        self.make_vendor(store_name='Rejected Styles', status_value=VendorStatus.REJECTED)
        self.assertEqual(self.client.get(self.bank_url).status_code, status.HTTP_403_FORBIDDEN)

    def test_bank_account_post_requires_all_fields(self):
        self.make_vendor(store_name='Complete Store')
        partial = {'account_name': 'Ada Okonkwo', 'account_number': '0123456789'}
        res = self.client.post(self.bank_url, partial, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bank_account_post_validates_account_number(self):
        self.make_vendor(store_name='Validated Store')
        res = self.client.post(self.bank_url, {
            'account_name': 'Ada Okonkwo',
            'account_number': 'abcdefghij',
            'bank_name': 'GTBank',
            'bank_code': '058',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bank_account_update_is_upsert_not_duplicate(self):
        self.make_vendor(store_name='Upsert Store')
        payload = {'account_name': 'Ada Okonkwo', 'account_number': '0123456789', 'bank_name': 'GTBank', 'bank_code': '058'}
        self.client.post(self.bank_url, payload, format='json')
        payload['bank_name'] = 'Zenith Bank'
        self.client.post(self.bank_url, payload, format='json')
        self.assertEqual(BankAccount.objects.filter(vendor__store_name='Upsert Store').count(), 1)


class MeRouteAliasTests(VendorQABase):
    """QA regression: PRD/sprint guides specify GET /api/v1/me/ (fixed 2026-08-11)."""

    def test_me_alias_and_canonical_route_return_identical_data(self):
        self.make_vendor(store_name='Route Check Styles')
        alias = self.client.get('/api/v1/me/')
        canonical = self.client.get('/api/v1/auth/me/')
        self.assertEqual(alias.status_code, status.HTTP_200_OK)
        self.assertEqual(canonical.status_code, status.HTTP_200_OK)
        self.assertEqual(alias.data, canonical.data)
        self.assertTrue(alias.data['user']['is_vendor'])

    def test_me_alias_requires_authentication(self):
        res = APIClient().get('/api/v1/me/')
        self.assertIn(res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class CSRFEnforcementTests(VendorQABase):
    """Verifies CSRF protection is actually enforced on session-authenticated POSTs."""

    def test_vendor_registration_without_csrf_token_rejected(self):
        csrf_client = APIClient(enforce_csrf_checks=True)

        # Obtain CSRF cookie
        csrf_res = csrf_client.get(reverse('csrf-token'))
        self.assertEqual(csrf_res.status_code, status.HTTP_200_OK)
        csrf_token = csrf_client.cookies['csrftoken'].value

        # Real session registration (sets sessionid cookie)
        reg_res = csrf_client.post(
            reverse('auth-register'),
            {'email': 'csrf.user@example.com', 'password': 'Password123!', 'first_name': 'C', 'last_name': 'S'},
            format='json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(reg_res.status_code, status.HTTP_201_CREATED)
        self.assertIn('sessionid', csrf_client.cookies)

        # POST without CSRF header must be rejected
        res_no_csrf = csrf_client.post(self.register_url, {'store_name': 'No CSRF Store', 'city': 'Lagos', 'state': 'Lagos'}, format='json')
        self.assertEqual(res_no_csrf.status_code, status.HTTP_403_FORBIDDEN)

        # Same POST with CSRF header succeeds
        res_with_csrf = csrf_client.post(
            self.register_url,
            {'store_name': 'With CSRF Store', 'city': 'Lagos', 'state': 'Lagos'},
            format='json',
            HTTP_X_CSRFTOKEN=csrf_client.cookies['csrftoken'].value,
        )
        self.assertEqual(res_with_csrf.status_code, status.HTTP_201_CREATED)
