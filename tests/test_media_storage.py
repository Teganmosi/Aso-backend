"""
Local media storage: image uploads, serving, inline-image rejection and the
legacy data: URI migration (apps/common/media_storage.py).
"""
import base64
import io
import shutil
import tempfile

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.products.models import ApprovalStatus, Category, Product, ProductMedia, ProductStatus
from apps.vendors.models import VendorProfile, VendorStatus


def make_jpeg(width=2400, height=3200, color=(120, 40, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', (width, height), color).save(buf, format='JPEG', quality=95)
    return buf.getvalue()


def jpeg_upload(name='photo.jpg', **kwargs):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, make_jpeg(**kwargs), content_type='image/jpeg')


class MediaStorageTestBase(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.client = APIClient()

        self.category = Category.objects.create(name='Women', description='Womenswear')
        self.vendor_user = User.objects.create_user(
            email='designer@aso.test', password='Password123!', phone_number='+2348011110000')
        self.vendor = VendorProfile.objects.create(
            user=self.vendor_user, store_name='Adire House', city='Lagos', state='Lagos',
            status=VendorStatus.APPROVED)
        self.other_user = User.objects.create_user(
            email='other@aso.test', password='Password123!', phone_number='+2348011110001')
        self.other_vendor = VendorProfile.objects.create(
            user=self.other_user, store_name='Other House', city='Abuja', state='FCT',
            status=VendorStatus.APPROVED)
        self.customer = User.objects.create_user(
            email='shopper@aso.test', password='Password123!', phone_number='+2348011110002')
        self.product = Product.objects.create(
            vendor=self.vendor, category=self.category, title='Indigo Gown',
            description='Hand-dyed', base_price_kobo=5000000, preparation_time_days=5,
            approval_status=ApprovalStatus.APPROVED, status=ProductStatus.PUBLISHED)

    def tearDown(self):
        # These tests hit cached public lists; don't leak cached responses into
        # later test modules (the test cache is shared across the whole run).
        cache.clear()
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def upload(self, user, kind='product', file=None):
        self.client.force_authenticate(user=user)
        return self.client.post('/api/v1/media/upload/',
                                {'file': file or jpeg_upload(), 'kind': kind}, format='multipart')


class ImageUploadTests(MediaStorageTestBase):
    def test_designer_upload_is_resized_webp_with_thumbnail(self):
        res = self.upload(self.vendor_user)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        url, thumb = res.data['url'], res.data['thumbnail_url']
        self.assertTrue(url.startswith(f'/media/vendors/{self.vendor.id}/products/'))
        self.assertTrue(url.endswith('.webp'))
        self.assertTrue(thumb.endswith('_thumb.webp'))

        full = Image.open(f'{self.media_root}/{url[len("/media/"):]}')
        small = Image.open(f'{self.media_root}/{thumb[len("/media/"):]}')
        self.assertEqual(full.format, 'WEBP')
        self.assertLessEqual(max(full.size), 1600)
        self.assertLessEqual(max(small.size), 480)

    def test_upload_requires_login(self):
        res = self.client.post('/api/v1/media/upload/', {'file': jpeg_upload(), 'kind': 'product'},
                               format='multipart')
        self.assertIn(res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_shopper_cannot_upload_product_photos(self):
        res = self.upload(self.customer, kind='product')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_logo_upload_allowed_before_vendor_profile_exists(self):
        res = self.upload(self.customer, kind='logo')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertTrue(res.data['url'].startswith(f'/media/users/{self.customer.id}/logo/'))
        self.assertIsNone(res.data['thumbnail_url'])

    def test_non_image_file_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake = SimpleUploadedFile('evil.jpg', b'<?php echo 1; ?>', content_type='image/jpeg')
        res = self.upload(self.vendor_user, file=fake)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_uploaded_file_is_served_with_long_cache(self):
        url = self.upload(self.vendor_user).data['url']
        self.client.force_authenticate(user=None)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertIn('immutable', res['Cache-Control'])
        # Path traversal out of MEDIA_ROOT must never serve a file (Django answers 400 or 404).
        self.assertIn(self.client.get('/media/../config/settings/base.py').status_code, (400, 404))


class InlineImageRejectionTests(MediaStorageTestBase):
    DATA_URI = 'data:image/jpeg;base64,' + base64.b64encode(make_jpeg(40, 40)).decode()

    def test_attaching_data_uri_media_is_rejected(self):
        self.client.force_authenticate(user=self.vendor_user)
        res = self.client.post(f'/api/v1/products/{self.product.id}/media/',
                               {'url': self.DATA_URI, 'is_primary': True}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ProductMedia.objects.filter(product=self.product).exists())

    def test_cannot_attach_another_designers_upload(self):
        other_url = self.upload(self.other_user).data['url']
        self.client.force_authenticate(user=self.vendor_user)
        res = self.client.post(f'/api/v1/products/{self.product.id}/media/',
                               {'url': other_url, 'is_primary': True}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_attach_a_users_logo_upload_as_product_photo(self):
        logo_url = self.upload(self.customer, kind='logo').data['url']  # /media/users/...
        self.client.force_authenticate(user=self.vendor_user)
        res = self.client.post(f'/api/v1/products/{self.product.id}/media/',
                               {'url': logo_url, 'is_primary': True}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_attached_upload_gets_thumbnail_and_list_uses_it(self):
        uploaded = self.upload(self.vendor_user).data
        self.client.force_authenticate(user=self.vendor_user)
        res = self.client.post(f'/api/v1/products/{self.product.id}/media/',
                               {'url': uploaded['url'], 'is_primary': True}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        media = ProductMedia.objects.get(product=self.product)
        self.assertEqual(media.thumbnail_url, uploaded['thumbnail_url'])

        self.client.force_authenticate(user=None)
        listing = self.client.get('/api/v1/products/')
        cards = {p['id']: p for p in listing.data['products']}
        self.assertEqual(cards[str(self.product.id)]['primary_image_url'], uploaded['thumbnail_url'])

    def test_vendor_logo_data_uri_is_rejected(self):
        self.client.force_authenticate(user=self.vendor_user)
        res = self.client.patch('/api/v1/vendors/profile/', {'logo_url': self.DATA_URI}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.vendor.refresh_from_db()
        self.assertFalse((self.vendor.logo_url or '').startswith('data:'))


class MigrateInlineImagesCommandTests(MediaStorageTestBase):
    def test_converts_inline_images_and_is_idempotent(self):
        data_uri = 'data:image/jpeg;base64,' + base64.b64encode(make_jpeg(1200, 1600)).decode()
        media = ProductMedia.objects.create(product=self.product, url=data_uri, is_primary=True)
        VendorProfile.objects.filter(id=self.vendor.id).update(logo_url=data_uri)
        broken = ProductMedia.objects.create(product=self.product, url='data:image/jpeg;base64,!!!!')

        out = io.StringIO()
        call_command('migrate_inline_images', '--dry-run', stdout=out)
        media.refresh_from_db()
        self.assertTrue(media.url.startswith('data:'), 'dry run must not write')

        call_command('migrate_inline_images', stdout=out)
        media.refresh_from_db()
        self.vendor.refresh_from_db()
        broken.refresh_from_db()
        self.assertTrue(media.url.startswith(f'/media/vendors/{self.vendor.id}/products/'))
        self.assertTrue(media.thumbnail_url.endswith('_thumb.webp'))
        self.assertTrue(self.vendor.logo_url.startswith(f'/media/vendors/{self.vendor.id}/logo/'))
        self.assertTrue(broken.url.startswith('data:'), 'undecodable rows are left untouched')

        converted_url = media.url
        call_command('migrate_inline_images', stdout=out)
        media.refresh_from_db()
        self.assertEqual(media.url, converted_url)
