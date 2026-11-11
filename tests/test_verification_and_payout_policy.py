"""
Launch policy (decided Nov 10, 2026):
  * Designers can open a studio and sell while unverified.
  * Submitting NIN/CAC sends the designer to an Aso admin for review; only an admin grants "Verified".
  * Unverified designers are blocked from withdrawing (server-side).
  * Every withdrawal waits for admin approval before any Paystack transfer is sent.
"""
from django.contrib.admin import helpers
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import User
from apps.payouts.models import PayoutRequest, PayoutStatus
from apps.payouts.services import get_or_create_vendor_balance, fail_payout, process_payout
from apps.vendors.models import BankAccount, VendorProfile, VendorStatus, VerificationStatus


class VerificationAndPayoutPolicyTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='policy.designer@example.com', password='Password123!', first_name='Bisi', last_name='Ade',
        )
        self.vendor = VendorProfile.objects.create(
            user=self.user, store_name='Bisi Couture', city='Lagos', state='Lagos', status=VendorStatus.APPROVED,
        )
        BankAccount.objects.create(
            vendor=self.vendor, account_name='Bisi Ade', account_number='0123456789',
            bank_name='GTBank', bank_code='058',
        )
        balance = get_or_create_vendor_balance(self.vendor)
        balance.available_balance_kobo = 5_000_000
        balance.save()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.withdraw_url = reverse('payout-withdraw')
        self.admin = User.objects.create_superuser(email='ops@example.com', password='AdminPass123!')
        self.admin_client = APIClient()
        self.admin_client.force_login(self.admin)

    def _verify(self):
        self.vendor.nin_number = '12345678901'
        self.vendor.save()
        self.admin_client.post('/admin/vendors/vendorprofile/', {
            'action': 'approve_identity_verification', helpers.ACTION_CHECKBOX_NAME: [str(self.vendor.pk)],
        })
        self.vendor.refresh_from_db()
        self.assertTrue(self.vendor.is_verified)

    # --- Verification --------------------------------------------------------------
    def test_new_designer_is_not_submitted_and_unverified(self):
        self.assertEqual(self.vendor.verification_status, VerificationStatus.NOT_SUBMITTED)
        self.assertFalse(self.vendor.is_verified)

    def test_designer_cannot_self_verify_via_profile_patch(self):
        res = self.client.patch('/api/v1/vendors/profile/', {
            'nin_number': '12345678901', 'is_verified': True, 'kyc_tier': 'TIER_3_ENTERPRISE',
            'verification_status': 'VERIFIED',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.vendor.refresh_from_db()
        self.assertFalse(self.vendor.is_verified)
        self.assertEqual(self.vendor.verification_status, VerificationStatus.PENDING_REVIEW)
        self.assertEqual(self.vendor.kyc_tier, 'TIER_1_STARTER')

    def test_invalid_nin_and_cac_rejected_on_profile_patch(self):
        self.assertEqual(self.client.patch('/api/v1/vendors/profile/', {'nin_number': 'abc'}, format='json').status_code,
                         status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.patch('/api/v1/vendors/profile/', {'cac_number': 'hello'}, format='json').status_code,
                         status.HTTP_400_BAD_REQUEST)

    @override_settings(VERIFICATION_REVIEW_EMAIL='designers@asomarketplace.com.ng',
                       EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_submission_alerts_admin_inbox(self):
        from django.core import mail
        self.client.patch('/api/v1/vendors/profile/', {'nin_number': '12345678901'}, format='json')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Bisi Couture', mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ['designers@asomarketplace.com.ng'])

    def test_rejection_reason_is_shown_to_designer_and_resubmission_requeues(self):
        self.client.patch('/api/v1/vendors/profile/', {'nin_number': '12345678901'}, format='json')
        self.vendor.refresh_from_db()
        self.vendor.verification_rejection_reason = 'Name on NIN does not match bank account'
        self.vendor.save(update_fields=['verification_rejection_reason'])
        self.admin_client.post('/admin/vendors/vendorprofile/', {
            'action': 'reject_identity_verification', helpers.ACTION_CHECKBOX_NAME: [str(self.vendor.pk)],
        })
        # Fresh user instance: force_authenticate would otherwise reuse a stale vendor_profile cache
        self.client.force_authenticate(user=User.objects.get(pk=self.user.pk))
        me = self.client.get(reverse('auth-me')).data
        vp = me.get('user', me)['vendor_profile']
        self.assertEqual(vp['verification_status'], 'REJECTED')
        self.assertIn('does not match', vp['verification_rejection_reason'])

        res = self.client.post('/api/v1/vendors/verify-kyc/', {}, format='json')  # resubmit same NIN
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.vendor.refresh_from_db()
        self.assertEqual(self.vendor.verification_status, VerificationStatus.PENDING_REVIEW)

    def test_changing_nin_after_verification_removes_badge(self):
        self._verify()
        self.client.patch('/api/v1/vendors/profile/', {'nin_number': '10987654321'}, format='json')
        self.vendor.refresh_from_db()
        self.assertFalse(self.vendor.is_verified)
        self.assertEqual(self.vendor.verification_status, VerificationStatus.PENDING_REVIEW)

    def test_saving_profile_with_unchanged_nin_keeps_badge(self):
        self._verify()
        self.client.patch('/api/v1/vendors/profile/', {'nin_number': '12345678901', 'description': 'New bio'},
                          format='json')
        self.vendor.refresh_from_db()
        self.assertTrue(self.vendor.is_verified)

    # --- Withdrawals ---------------------------------------------------------------
    def test_unverified_designer_cannot_withdraw(self):
        res = self.client.post(self.withdraw_url, {'amount_kobo': 1_000_000}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(PayoutRequest.objects.exists())

    def test_verified_withdrawal_waits_for_admin_approval(self):
        self._verify()
        res = self.client.post(self.withdraw_url, {'amount_kobo': 1_000_000}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        payout = PayoutRequest.objects.get()
        self.assertEqual(payout.status, PayoutStatus.PAYOUT_RESERVED)  # "Awaiting Admin Approval"
        self.assertFalse(payout.transfer_code)  # nothing sent to Paystack yet

        self.admin_client.post('/admin/payouts/payoutrequest/', {
            'action': 'approve_and_send_payouts', helpers.ACTION_CHECKBOX_NAME: [str(payout.pk)],
        })
        payout.refresh_from_db()
        self.assertEqual(payout.status, PayoutStatus.PROCESSING)
        self.assertTrue(payout.transfer_code)

    def test_admin_rejecting_payout_returns_funds_once(self):
        self._verify()
        self.client.post(self.withdraw_url, {'amount_kobo': 1_000_000}, format='json')
        payout = PayoutRequest.objects.get()
        self.admin_client.post('/admin/payouts/payoutrequest/', {
            'action': 'reject_payouts', helpers.ACTION_CHECKBOX_NAME: [str(payout.pk)],
        })
        fail_payout(payout, 'replayed transfer.failed webhook')  # must not credit twice
        balance = get_or_create_vendor_balance(self.vendor)
        balance.refresh_from_db()
        self.assertEqual(balance.available_balance_kobo, 5_000_000)
        self.assertEqual(balance.reserved_balance_kobo, 0)

    def test_failed_then_reversed_transfer_does_not_double_credit(self):
        """QA-06 regression: transfer.failed followed by transfer.reversed."""
        self._verify()
        self.client.post(self.withdraw_url, {'amount_kobo': 1_000_000}, format='json')
        payout = process_payout(PayoutRequest.objects.get())
        fail_payout(payout, 'transfer.failed')
        fail_payout(payout, 'transfer.reversed')
        balance = get_or_create_vendor_balance(self.vendor)
        balance.refresh_from_db()
        self.assertEqual(balance.available_balance_kobo, 5_000_000)
