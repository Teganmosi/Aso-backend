from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from apps.accounts.models import User
from apps.vendors.models import VendorProfile, VendorStatus
from apps.products.models import Category, Product, ProductVariant, ApprovalStatus, ProductStatus
from apps.cart.models import Cart, CartItem


class CartEngineTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Customer User
        self.customer = User.objects.create_user(
            email='customer@example.com',
            password='Password123!',
            first_name='Amina',
            last_name='Okoro',
            phone_number='+2348011111111'
        )

        # Vendor 1 User & Profile ("Lagos Luxe Native")
        self.vendor_user_1 = User.objects.create_user(
            email='vendor1@example.com',
            password='Password123!',
            first_name='Tunde',
            last_name='Ade',
            phone_number='+2348022222222'
        )
        self.vendor_1 = VendorProfile.objects.create(
            user=self.vendor_user_1,
            store_name='Lagos Luxe Native',
            slug='lagos-luxe-native',
            description='Luxury Nigerian traditional attire',
            city='Lagos',
            state='Lagos',
            status=VendorStatus.APPROVED
        )

        # Vendor 2 User & Profile ("Abuja Couture")
        self.vendor_user_2 = User.objects.create_user(
            email='vendor2@example.com',
            password='Password123!',
            first_name='Fatima',
            last_name='Bello',
            phone_number='+2348033333333'
        )
        self.vendor_2 = VendorProfile.objects.create(
            user=self.vendor_user_2,
            store_name='Abuja Couture',
            slug='abuja-couture',
            description='Bespoke northern couture',
            city='Abuja',
            state='FCT',
            status=VendorStatus.APPROVED
        )

        # Category
        self.category = Category.objects.create(
            name='Traditional Attire',
            slug='traditional-attire'
        )

        # Product 1 (Vendor 1)
        self.product_1 = Product.objects.create(
            vendor=self.vendor_1,
            category=self.category,
            title='Royal Silk Agbada',
            description='Handmade silk agbada set',
            base_price_kobo=7500000,  # N75,000
            approval_status=ApprovalStatus.APPROVED,
            status=ProductStatus.PUBLISHED
        )
        self.variant_1a = ProductVariant.objects.create(
            product=self.product_1,
            size='XL',
            color='Navy',
            sku='ASO-V1-P1-XL-NAVY',
            stock_quantity=5
        )
        self.variant_1b = ProductVariant.objects.create(
            product=self.product_1,
            size='L',
            color='Black',
            sku='ASO-V1-P1-L-BLACK',
            stock_quantity=3
        )

        # Product 2 (Vendor 2)
        self.product_2 = Product.objects.create(
            vendor=self.vendor_2,
            category=self.category,
            title='Embroidered Kaftan',
            description='Premium embroidered kaftan',
            base_price_kobo=5000000,  # N50,000
            approval_status=ApprovalStatus.APPROVED,
            status=ProductStatus.PUBLISHED
        )
        self.variant_2a = ProductVariant.objects.create(
            product=self.product_2,
            size='M',
            color='Red',
            sku='ASO-V2-P2-M-RED',
            stock_quantity=10
        )

        # Unapproved / Draft Product
        self.draft_product = Product.objects.create(
            vendor=self.vendor_1,
            category=self.category,
            title='Draft Senator Set',
            description='Draft item',
            base_price_kobo=3000000,
            approval_status=ApprovalStatus.PENDING,
            status=ProductStatus.DRAFT
        )
        self.draft_variant = ProductVariant.objects.create(
            product=self.draft_product,
            size='L',
            color='Blue',
            sku='ASO-DRAFT-L-BLUE',
            stock_quantity=10
        )

    def test_unauthenticated_cart_access_fails(self):
        response = self.client.get('/api/v1/cart/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_get_empty_cart(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get('/api/v1/cart/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertIsNone(data['vendor'])
        self.assertEqual(data['items'], [])
        self.assertEqual(data['subtotal_kobo'], 0)
        self.assertEqual(data['subtotal_naira'], 0.0)
        self.assertEqual(data['item_count'], 0)

    def test_add_item_to_cart_success(self):
        self.client.force_authenticate(user=self.customer)
        payload = {
            'variant_id': str(self.variant_1a.id),
            'quantity': 1
        }
        response = self.client.post('/api/v1/cart/items/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertIsNotNone(data['vendor'])
        self.assertEqual(data['vendor']['store_name'], 'Lagos Luxe Native')
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['subtotal_kobo'], 7500000)
        self.assertEqual(data['subtotal_naira'], 75000.0)
        self.assertEqual(data['item_count'], 1)

    def test_add_same_variant_updates_quantity(self):
        self.client.force_authenticate(user=self.customer)
        payload = {
            'variant_id': str(self.variant_1a.id),
            'quantity': 1
        }
        self.client.post('/api/v1/cart/items/', data=payload, format='json')
        response = self.client.post('/api/v1/cart/items/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['quantity'], 2)
        self.assertEqual(data['subtotal_kobo'], 15000000)
        self.assertEqual(data['subtotal_naira'], 150000.0)
        self.assertEqual(data['item_count'], 2)

    def test_single_vendor_enforcement(self):
        """
        Attempting to add a variant from Designer B when cart has item from Designer A
        must fail with 400 Bad Request and exact error message.
        """
        self.client.force_authenticate(user=self.customer)
        # Add Designer A product
        self.client.post('/api/v1/cart/items/', data={'variant_id': str(self.variant_1a.id), 'quantity': 1}, format='json')

        # Attempt to add Designer B product
        payload = {
            'variant_id': str(self.variant_2a.id),
            'quantity': 1
        }
        response = self.client.post('/api/v1/cart/items/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error_msg = response.data.get('detail') or str(response.data)
        self.assertIn("Your cart already contains items from Lagos Luxe Native. Checkout or clear cart before adding items from another designer.", error_msg)

    def test_add_item_exceeding_stock_fails(self):
        self.client.force_authenticate(user=self.customer)
        payload = {
            'variant_id': str(self.variant_1a.id),
            'quantity': 10  # stock is 5
        }
        response = self.client.post('/api/v1/cart/items/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_unapproved_product_variant_fails(self):
        self.client.force_authenticate(user=self.customer)
        payload = {
            'variant_id': str(self.draft_variant.id),
            'quantity': 1
        }
        response = self.client.post('/api/v1/cart/items/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_item_quantity(self):
        self.client.force_authenticate(user=self.customer)
        res = self.client.post('/api/v1/cart/items/', data={'variant_id': str(self.variant_1a.id), 'quantity': 1}, format='json')
        item_id = res.data['data']['items'][0]['id']

        response = self.client.patch(f'/api/v1/cart/items/{item_id}/', data={'quantity': 3}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['items'][0]['quantity'], 3)
        self.assertEqual(data['subtotal_kobo'], 7500000 * 3)
        self.assertEqual(data['subtotal_naira'], 75000.0 * 3)
        self.assertEqual(data['item_count'], 3)

    def test_update_item_quantity_exceeding_stock_fails(self):
        self.client.force_authenticate(user=self.customer)
        res = self.client.post('/api/v1/cart/items/', data={'variant_id': str(self.variant_1a.id), 'quantity': 1}, format='json')
        item_id = res.data['data']['items'][0]['id']

        # stock is 5, attempt to patch quantity to 999
        response = self.client.patch(f'/api/v1/cart/items/{item_id}/', data={'quantity': 999}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_item_quantity_to_zero_removes_item(self):
        self.client.force_authenticate(user=self.customer)
        res = self.client.post('/api/v1/cart/items/', data={'variant_id': str(self.variant_1a.id), 'quantity': 1}, format='json')
        item_id = res.data['data']['items'][0]['id']

        response = self.client.patch(f'/api/v1/cart/items/{item_id}/', data={'quantity': 0}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['items'], [])
        self.assertIsNone(data['vendor'])
        self.assertEqual(data['subtotal_kobo'], 0)
        self.assertEqual(data['item_count'], 0)

    def test_remove_item_from_cart(self):
        self.client.force_authenticate(user=self.customer)
        res = self.client.post('/api/v1/cart/items/', data={'variant_id': str(self.variant_1a.id), 'quantity': 1}, format='json')
        item_id = res.data['data']['items'][0]['id']

        response = self.client.delete(f'/api/v1/cart/items/{item_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['items'], [])
        self.assertIsNone(data['vendor'])

    def test_clear_cart(self):
        self.client.force_authenticate(user=self.customer)
        self.client.post('/api/v1/cart/items/', data={'variant_id': str(self.variant_1a.id), 'quantity': 1}, format='json')
        self.client.post('/api/v1/cart/items/', data={'variant_id': str(self.variant_1b.id), 'quantity': 2}, format='json')

        response = self.client.delete('/api/v1/cart/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        self.assertEqual(data['items'], [])
        self.assertIsNone(data['vendor'])
        self.assertEqual(data['subtotal_kobo'], 0)
        self.assertEqual(data['item_count'], 0)
