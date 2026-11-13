"""Public designer directory only lists studios with at least one live product."""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.products.models import ApprovalStatus, Category, Product, ProductStatus
from apps.vendors.models import VendorProfile, VendorStatus


class VendorDirectoryTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Men', description='m')

    def make_vendor(self, name):
        user = User.objects.create_user(email=f'{name.lower().replace(" ", "")}@dir.test', password='Password123!')
        return VendorProfile.objects.create(user=user, store_name=name, city='Lagos', state='Lagos',
                                            status=VendorStatus.APPROVED)

    def make_product(self, vendor, price, approval=ApprovalStatus.APPROVED):
        return Product.objects.create(vendor=vendor, category=self.category, title=f'{vendor.store_name} piece {price}',
                                      description='d', base_price_kobo=price, approval_status=approval,
                                      status=ProductStatus.PUBLISHED)

    def test_directory_hides_empty_and_pending_only_studios(self):
        live = self.make_vendor('Live Studio')
        self.make_product(live, 5000000)
        self.make_vendor('Empty Studio')
        pending_only = self.make_vendor('Pending Studio')
        self.make_product(pending_only, 100000, approval=ApprovalStatus.PENDING)

        names = [v['store_name'] for v in APIClient().get('/api/v1/vendors/').data]
        self.assertEqual(names, ['Live Studio'])

        # Empty studios are still reachable by direct link.
        self.assertEqual(APIClient().get('/api/v1/vendors/empty-studio/').status_code, 200)

    def test_starting_price_ignores_pending_products(self):
        studio = self.make_vendor('Price Studio')
        self.make_product(studio, 9000000)
        self.make_product(studio, 100000, approval=ApprovalStatus.PENDING)  # cheaper, but not live
        card = APIClient().get('/api/v1/vendors/').data[0]
        self.assertEqual(card['product_count'], 1)
        self.assertEqual(card['starting_price_naira'], 90000.0)
