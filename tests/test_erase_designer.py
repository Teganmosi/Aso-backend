"""Erasing a designer's personal data works even when their studio has orders (which can't be deleted)."""
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.orders.models import Order, OrderItem, OrderStatus
from apps.products.models import Category, Product, ProductMedia, ProductStatus
from apps.vendors.models import BankAccount, VendorProfile, VendorStatus


class EraseDesignerTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser(email='ops@aso.test', password='x')
        self.designer = User.objects.create_user(email='arike@example.com', password='x', first_name='Arike',
                                                 last_name='O', phone_number='+2348031112222')
        self.vendor = VendorProfile.objects.create(
            user=self.designer, store_name='Arike Styles', city='Yaba', state='Lagos', status=VendorStatus.APPROVED,
            instagram_handle='arikestyles', nin_number='12345678901', workshop_address='5 Herbert Macaulay',
            logo_url='/media/vendors/x/logo.webp', is_featured=True)
        BankAccount.objects.create(vendor=self.vendor, account_name='Arike O', account_number='0123456789',
                                   bank_name='GTBank', bank_code='058')
        Address.objects.create(user=self.designer, full_name='Arike O', phone_number='08031112222',
                               street_address='5 Herbert Macaulay', city='Yaba', state='Lagos')
        self.product = Product.objects.create(
            vendor=self.vendor, category=Category.objects.create(name='Gowns', description='x'),
            title='Arike Signature Gown', description='Her design', base_price_kobo=5_000_000,
            status=ProductStatus.PUBLISHED)
        ProductMedia.objects.create(product=self.product, url='/media/vendors/x/a.webp', is_primary=True)
        shopper = User.objects.create_user(email='kemi@aso.test', password='x')
        self.order = Order.objects.create(
            order_number='ASO-T-1', customer=shopper, vendor=self.vendor, order_status=OrderStatus.CANCELLED,
            subtotal_kobo=5_000_000, total_amount_kobo=5_000_000, payment_expires_at=timezone.now() + timedelta(hours=1),
            shipping_address_snapshot={'full_name': 'Kemi'})
        OrderItem.objects.create(order=self.order, product_title_snapshot='Arike Signature Gown',
                                 variant_size_snapshot='M', sku_snapshot='X', unit_price_kobo=5_000_000,
                                 quantity=1, total_price_kobo=5_000_000)
        self.client.force_login(self.staff)

    def tearDown(self):
        cache.clear()

    def post_action(self, **extra):
        return self.client.post(reverse('admin:vendors_vendorprofile_changelist'), {
            'action': 'erase_personal_data', '_selected_action': [str(self.vendor.pk)], **extra})

    def test_confirmation_page_then_erase(self):
        page = self.post_action()
        self.assertContains(page, 'Arike Styles')
        self.assertContains(page, '1 order')
        # Without typing ERASE nothing happens.
        self.post_action(erase_confirmed='1', confirm_text='yes')
        self.vendor.refresh_from_db()
        self.assertEqual(self.vendor.store_name, 'Arike Styles')

        self.post_action(erase_confirmed='1', confirm_text='ERASE')
        self.vendor.refresh_from_db()
        self.designer.refresh_from_db()
        self.product.refresh_from_db()
        self.assertNotIn('Arike', self.vendor.store_name)
        self.assertIsNone(self.vendor.nin_number)
        self.assertIsNone(self.vendor.instagram_handle)
        self.assertIsNone(self.vendor.logo_url)
        self.assertFalse(self.vendor.is_featured)
        self.assertEqual(self.vendor.status, VendorStatus.SUSPENDED)
        self.assertFalse(BankAccount.objects.filter(vendor=self.vendor).exists())
        self.assertFalse(Address.objects.filter(user=self.designer).exists())
        self.assertEqual(self.designer.first_name, '')
        self.assertIsNone(self.designer.phone_number)
        self.assertFalse(self.designer.is_active)
        self.assertFalse(self.designer.has_usable_password())
        self.assertTrue(self.designer.email.endswith('@erased.invalid'))
        self.assertFalse(self.product.is_active)
        self.assertNotIn('Arike', self.product.title)
        self.assertFalse(ProductMedia.objects.filter(product=self.product).exists())
        # The order and what was bought are kept for the accounts.
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())
        self.assertEqual(self.order.items.first().product_title_snapshot, 'Arike Signature Gown')
        # Her real email is free to sign up again.
        self.assertFalse(User.objects.filter(email='arike@example.com').exists())
        # Gone from the public site.
        self.assertNotIn('Arike', self.client.get('/api/v1/vendors/').content.decode())

    def test_warns_when_a_paid_order_is_still_open(self):
        Order.objects.filter(pk=self.order.pk).update(order_status=OrderStatus.PAID)
        self.assertContains(self.post_action(), 'paid or in progress')
