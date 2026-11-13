"""One spelling per Nigerian state, so same-state deliveries aren't quoted as interstate."""
from django.test import SimpleTestCase, TestCase

from apps.accounts.models import Address, User
from apps.common.nigeria import normalize_state, same_state
from apps.vendors.models import VendorProfile


class NormalizeStateTests(SimpleTestCase):
    def test_variants(self):
        self.assertEqual(normalize_state('Lagos State'), 'Lagos')
        self.assertEqual(normalize_state('  lagos  state '), 'Lagos')
        self.assertEqual(normalize_state('akwa ibom'), 'Akwa Ibom')
        self.assertEqual(normalize_state('FCT - Abuja'), 'Abuja (FCT)')
        self.assertEqual(normalize_state('Abuja'), 'Abuja (FCT)')
        self.assertEqual(normalize_state('Somewhere Else'), 'Somewhere Else')
        self.assertEqual(normalize_state(None), '')

    def test_same_state(self):
        self.assertTrue(same_state('Lagos State', 'lagos'))
        self.assertFalse(same_state('Lagos', 'Ogun State'))


class SavedStateTests(TestCase):
    def test_models_store_canonical_state(self):
        user = User.objects.create_user(email='s@aso.test', password='Password123!')
        vendor = VendorProfile.objects.create(user=user, store_name='S Studio', city='Ikeja', state='Lagos State')
        self.assertEqual(vendor.state, 'Lagos')
        addr = Address.objects.create(user=user, full_name='S', phone_number='08030000000',
                                      street_address='1 Road', city='Ikeja', state='lagos state')
        self.assertEqual(addr.state, 'Lagos')
