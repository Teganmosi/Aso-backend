"""Fit estimator v2 and the measurement checks that protect designers' cut sheets."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import CustomerProfile, User
from apps.common.measurements import clean_measurements
from apps.orders.models import MessageType, Order, OrderItem, OrderMessage, OrderStatus
from apps.products.fit_intelligence import calculate_fit_estimate
from apps.products.models import Category, Product, ProductStatus, ProductVariant
from apps.vendors.models import VendorProfile, VendorStatus


class EstimatorTests(TestCase):
    def test_women_and_men_get_different_tables(self):
        woman = calculate_fit_estimate(category='corset_gown', rtw_size='M', height_inches=64, sex='female')
        man = calculate_fit_estimate(category='tops_senator', rtw_size='M', height_inches=70, sex='male')
        self.assertLess(woman['measurements']['chest_bust'], man['measurements']['chest_bust'])
        self.assertGreater(woman['measurements']['hips'], woman['measurements']['waist'])
        self.assertNotIn('underbust', man['measurements'])

    def test_underbust_is_bigger_than_waist_and_smaller_than_bust(self):
        for size in ('XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL'):
            m = calculate_fit_estimate(category='corset_gown', rtw_size=size, sex='female')['measurements']
            self.assertLess(m['underbust'], m['chest_bust'], size)
            # Most women: underbust above waist. At plus sizes the waist catches up.
            if size in ('XS', 'S', 'M', 'L', 'XL'):
                self.assertGreater(m['underbust'], m['waist'], size)
            else:
                self.assertGreaterEqual(m['underbust'] + 1, m['waist'], size)

    def test_sizes_go_up_and_height_changes_lengths(self):
        sizes = [calculate_fit_estimate(rtw_size=s, sex='male')['measurements']['chest_bust']
                 for s in ('S', 'M', 'L', 'XL', 'XXL', '3XL')]
        self.assertEqual(sizes, sorted(sizes))
        short = calculate_fit_estimate(height_inches=64, sex='male')['measurements']
        tall = calculate_fit_estimate(height_inches=76, sex='male')['measurements']
        for key in ('sleeve_length', 'trouser_length', 'top_length', 'inseam'):
            self.assertGreater(tall[key], short[key], key)

    def test_ranges_are_honest_and_labelled_as_a_rough_guide(self):
        res = calculate_fit_estimate(rtw_size='L', sex='male')
        self.assertEqual(res['confidence_tier'], 'low')
        self.assertIn('tape measure', res['confidence_label'])
        waist = res['estimated_ranges']['waist']
        self.assertGreaterEqual(waist['max'] - waist['min'], 6)  # ±3 inches, not a false ±1
        self.assertNotIn('Calibrated', str(res))

    def test_numbers_the_shopper_gives_are_kept(self):
        res = calculate_fit_estimate(rtw_size='L', sex='male', known_measurements={'waist': 38})
        self.assertEqual(res['measurements']['waist'], 38)
        self.assertNotIn('waist', res['estimated_fields'])

    def test_api_accepts_sex(self):
        res = APIClient().post('/api/v1/fit/estimate/', {'rtw_size': 'M', 'sex': 'female', 'height_inches': 64,
                                                         'category': 'corset_gown'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['data']['input_profile']['sex'], 'female')


class MeasurementCheckTests(TestCase):
    def test_typo_is_rejected(self):
        with self.assertRaises(ValidationError) as cm:
            clean_measurements({'unit': 'IN', 'waist': '340'})
        self.assertIn('Waist', str(cm.exception))

    def test_centimetres_typed_as_inches_is_caught(self):
        with self.assertRaises(ValidationError) as cm:
            clean_measurements({'unit': 'IN', 'chest_bust': '96'})
        self.assertIn('centimetres', str(cm.exception))

    def test_centimetres_are_accepted_in_cm_mode(self):
        self.assertEqual(clean_measurements({'unit': 'CM', 'chest_bust': '96'})['chest_bust'], '96')

    def test_swapped_fields_are_caught(self):
        with self.assertRaises(ValidationError):
            clean_measurements({'unit': 'IN', 'chest_bust': '30', 'underbust': '36'})
        with self.assertRaises(ValidationError):
            clean_measurements({'unit': 'IN', 'trouser_length': '30', 'inseam': '32'})

    def test_junk_is_dropped_and_notes_are_capped(self):
        clean = clean_measurements({'unit': 'IN', 'waist': '32', '<script>': 'x', 'notes': 'n' * 5000})
        self.assertNotIn('<script>', clean)
        self.assertEqual(len(clean['notes']), 1000)

    def test_text_is_not_a_number(self):
        with self.assertRaises(ValidationError):
            clean_measurements({'unit': 'IN', 'waist': 'thirty'})


class MeasurementFlowTests(TestCase):
    def setUp(self):
        self.shopper = User.objects.create_user(email='kemi@aso.test', password='x')
        designer = User.objects.create_user(email='d@aso.test', password='x')
        self.vendor = VendorProfile.objects.create(user=designer, store_name='S', city='I', state='L',
                                                   status=VendorStatus.APPROVED)
        self.designer = designer
        product = Product.objects.create(vendor=self.vendor, category=Category.objects.create(name='G', description='x'),
                                         title='Gown', description='x', base_price_kobo=5_000_000,
                                         status=ProductStatus.PUBLISHED)
        self.variant = ProductVariant.objects.create(product=product, size='M', stock_quantity=5)
        self.client = APIClient()

    def test_add_to_cart_rejects_impossible_measurements(self):
        self.client.force_authenticate(self.shopper)
        res = self.client.post('/api/v1/cart/items/', {'variant_id': str(self.variant.id), 'quantity': 1,
                                                       'custom_measurements': {'unit': 'IN', 'waist': '400'}},
                               format='json')
        self.assertEqual(res.status_code, 400)
        ok = self.client.post('/api/v1/cart/items/', {'variant_id': str(self.variant.id), 'quantity': 1,
                                                      'custom_measurements': {'unit': 'IN', 'waist': '32'}},
                              format='json')
        self.assertIn(ok.status_code, (200, 201), ok.data)

    def test_profile_never_keeps_estimated_numbers(self):
        self.client.force_authenticate(self.shopper)
        res = self.client.put('/api/v1/auth/profile/measurements/', {
            'unit': 'IN', 'waist': '32', 'hips': '42', 'fit_source': 'smart_estimator_v2',
            'estimated_fields': ['hips'], 'estimated_ranges': {'hips': {'min': 40, 'max': 44}},
        }, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        saved = CustomerProfile.objects.get(user=self.shopper).saved_measurements
        self.assertEqual(saved.get('waist'), '32')
        self.assertNotIn('hips', saved)
        self.assertNotIn('estimated_ranges', saved)

    def test_recheck_updates_the_right_piece_in_a_multi_piece_order(self):
        order = Order.objects.create(order_number='ASO-M-1', customer=self.shopper, vendor=self.vendor,
                                     order_status=OrderStatus.PAID, subtotal_kobo=1, total_amount_kobo=1,
                                     payment_expires_at=timezone.now() + timedelta(hours=1),
                                     shipping_address_snapshot={'full_name': 'Kemi'})
        common = dict(order=order, variant_size_snapshot='M', sku_snapshot='X', unit_price_kobo=1, quantity=1,
                      total_price_kobo=1)
        OrderItem.objects.create(product_title_snapshot='Cap', custom_measurements={}, **common)
        gown = OrderItem.objects.create(product_title_snapshot='Gown', custom_measurements={
            'unit': 'IN', 'waist': '30', 'fit_source': 'smart_estimator_v2', 'estimated_fields': ['waist']}, **common)

        self.client.force_authenticate(self.designer)
        req = self.client.post(f'/api/v1/orders/{order.id}/messages/action-request/',
                               {'measurement_key': 'waist', 'label': 'Waist'}, format='json')
        self.assertEqual(req.status_code, 201, req.data)
        msg = OrderMessage.objects.get(order=order, message_type=MessageType.ACTION_REQUEST)
        self.assertEqual(msg.action_payload['order_item_id'], str(gown.id))

        self.client.force_authenticate(self.shopper)
        bad = self.client.post(f'/api/v1/orders/{order.id}/messages/action-resolve/',
                               {'message_id': str(msg.id), 'measurement_key': 'waist', 'new_value': '320'},
                               format='json')
        self.assertEqual(bad.status_code, 400)
        res = self.client.post(f'/api/v1/orders/{order.id}/messages/action-resolve/',
                               {'message_id': str(msg.id), 'measurement_key': 'waist', 'new_value': '31.5'},
                               format='json')
        self.assertEqual(res.status_code, 200, res.data)
        gown.refresh_from_db()
        self.assertEqual(gown.custom_measurements['waist'], '31.5')
        self.assertEqual(gown.custom_measurements['estimated_fields'], [])  # now confirmed by the shopper
