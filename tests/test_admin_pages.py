"""Every admin page opens for staff, shows the 'Needs your attention' panel and naira (not kobo)."""
from datetime import timedelta

from django.contrib import admin
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.orders.models import Order, OrderItem, OrderStatus
from apps.payouts.models import LedgerEntry, LedgerEntryType, PayoutRequest, PayoutStatus, VendorBalance
from apps.products.models import ApprovalStatus, Category, Product, ProductMedia, ProductStatus, ProductVariant
from apps.vendors.models import BankAccount, VendorProfile, VendorStatus, VerificationStatus


class AdminPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(email='ops@aso.test', password='Admin-Pass-2026', first_name='Ops')
        designer = User.objects.create_user(email='tolu@aso.test', password='x', first_name='Tolu', last_name='A',
                                            phone_number='+2348031234567')
        cls.vendor = VendorProfile.objects.create(user=designer, store_name='Tolu Couture', city='Surulere',
                                                  state='Lagos', status=VendorStatus.APPROVED, is_verified=True,
                                                  verification_status=VerificationStatus.PENDING_REVIEW)
        cls.bank = BankAccount.objects.create(vendor=cls.vendor, account_name='Tolu A', account_number='0123456789',
                                              bank_name='GTBank', bank_code='058')
        cat = Category.objects.create(name='Agbada', description='x')
        cls.product = Product.objects.create(vendor=cls.vendor, category=cat, title='Emerald Agbada', description='d',
                                             base_price_kobo=18_500_000, approval_status=ApprovalStatus.PENDING,
                                             status=ProductStatus.PUBLISHED)
        ProductMedia.objects.create(product=cls.product, url='/media/products/a.jpg', is_primary=True)
        variant = ProductVariant.objects.create(product=cls.product, size='L', sku='EA-L', stock_quantity=3)
        shopper = User.objects.create_user(email='kemi@aso.test', password='x', first_name='Kemi')
        Address.objects.create(user=shopper, full_name='Kemi', phone_number='08030000001',
                               street_address='1 Road', city='Surulere', state='Lagos')
        cls.order = Order.objects.create(
            order_number='ASO-TEST-1', customer=shopper, vendor=cls.vendor, order_status=OrderStatus.PAID,
            subtotal_kobo=18_500_000, total_amount_kobo=18_500_000,
            payment_expires_at=timezone.now() + timedelta(minutes=30),
            vendor_accept_due_by=timezone.now() + timedelta(hours=3),
            shipping_address_snapshot={'full_name': 'Kemi Adebayo'})
        OrderItem.objects.create(order=cls.order, variant=variant, product_title_snapshot='Emerald Agbada',
                                 variant_size_snapshot='L', sku_snapshot='EA-L', unit_price_kobo=18_500_000,
                                 quantity=1, total_price_kobo=18_500_000,
                                 custom_measurements={'chest': 42, 'waist': 36})
        VendorBalance.objects.create(vendor=cls.vendor, available_balance_kobo=6_650_000)
        cls.payout = PayoutRequest.objects.create(vendor=cls.vendor, amount_kobo=10_000_000, reference='ASO-PAY-1',
                                                  bank_account=cls.bank, status=PayoutStatus.PAYOUT_RESERVED)
        LedgerEntry.objects.create(vendor=cls.vendor, amount_kobo=10_000_000,
                                   entry_type=LedgerEntryType.PAYOUT_RESERVE, payout_request=cls.payout)

    def setUp(self):
        self.client.force_login(self.staff)

    def test_home_shows_what_needs_attention(self):
        res = self.client.get(reverse('admin:index'))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode()
        self.assertIn('Needs your attention', html)
        self.assertIn('Pieces waiting for review', html)
        self.assertIn('₦100,000 in total', html)          # payouts waiting, in naira
        self.assertIn('approval_status__exact=PENDING', html)
        self.assertIn('Aso Admin', html)
        self.assertIn('aso_admin/admin.css', html)
        self.assertIn('Designers', html)                   # plain section names

    def test_every_list_and_detail_page_opens(self):
        for model, model_admin in admin.site._registry.items():
            meta = model._meta
            url = reverse(f'admin:{meta.app_label}_{meta.model_name}_changelist')
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200, f'{url} -> {res.status_code}')
            obj = model.objects.first()
            if obj is not None:
                detail = reverse(f'admin:{meta.app_label}_{meta.model_name}_change', args=[obj.pk])
                res = self.client.get(detail)
                self.assertEqual(res.status_code, 200, f'{detail} -> {res.status_code}')

    def test_money_is_shown_in_naira(self):
        payouts = self.client.get(reverse('admin:payouts_payoutrequest_changelist')).content.decode()
        self.assertIn('₦100,000', payouts)
        self.assertIn('0123456789', payouts)               # the account being paid is visible
        self.assertIn('code 058', payouts)
        self.assertNotIn('10000000', payouts)
        ledger = self.client.get(reverse('admin:payouts_ledgerentry_changelist')).content.decode()
        self.assertIn('−₦100,000', ledger)                 # a withdrawal is money out
        orders = self.client.get(reverse('admin:orders_order_changelist')).content.decode()
        self.assertIn('₦185,000', orders)
        self.assertIn('Emerald Agbada (L)', orders)
        products = self.client.get(reverse('admin:products_product_changelist')).content.decode()
        self.assertIn('Waiting for review', products)
        self.assertIn('/media/products/a.jpg', products)   # thumbnail

    def test_login_page_is_branded(self):
        self.client.logout()
        res = self.client.get(reverse('admin:login'))
        self.assertEqual(res.status_code, 200)
        self.assertIn('aso_admin/admin.css', res.content.decode())
