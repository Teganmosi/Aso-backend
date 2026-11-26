"""Who a piece is for, the size guide for that piece, designer charts, and "Did it fit?"."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.orders.models import Order, OrderItem, OrderStatus
from apps.products.models import Category, FitFeedback, Product, ProductStatus, ProductVariant
from apps.products.sizing import clean_designer_chart, detect_wearer, typical_rows
from apps.vendors.models import VendorProfile, VendorStatus


class WearerTests(TestCase):
    def test_department_decides(self):
        self.assertEqual(detect_wearer('Royal Kaftan', 'Senator Suits', 'senator-suits', 'Men'), 'male')
        self.assertEqual(detect_wearer('Royal Kaftan', 'Boubou & Silk Kaftans', 'boubou', 'Women'), 'female')

    def test_title_decides_when_department_is_mixed(self):
        self.assertEqual(detect_wearer('Bridal Iro and Buba', 'Handwoven Aso Oke', 'handwoven-aso-oke', 'Traditional & Bridal'), 'female')
        self.assertEqual(detect_wearer('Groom Agbada Set', 'Handwoven Aso Oke', 'handwoven-aso-oke', 'Traditional & Bridal'), 'male')
        self.assertEqual(detect_wearer("Women's Agbada"), 'female')  # explicit word beats garment word

    def test_unknown_when_nothing_says(self):
        self.assertIsNone(detect_wearer('Aso Oke Set', 'Handwoven Aso Oke', 'handwoven-aso-oke', 'Traditional & Bridal'))


class SizeGuideTests(TestCase):
    def setUp(self):
        women = Category.objects.create(name='Women', description='x')
        men = Category.objects.create(name='Men', description='x')
        self.gowns = Category.objects.create(name='Aso Ebi & Corset Gowns', description='x', parent=women)
        self.senator = Category.objects.create(name='Senator Suits', description='x', parent=men)
        u = User.objects.create_user(email='d@aso.test', password='x')
        self.vendor = VendorProfile.objects.create(user=u, store_name='S', city='I', state='L',
                                                   status=VendorStatus.APPROVED)

    def make(self, title, cat, sizes, chart=None):
        p = Product.objects.create(vendor=self.vendor, category=cat, title=title, description='x',
                                   base_price_kobo=1000, status=ProductStatus.PUBLISHED, size_chart=chart or {})
        for s in sizes:
            ProductVariant.objects.create(product=p, size=s, stock_quantity=3)
        return p

    def detail(self, p):
        return APIClient().get(f'/api/v1/products/{p.slug}/').json()

    def test_gown_guide_is_for_women_with_underbust_and_only_sold_sizes(self):
        p = self.make('Lace Corset Gown', self.gowns, ['S', 'M', 'L', 'Bespoke Fit'])
        d = self.detail(p)
        d = d.get('product', d)
        self.assertEqual(d['wearer'], 'female')
        chart = d['size_chart']
        self.assertTrue(chart['is_generic'])
        self.assertEqual([r['size'] for r in chart['body_measurements']], ['S', 'M', 'L'])
        self.assertIn('underbust', chart['body_measurements'][0])
        self.assertEqual(chart['body_measurements'][1]['uk_size'], '12')
        self.assertEqual(chart['garment_measurements'], {})  # no invented product dimensions
        self.assertNotIn('height', chart['body_measurements'][0])

    def test_senator_guide_is_mens_with_neck(self):
        p = self.make('Classic Senator', self.senator, ['M', 'L', 'XL'])
        d = self.detail(p)
        d = d.get('product', d)
        row = d['size_chart']['body_measurements'][0]
        self.assertEqual(d['wearer'], 'male')
        self.assertIn('neck_collar', row)
        self.assertNotIn('uk_size', row)

    def test_ranges_meet_without_gaps(self):
        rows = typical_rows(['S', 'M', 'L'], 'female', 'full_set')
        self.assertEqual(rows[0]['bust'].split('-')[1], rows[1]['bust'].split('-')[0])

    def test_uk_number_sizes_are_understood(self):
        rows = typical_rows(['10', '12', '14'], 'female', 'corset_gown')
        self.assertEqual([r['size'] for r in rows], ['10', '12', '14'])

    def test_designer_chart_wins_and_is_checked(self):
        chart = clean_designer_chart({'stretch': 'SLIGHT', 'body_measurements': [
            {'size': 'M', 'bust': '36-38', 'waist': '30', 'hip': '40-42', 'length': '56'}]})
        self.assertEqual(chart['body_measurements'][0]['bust_cm'], '91-97')
        self.assertEqual(chart['garment_measurements']['tops'][0]['length'], '56')
        with self.assertRaises(ValueError):
            clean_designer_chart({'body_measurements': [{'size': 'M', 'bust': '92-97'}]})  # cm typed as inches
        with self.assertRaises(ValueError):
            clean_designer_chart({'body_measurements': [{'size': 'M', 'waist': '32-30'}]})
        p = self.make('Lace Corset Gown', self.gowns, ['M'], chart=chart)
        d = self.detail(p)
        self.assertFalse(d.get('product', d)['size_chart'].get('is_generic', False))

    def test_typical_endpoint_for_designers(self):
        res = APIClient().get('/api/v1/size-guide/typical/', {'category_id': str(self.gowns.id),
                                                             'title': 'Lace gown', 'sizes': 'S,M'}).json()
        self.assertEqual(res['wearer'], 'female')
        self.assertEqual(len(res['rows']), 2)


class DidItFitTests(TestCase):
    def setUp(self):
        self.shopper = User.objects.create_user(email='kemi@aso.test', password='x')
        u = User.objects.create_user(email='d@aso.test', password='x')
        vendor = VendorProfile.objects.create(user=u, store_name='S', city='I', state='L', status=VendorStatus.APPROVED)
        self.order = Order.objects.create(order_number='ASO-F-1', customer=self.shopper, vendor=vendor,
                                          order_status=OrderStatus.DELIVERED, subtotal_kobo=1, total_amount_kobo=1,
                                          payment_expires_at=timezone.now() + timedelta(hours=1),
                                          shipping_address_snapshot={'full_name': 'Kemi'})
        self.item = OrderItem.objects.create(order=self.order, product_title_snapshot='Gown', variant_size_snapshot='Bespoke Fit',
                                             sku_snapshot='X', unit_price_kobo=1, quantity=1, total_price_kobo=1,
                                             custom_measurements={'unit': 'IN', 'waist': '30', 'hips': '40',
                                                                  'estimated_fields': ['hips'],
                                                                  'fit_source': 'smart_estimator_v2'})
        self.url = f'/api/v1/orders/{self.order.id}/items/{self.item.id}/fit/'
        self.client = APIClient()

    def test_shopper_answers_and_can_change_their_answer(self):
        self.client.force_authenticate(self.shopper)
        res = self.client.post(self.url, {'result': 'TOO_SMALL', 'areas': ['hips', 'nonsense']}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        fb = FitFeedback.objects.get(order_item=self.item)
        self.assertEqual((fb.fit_result, fb.fit_source, fb.problem_areas), ('TOO_SMALL', 'estimate', ['hips']))
        self.assertEqual(fb.estimated_measurements, {'hips': '40'})
        self.client.post(self.url, {'result': 'GREAT'}, format='json')
        self.assertEqual(FitFeedback.objects.filter(order_item=self.item).count(), 1)
        order = self.client.get(f'/api/v1/orders/{self.order.id}/').json()
        order = order.get('data', order.get('order', order))
        self.assertEqual(order['items'][0]['fit_feedback'], 'GREAT')

    def test_only_after_delivery_and_only_your_order(self):
        Order.objects.filter(pk=self.order.pk).update(order_status=OrderStatus.PREPARING)
        self.client.force_authenticate(self.shopper)
        self.assertEqual(self.client.post(self.url, {'result': 'GREAT'}, format='json').status_code, 400)
        Order.objects.filter(pk=self.order.pk).update(order_status=OrderStatus.DELIVERED)
        stranger = User.objects.create_user(email='x@aso.test', password='x')
        self.client.force_authenticate(stranger)
        self.assertEqual(self.client.post(self.url, {'result': 'GREAT'}, format='json').status_code, 404)

    def test_old_feedback_endpoint_needs_login(self):
        res = APIClient().post('/api/v1/fit/feedback/', {'final_measurements': {'waist': 30}}, format='json')
        self.assertIn(res.status_code, (401, 403))

    def test_admin_report(self):
        FitFeedback.objects.create(order_item=self.item, customer=self.shopper, fit_result='GREAT', fit_source='measured')
        staff = User.objects.create_superuser(email='ops@aso.test', password='x')
        c = APIClient()
        c.force_login(staff)
        res = c.get('/admin/products/fitfeedback/')
        self.assertContains(res, 'Fit success, last 90 days')
        self.assertContains(res, '100%')


class CutTests(TestCase):
    def test_name_beats_category(self):
        from apps.products.sizing import cut_for_text
        self.assertEqual(cut_for_text('Indigo Adire Gown', 'Agbada & Grand Native Sets'), 'corset_gown')
        self.assertEqual(cut_for_text('Royal Set', 'Agbada & Grand Native Sets'), 'tops_senator')
        self.assertEqual(cut_for_text('Classic Piece', 'Misc'), 'full_set')


class AccessoryTests(TestCase):
    def setUp(self):
        acc = Category.objects.create(name='Accessories', description='x')
        self.caps = Category.objects.create(name='Caps (Fila) & Headwear', description='x', parent=acc)
        self.beads = Category.objects.create(name='Coral Beads & Jewelry', description='x', parent=acc)
        men = Category.objects.create(name='Men', description='x')
        self.senator = Category.objects.create(name='Senator Suits', description='x', parent=men)
        u = User.objects.create_user(email='d@aso.test', password='x')
        self.vendor = VendorProfile.objects.create(user=u, store_name='S', city='I', state='L',
                                                   status=VendorStatus.APPROVED)

    def make(self, title, cat, sizes):
        p = Product.objects.create(vendor=self.vendor, category=cat, title=title, description='x',
                                   base_price_kobo=1000, status=ProductStatus.PUBLISHED)
        for s in sizes:
            ProductVariant.objects.create(product=p, size=s, stock_quantity=3)
        d = APIClient().get(f'/api/v1/products/{p.slug}/').json()
        return d.get('product', d)

    def test_kinds(self):
        from apps.products.sizing import fit_kind
        self.assertEqual(fit_kind('Velvet Fila', 'Caps (Fila) & Headwear', 'caps', 'Accessories'), 'headwear')
        self.assertEqual(fit_kind('Royal Set', 'Caps (Fila) & Headwear', 'caps', 'Accessories'), 'headwear')
        self.assertEqual(fit_kind('Benin Coral Necklace', 'Coral Beads & Jewelry', 'coral', 'Accessories'), 'one_size')
        self.assertEqual(fit_kind('Aso Oke Gele', 'Caps (Fila) & Headwear', 'caps', 'Accessories'), 'one_size')
        self.assertEqual(fit_kind('Embroidered Fila', 'Senator Suits', 'senator', 'Men'), 'headwear')
        self.assertEqual(fit_kind('Agbada with matching fila', 'Senator Suits', 'senator', 'Men'), 'clothing')
        self.assertEqual(fit_kind('Bridal Headdress', 'Misc', 'misc', ''), 'one_size')
        self.assertEqual(fit_kind('Classic Senator', 'Senator Suits', 'senator', 'Men'), 'clothing')

    def test_cap_guide_is_by_head(self):
        d = self.make('Velvet Fila', self.caps, ['S', 'M', 'L', 'Bespoke Fit'])
        self.assertEqual(d['fit_kind'], 'headwear')
        rows = d['size_chart']['body_measurements']
        self.assertEqual([r['size'] for r in rows], ['S', 'M', 'L'])
        self.assertEqual(set(rows[0]) - {'size'}, {'head', 'head_cm'})
        self.assertEqual(rows[0]['head'].split('-')[1], rows[1]['head'].split('-')[0])

    def test_beads_have_no_body_guide(self):
        d = self.make('Benin Coral Necklace', self.beads, ['Free Size'])
        self.assertEqual(d['fit_kind'], 'one_size')
        self.assertEqual(d['size_chart']['body_measurements'], [])

    def test_designer_head_chart_and_head_measurement(self):
        chart = clean_designer_chart({'body_measurements': [{'size': 'M', 'head': '22-22.75'}]})
        self.assertEqual(chart['body_measurements'][0]['head_cm'], '56-58')
        with self.assertRaises(ValueError):
            clean_designer_chart({'body_measurements': [{'size': 'M', 'head': '57'}]})  # cm typed as inches
        from apps.common.measurements import clean_measurements
        self.assertEqual(clean_measurements({'unit': 'IN', 'head': '22.5'})['head'], '22.5')

    def test_typical_endpoint_for_caps(self):
        res = APIClient().get('/api/v1/size-guide/typical/', {'category_id': str(self.caps.id),
                                                             'title': 'Velvet Fila', 'sizes': 'M,L'}).json()
        self.assertEqual((res['fit_kind'], res['columns']), ('headwear', ['head']))
        res = APIClient().get('/api/v1/size-guide/typical/', {'category_id': str(self.beads.id),
                                                             'title': 'Coral beads', 'sizes': 'M'}).json()
        self.assertEqual(res['rows'], [])
