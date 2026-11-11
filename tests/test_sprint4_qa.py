"""
QA Verification Suite - Sprint 4: Product Variants & Presigned S3/R2 Media Pipeline.

Covers the sprint.md verification guide flow plus adversarial edge cases:
- Presigned upload URL: MIME whitelist, vendor-scoped object key, real SigV4 signing
- Variant CRUD: auto-SKU, duplicate size/color guard, validation, ownership
- Media attach: primary handling, ownership boundary on storage URLs, ordering
- Public product detail by UUID or slug: gallery + active-variant matrix
- Permission boundaries, CSRF enforcement, non-UUID identifier safety
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.vendors.models import VendorProfile, VendorStatus
from apps.products.models import (
    Category, Product, ProductVariant, ProductMedia,
    ApprovalStatus, ProductStatus, MediaType
)


class Sprint4Base(TestCase):
    """Shared fixtures for Sprint 4 QA tests."""

    def setUp(self):
        self.men = Category.objects.create(name='Men')
        self.agbada = Category.objects.create(name='Agbada', parent=self.men)

        self.vendor_a_user = User.objects.create_user(
            email='vendor.a@qa.test', password='Password123!', first_name='Ada', last_name='A')
        self.vendor_a = VendorProfile.objects.create(
            user=self.vendor_a_user, store_name='Lagos Luxe QA', city='Lagos', state='Lagos',
            status=VendorStatus.APPROVED, is_verified=True)

        self.vendor_b_user = User.objects.create_user(
            email='vendor.b@qa.test', password='Password123!', first_name='Bola', last_name='B')
        self.vendor_b = VendorProfile.objects.create(
            user=self.vendor_b_user, store_name='Abuja Threads QA', city='Abuja', state='FCT',
            status=VendorStatus.APPROVED, is_verified=True)

        self.customer = User.objects.create_user(
            email='customer@qa.test', password='Password123!', first_name='Chidi', last_name='C')

        self.vendor_client = APIClient()
        self.vendor_client.force_authenticate(user=self.vendor_a_user)

        # Approved + published product owned by vendor A
        self.product = Product.objects.create(
            vendor=self.vendor_a, category=self.agbada, title='Royal Silk Agbada',
            description='Handmade silk agbada with gold embroidery', base_price_kobo=7500000,
            approval_status=ApprovalStatus.APPROVED, status=ProductStatus.PUBLISHED)

        self.upload_url = '/api/v1/products/upload-url/'
        self.variants_url = '/api/v1/products/%s/variants/' % self.product.id
        self.media_url = '/api/v1/products/%s/media/' % self.product.id
        self.public_detail_by_id = '/api/v1/products/%s/' % self.product.id
        self.public_detail_by_slug = '/api/v1/products/%s/' % self.product.slug


class SprintGuideFlowTests(Sprint4Base):
    """End-to-end walkthrough exactly as written in sprint.md Sprint 4 guide."""

    def test_full_guide_flow_presign_variants_media_public_detail(self):
        # Step 1: Presigned media upload request
        res = self.vendor_client.post(self.upload_url, {
            'filename': 'agbada.jpg', 'file_type': 'image/jpeg'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data['data']
        self.assertIn('X-Amz-Signature=', data['upload_url'])
        key_pattern = r'^vendors/%s/products/[0-9a-f-]{36}\.jpg$' % self.vendor_a.id
        self.assertRegex(data['object_key'], key_pattern)
        self.assertEqual(data['file_type'], 'image/jpeg')
        self.assertEqual(data['expires_in'], 3600)

        # Step 2: Variant creation (XL / Navy / 5 and L / Black / 3)
        v1 = self.vendor_client.post(self.variants_url, {
            'size': 'XL', 'color': 'Navy', 'stock_quantity': 5}, format='json')
        v2 = self.vendor_client.post(self.variants_url, {
            'size': 'L', 'color': 'Black', 'stock_quantity': 3}, format='json')
        self.assertEqual(v1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(v2.status_code, status.HTTP_201_CREATED)
        self.assertTrue(v1.data['variant']['sku'].startswith('ASO-'))
        self.assertTrue(v2.data['variant']['sku'].startswith('ASO-'))

        # Step 3: Attach uploaded media URL to the product
        media_res = self.vendor_client.post(self.media_url, {
            'media_type': 'IMAGE', 'url': data['public_url']}, format='json')
        self.assertEqual(media_res.status_code, status.HTTP_201_CREATED)

        # Step 4: GET /api/v1/products/{id}/ returns gallery + variant matrix
        detail = APIClient().get(self.public_detail_by_id)
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        body = detail.data['product']
        self.assertEqual(len(body['media']), 1)
        self.assertEqual(body['media'][0]['url'], data['public_url'])
        self.assertEqual(len(body['variants']), 2)
        sizes = {v['size'] for v in body['variants']}
        self.assertEqual(sizes, {'XL', 'L'})
        stocks = {v['size']: v['stock_quantity'] for v in body['variants']}
        self.assertEqual(stocks, {'XL': 5, 'L': 3})
        self.assertTrue(all(v['in_stock'] for v in body['variants']))


class PresignedUploadUrlTests(Sprint4Base):
    MIME_EXTENSION = {
        'image/jpeg': ('jpg', 10 * 1024 * 1024),
        'image/png': ('png', 10 * 1024 * 1024),
        'image/webp': ('webp', 10 * 1024 * 1024),
        'video/mp4': ('mp4', 50 * 1024 * 1024),
    }

    def test_each_allowed_mime_returns_correct_extension_and_limit(self):
        for mime, (ext, limit) in self.MIME_EXTENSION.items():
            res = self.vendor_client.post(self.upload_url, {
                'filename': 'asset.%s' % ext, 'file_type': mime}, format='json')
            self.assertEqual(res.status_code, status.HTTP_200_OK, msg=mime)
            data = res.data['data']
            self.assertTrue(data['object_key'].endswith('.%s' % ext), msg=mime)
            self.assertEqual(data['max_size_bytes'], limit, msg=mime)
            self.assertIn('X-Amz-Signature=', data['upload_url'], msg=mime)

    def test_disallowed_mime_types_rejected(self):
        for mime in ('application/pdf', 'image/gif', 'video/avi', 'image/svg+xml'):
            res = self.vendor_client.post(self.upload_url, {
                'filename': 'x', 'file_type': mime}, format='json')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg=mime)

    def test_missing_fields_rejected(self):
        self.assertEqual(
            self.vendor_client.post(self.upload_url, {}, format='json').status_code,
            status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self.vendor_client.post(self.upload_url, {'filename': 'a.jpg'}, format='json').status_code,
            status.HTTP_400_BAD_REQUEST)

    def test_permission_boundaries(self):
        payload = {'filename': 'a.jpg', 'file_type': 'image/jpeg'}
        # Anonymous
        self.assertEqual(APIClient().post(self.upload_url, payload, format='json').status_code,
                         status.HTTP_403_FORBIDDEN)
        # Customer without vendor profile
        customer_client = APIClient()
        customer_client.force_authenticate(user=self.customer)
        self.assertEqual(customer_client.post(self.upload_url, payload, format='json').status_code,
                         status.HTTP_403_FORBIDDEN)
        # Pending vendor
        pending_user = User.objects.create_user(
            email='pending@qa.test', password='Password123!', first_name='P', last_name='V')
        VendorProfile.objects.create(
            user=pending_user, store_name='Pending QA', city='Lagos', state='Lagos',
            status=VendorStatus.PENDING)
        pending_client = APIClient()
        pending_client.force_authenticate(user=pending_user)
        self.assertEqual(pending_client.post(self.upload_url, payload, format='json').status_code,
                         status.HTTP_403_FORBIDDEN)


class VariantManagementTests(Sprint4Base):
    def test_create_variant_generates_sku_and_echoes_price_fields(self):
        res = self.vendor_client.post(self.variants_url, {
            'size': 'XL', 'color': 'Navy', 'stock_quantity': 5}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        variant = res.data['variant']
        self.assertTrue(variant['sku'].startswith('ASO-'))
        # Shared base price when no override is supplied
        self.assertEqual(variant['price_kobo'], self.product.base_price_kobo)
        self.assertEqual(variant['price_naira'], 75000.0)
        self.assertTrue(variant['in_stock'])

    def test_price_override_takes_precedence_over_base_price(self):
        res = self.vendor_client.post(self.variants_url, {
            'size': 'XXL', 'color': 'Gold', 'stock_quantity': 1,
            'price_override_kobo': 9900000}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['variant']['price_kobo'], 9900000)
        self.assertEqual(res.data['variant']['price_naira'], 99000.0)

    def test_duplicate_size_color_rejected(self):
        payload = {'size': 'XL', 'color': 'Navy', 'stock_quantity': 5}
        self.assertEqual(self.vendor_client.post(self.variants_url, payload, format='json').status_code,
                         status.HTTP_201_CREATED)
        res = self.vendor_client.post(self.variants_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_cannot_bypass_duplicate_size_color_guard(self):
        """
        QA REGRESSION (bug found & fixed 2026-08-13): the (product, size, color)
        uniqueness guard was enforced on CREATE but not on UPDATE, so a PATCH that
        changed size/color could create a duplicate combination. The update path now
        re-validates uniqueness and must reject with 400.
        """
        r1 = self.vendor_client.post(self.variants_url, {'size': 'XL', 'color': 'Navy', 'stock_quantity': 5}, format='json')
        r2 = self.vendor_client.post(self.variants_url, {'size': 'L', 'color': 'Black', 'stock_quantity': 3}, format='json')
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)

        v2_id = r2.data['variant']['id']
        patch_res = self.vendor_client.patch(
            '/api/v1/products/%s/variants/%s/' % (self.product.id, v2_id),
            {'size': 'XL', 'color': 'Navy'}, format='json')
        self.assertEqual(patch_res.status_code, status.HTTP_400_BAD_REQUEST)

        # A non-conflicting update still succeeds
        ok_res = self.vendor_client.patch(
            '/api/v1/products/%s/variants/%s/' % (self.product.id, v2_id),
            {'size': 'M', 'color': 'Black'}, format='json')
        self.assertEqual(ok_res.status_code, status.HTTP_200_OK)

    def test_validation_failures(self):
        for payload in (
            {'size': '   ', 'stock_quantity': 1},          # blank size
            {'size': 'XL', 'stock_quantity': -5},           # negative stock
            {'size': 'XL', 'stock_quantity': 1, 'price_override_kobo': 0},  # free variant
        ):
            res = self.vendor_client.post(self.variants_url, payload, format='json')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg=str(payload))

    def test_list_get_patch_delete_lifecycle(self):
        created = self.vendor_client.post(self.variants_url, {
            'size': 'M', 'color': 'Black', 'stock_quantity': 2}, format='json').data['variant']
        variant_id = created['id']

        listing = self.vendor_client.get(self.variants_url)
        self.assertEqual(len(listing.data['variants']), 1)

        # Lookup works by id and by product slug
        by_id = self.vendor_client.get('/api/v1/products/%s/variants/%s/' % (self.product.id, variant_id))
        by_slug = self.vendor_client.get('/api/v1/products/%s/variants/%s/' % (self.product.slug, variant_id))
        self.assertEqual(by_id.status_code, status.HTTP_200_OK)
        self.assertEqual(by_slug.status_code, status.HTTP_200_OK)

        patch_res = self.vendor_client.patch(
            '/api/v1/products/%s/variants/%s/' % (self.product.id, variant_id),
            {'stock_quantity': 9}, format='json')
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data['variant']['stock_quantity'], 9)

        delete_res = self.vendor_client.delete(
            '/api/v1/products/%s/variants/%s/' % (self.product.id, variant_id))
        self.assertEqual(delete_res.status_code, status.HTTP_200_OK)
        self.assertEqual(ProductVariant.objects.filter(id=variant_id).count(), 0)
        self.assertEqual(
            self.vendor_client.get('/api/v1/products/%s/variants/%s/' % (self.product.id, variant_id)).status_code,
            status.HTTP_404_NOT_FOUND)

    def test_non_uuid_variant_identifier_returns_404_not_500(self):
        base = '/api/v1/products/%s/variants/not-a-uuid/' % self.product.id
        self.assertEqual(self.vendor_client.get(base).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.vendor_client.patch(base, {'stock_quantity': 1}, format='json').status_code,
                         status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.vendor_client.delete(base).status_code, status.HTTP_404_NOT_FOUND)

    def test_cross_vendor_and_non_vendor_boundaries(self):
        vendor_b_client = APIClient()
        vendor_b_client.force_authenticate(user=self.vendor_b_user)
        # Vendor B cannot list/create on vendor A's product
        self.assertEqual(vendor_b_client.get(self.variants_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(vendor_b_client.post(
            self.variants_url, {'size': 'XL', 'stock_quantity': 1}, format='json').status_code,
            status.HTTP_404_NOT_FOUND)
        # Customer gets 403
        customer_client = APIClient()
        customer_client.force_authenticate(user=self.customer)
        self.assertEqual(customer_client.get(self.variants_url).status_code, status.HTTP_403_FORBIDDEN)

    def test_in_stock_matrix_and_inactive_variant_hidden_publicly(self):
        ProductVariant.objects.create(product=self.product, size='XL', color='Navy', stock_quantity=5)
        ProductVariant.objects.create(product=self.product, size='S', color='Navy', stock_quantity=0)
        ProductVariant.objects.create(
            product=self.product, size='M', color='Navy', stock_quantity=7, is_active=False)

        detail = APIClient().get(self.public_detail_by_id).data['product']
        sizes = {v['size'] for v in detail['variants']}
        self.assertEqual(sizes, {'XL', 'S'})  # inactive M hidden from the public matrix
        stock_flags = {v['size']: v['in_stock'] for v in detail['variants']}
        self.assertEqual(stock_flags, {'XL': True, 'S': False})


class MediaManagementTests(Sprint4Base):
    def setUp(self):
        super().setUp()
        self.own_url = 'https://cdn.aso.ng/vendors/%s/products/hero.jpg' % self.vendor_a.id
        self.other_vendor_url = 'https://cdn.aso.ng/vendors/%s/products/stolen.jpg' % self.vendor_b.id

    def test_attach_first_media_auto_primary(self):
        res = self.vendor_client.post(self.media_url, {'media_type': 'IMAGE', 'url': self.own_url}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data['media']['is_primary'])

    def test_new_primary_demotes_existing(self):
        first = self.vendor_client.post(self.media_url, {
            'media_type': 'IMAGE', 'url': self.own_url}, format='json').data['media']
        self.assertTrue(first['is_primary'])

        second = self.vendor_client.post(self.media_url, {
            'media_type': 'IMAGE', 'url': self.own_url.replace('hero', 'second'),
            'is_primary': True}, format='json').data['media']
        self.assertTrue(second['is_primary'])

        self.assertFalse(ProductMedia.objects.get(id=first['id']).is_primary)
        self.assertEqual(ProductMedia.objects.filter(product=self.product, is_primary=True).count(), 1)

    def test_list_ordering_and_delete(self):
        self.vendor_client.post(self.media_url, {
            'media_type': 'IMAGE', 'url': self.own_url, 'display_order': 2}, format='json')
        self.vendor_client.post(self.media_url, {
            'media_type': 'IMAGE', 'url': self.own_url.replace('hero', 'b'), 'display_order': 1}, format='json')

        listing = self.vendor_client.get(self.media_url).data['media']
        self.assertEqual([m['display_order'] for m in listing], [1, 2])

        media_id = listing[0]['id']
        del_res = self.vendor_client.delete('/api/v1/products/%s/media/%s/' % (self.product.id, media_id))
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)
        self.assertEqual(ProductMedia.objects.filter(product=self.product).count(), 1)

    def test_non_uuid_media_identifier_returns_404_not_500(self):
        res = self.vendor_client.delete('/api/v1/products/%s/media/not-a-uuid/' % self.product.id)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_storage_url_ownership_boundary(self):
        # Own vendor namespace -> allowed
        res_own = self.vendor_client.post(self.media_url, {'media_type': 'IMAGE', 'url': self.own_url}, format='json')
        self.assertEqual(res_own.status_code, status.HTTP_201_CREATED)
        # Another vendor's storage path -> rejected
        res_other = self.vendor_client.post(self.media_url, {'media_type': 'IMAGE', 'url': self.other_vendor_url}, format='json')
        self.assertEqual(res_other.status_code, status.HTTP_400_BAD_REQUEST)
        # External URL -> allowed (no CDN lock-in yet)
        res_ext = self.vendor_client.post(self.media_url, {
            'media_type': 'IMAGE', 'url': 'https://external-cdn.example.com/photo.jpg'}, format='json')
        self.assertEqual(res_ext.status_code, status.HTTP_201_CREATED)

    def test_cross_vendor_and_non_vendor_boundaries(self):
        vendor_b_client = APIClient()
        vendor_b_client.force_authenticate(user=self.vendor_b_user)
        self.assertEqual(vendor_b_client.get(self.media_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(vendor_b_client.post(
            self.media_url, {'media_type': 'IMAGE', 'url': self.own_url}, format='json').status_code,
            status.HTTP_404_NOT_FOUND)
        customer_client = APIClient()
        customer_client.force_authenticate(user=self.customer)
        self.assertEqual(customer_client.get(self.media_url).status_code, status.HTTP_403_FORBIDDEN)


class PublicDetailTests(Sprint4Base):
    def test_detail_by_id_and_by_slug_return_same_product(self):
        by_id = APIClient().get(self.public_detail_by_id)
        by_slug = APIClient().get(self.public_detail_by_slug)
        self.assertEqual(by_id.status_code, status.HTTP_200_OK)
        self.assertEqual(by_slug.status_code, status.HTTP_200_OK)
        self.assertEqual(by_id.data['product']['id'], by_slug.data['product']['id'])

    def test_garbage_identifier_returns_404_not_500(self):
        res = APIClient().get('/api/v1/products/not-a-real-product/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(res.data['success'])

    def test_hidden_states_return_404(self):
        cases = [
            ('Pending Product', {'approval_status': ApprovalStatus.PENDING, 'status': ProductStatus.PUBLISHED}),
            ('Draft Product', {'approval_status': ApprovalStatus.APPROVED, 'status': ProductStatus.DRAFT}),
            ('Archived Product', {'approval_status': ApprovalStatus.APPROVED, 'status': ProductStatus.ARCHIVED}),
            ('Rejected Product', {'approval_status': ApprovalStatus.REJECTED, 'status': ProductStatus.PUBLISHED}),
            ('Deleted Product', {'approval_status': ApprovalStatus.APPROVED,
                                 'status': ProductStatus.PUBLISHED, 'is_active': False}),
        ]
        for title, overrides in cases:
            product = Product.objects.create(
                vendor=self.vendor_a, category=self.agbada, title=title,
                description='d', base_price_kobo=100000, **overrides)
            res = APIClient().get('/api/v1/products/%s/' % product.id)
            self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND, msg=title)

    def test_suspended_vendor_product_hidden(self):
        suspended_user = User.objects.create_user(
            email='susp@qa.test', password='Password123!', first_name='S', last_name='V')
        suspended_vendor = VendorProfile.objects.create(
            user=suspended_user, store_name='Suspended QA', city='Lagos', state='Lagos',
            status=VendorStatus.SUSPENDED)
        product = Product.objects.create(
            vendor=suspended_vendor, category=self.agbada, title='Suspended Vendor Product',
            description='d', base_price_kobo=100000,
            approval_status=ApprovalStatus.APPROVED, status=ProductStatus.PUBLISHED)
        self.assertEqual(APIClient().get('/api/v1/products/%s/' % product.id).status_code,
                         status.HTTP_404_NOT_FOUND)

    def test_gallery_and_variant_matrix_shape(self):
        ProductVariant.objects.create(product=self.product, size='XL', color='Navy', stock_quantity=5)
        ProductMedia.objects.create(product=self.product, media_type=MediaType.IMAGE,
                                    url='https://cdn.aso.ng/vendors/%s/products/a.jpg' % self.vendor_a.id,
                                    is_primary=True)
        ProductMedia.objects.create(product=self.product, media_type=MediaType.VIDEO,
                                    url='https://cdn.aso.ng/vendors/%s/products/v.mp4' % self.vendor_a.id,
                                    display_order=1)

        body = APIClient().get(self.public_detail_by_id).data['product']
        self.assertEqual(body['primary_image_url'], body['media'][0]['url'])
        media_fields = set(body['media'][0].keys())
        for field in ('id', 'media_type', 'url', 'display_order', 'is_primary'):
            self.assertIn(field, media_fields)
        variant_fields = set(body['variants'][0].keys())
        for field in ('id', 'size', 'color', 'sku', 'stock_quantity', 'in_stock', 'price_kobo'):
            self.assertIn(field, variant_fields)

    def test_list_serializer_primary_image_and_available_sizes(self):
        ProductVariant.objects.create(product=self.product, size='XL', color='Navy', stock_quantity=5)
        ProductVariant.objects.create(product=self.product, size='S', color='Navy', stock_quantity=0)
        ProductMedia.objects.create(product=self.product, media_type=MediaType.IMAGE,
                                    url='https://cdn.aso.ng/vendors/%s/products/cover.jpg' % self.vendor_a.id,
                                    is_primary=True)

        res = APIClient().get('/api/v1/products/?search=Royal Silk')
        self.assertEqual(res.data['count'], 1)
        item = res.data['products'][0]
        self.assertEqual(item['primary_image_url'],
                         'https://cdn.aso.ng/vendors/%s/products/cover.jpg' % self.vendor_a.id)
        self.assertEqual(item['available_sizes'], ['XL'])  # in-stock sizes only


class CSRFEnforcementTests(Sprint4Base):
    def test_upload_url_requires_csrf_on_session_auth(self):
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.get(reverse('csrf-token'))
        token = csrf_client.cookies['csrftoken'].value
        reg = csrf_client.post(reverse('auth-register'), {
            'email': 'csrf.vendor@qa.test', 'password': 'Password123!',
            'first_name': 'C', 'last_name': 'V'}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(reg.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email='csrf.vendor@qa.test')
        VendorProfile.objects.create(user=user, store_name='CSRF Vendor QA', city='Lagos',
                                     state='Lagos', status=VendorStatus.APPROVED)

        payload = {'filename': 'a.jpg', 'file_type': 'image/jpeg'}
        res_no_csrf = csrf_client.post(self.upload_url, payload, format='json')
        self.assertEqual(res_no_csrf.status_code, status.HTTP_403_FORBIDDEN)

        res_with_csrf = csrf_client.post(self.upload_url, payload, format='json',
                                         HTTP_X_CSRFTOKEN=csrf_client.cookies['csrftoken'].value)
        self.assertEqual(res_with_csrf.status_code, status.HTTP_200_OK)
