"""Designers adding several pieces in a row must never hit a server error (500)."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.products.models import Category, ProductVariant
from apps.vendors.models import VendorProfile, VendorStatus


class PieceUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='maker@aso.test', password='x')
        VendorProfile.objects.create(user=self.user, store_name='Maker', city='Ikeja', state='Lagos',
                                     status=VendorStatus.APPROVED)
        self.cat = Category.objects.create(name='Gowns', description='x')
        self.client = APIClient(raise_request_exception=False)
        self.client.force_authenticate(self.user)

    def create(self, title, sizes=('S', 'M', 'L'), colors=('Blue',)):
        return self.client.post('/api/v1/vendor/products/', {
            'title': title, 'category_id': str(self.cat.id), 'description': 'Lined, with a side zip.',
            'base_price_kobo': 5_000_000, 'sizes': list(sizes), 'colors': list(colors), 'status': 'PUBLISHED',
        }, format='json')

    def test_pieces_with_similar_names(self):
        # Stock codes used to come from the first 14 letters of the name, so these collided.
        for title in ['Ankara Two-Piece Blue', 'Ankara Two-Piece Red', 'Ankara Two-Piece Green']:
            res = self.create(title)
            self.assertEqual(res.status_code, 201, f'{title}: {res.status_code} {getattr(res, "data", "")}')
        self.assertEqual(ProductVariant.objects.count(), 9)

    def test_same_name_three_times(self):
        for _ in range(3):
            self.assertEqual(self.create('Signature Kaftan').status_code, 201)

    def test_sizes_that_look_alike(self):
        # 'XL' / 'XL ' / 'xl' and long custom sizes cut to the same few letters.
        res = self.create('Bridal Set', sizes=('Size 10 Petite', 'Size 10 Petite Long', 'XL', 'xl'))
        self.assertEqual(res.status_code, 201, getattr(res, 'data', ''))

    def test_colours_that_look_alike(self):
        res = self.create('Party Gown', colors=('Royal Blue', 'Royal Blush', 'Gold'))
        self.assertEqual(res.status_code, 201, getattr(res, 'data', ''))

    def test_editing_sizes_on_two_similar_pieces(self):
        a = self.create('Ankara Two-Piece Blue').data['product']['id']
        b = self.create('Ankara Two-Piece Red').data['product']['id']
        for pid in (a, b):
            res = self.client.patch(f'/api/v1/vendor/products/{pid}/', {'sizes': ['XL', 'XXL'], 'colors': ['Gold']},
                                    format='json')
            self.assertEqual(res.status_code, 200, getattr(res, 'data', ''))
