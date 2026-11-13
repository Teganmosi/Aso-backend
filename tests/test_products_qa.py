"""
QA Verification Suite - Sprint 3: Category Tree & Product Catalog Engine.

Covers the sprint.md verification guide flow plus adversarial edge cases:
- Product creation (PENDING default) -> admin approval -> public search visibility
- Category tree seeding, public category endpoints, inactive handling
- Permission boundaries (anonymous/customer/unapproved vendors/cross-vendor)
- Visibility matrix (approval_status x status x is_active x vendor status)
- Search, category/vendor filters, price ranges, sorting, malformed params
- Vendor dashboard CRUD, re-approval reset on core edits, soft delete
- Admin moderation bulk actions, CSRF enforcement, sensitive field leakage
"""
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User
from apps.vendors.models import VendorProfile, VendorStatus
from apps.products.models import Category, Product, ApprovalStatus, ProductStatus


class ProductsQABase(TestCase):
    """Shared fixtures for Sprint 3 QA tests."""

    def setUp(self):
        # Category tree: Men -> Agbada, Kaftan / Women
        self.men = Category.objects.create(name='Men', description='Menswear')
        self.agbada = Category.objects.create(name='Agbada', parent=self.men, description='Grand agbada')
        self.kaftan = Category.objects.create(name='Kaftan', parent=self.men, description='Kaftans')
        self.women = Category.objects.create(name='Women', description='Womenswear')

        # Vendor A (approved)
        self.vendor_a_user = User.objects.create_user(
            email='vendor.a@qa.test', password='Password123!', first_name='Ada', last_name='A')
        self.vendor_a = VendorProfile.objects.create(
            user=self.vendor_a_user, store_name='Lagos Luxe QA', city='Lagos', state='Lagos',
            status=VendorStatus.APPROVED, is_verified=True)

        # Vendor B (approved) - for cross-vendor isolation tests
        self.vendor_b_user = User.objects.create_user(
            email='vendor.b@qa.test', password='Password123!', first_name='Bola', last_name='B')
        self.vendor_b = VendorProfile.objects.create(
            user=self.vendor_b_user, store_name='Abuja Threads QA', city='Abuja', state='FCT',
            status=VendorStatus.APPROVED, is_verified=True)

        # Customer (no vendor profile)
        self.customer = User.objects.create_user(
            email='customer@qa.test', password='Password123!', first_name='Chidi', last_name='C')

        self.vendor_client = APIClient()
        self.vendor_client.force_authenticate(user=self.vendor_a_user)
        self.products_url = '/api/v1/products/'

    # -- helpers ---------------------------------------------------------
    def make_product(self, vendor=None, category=None, title='QA Product',
                     approval=ApprovalStatus.APPROVED, prod_status=ProductStatus.PUBLISHED,
                     price=5000000, **extra):
        return Product.objects.create(
            vendor=vendor or self.vendor_a,
            category=category or self.agbada,
            title=title,
            description=extra.pop('description', 'QA test product'),
            base_price_kobo=price,
            approval_status=approval,
            status=prod_status,
            **extra,
        )

    def make_admin_client(self, email='qa.admin@aso.test'):
        admin_user = User.objects.create_superuser(email=email, password='AdminPass123!')
        client = APIClient()
        client.force_login(admin_user)
        return client

    def create_via_api(self, client=None, title='Royal Silk Agbada', category=None,
                       price=7500000, **overrides):
        payload = {
            'title': title,
            'category_id': str((category or self.agbada).id),
            'description': 'Handmade silk agbada with intricate embroidery',
            'base_price_kobo': price,
            'preparation_time_days': 5,
        }
        payload.update(overrides)
        return (client or self.vendor_client).post(self.products_url, payload, format='json')


class SprintGuideFlowTests(ProductsQABase):
    """End-to-end walkthrough exactly as written in sprint.md Sprint 3 guide."""

    def test_full_create_approve_search_flow(self):
        # Step 1: Approved vendor creates "Royal Silk Agbada" at 7,500,000 Kobo
        res = self.create_via_api()
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['product']['approval_status'], 'PENDING')
        self.assertEqual(res.data['product']['base_price_kobo'], 7500000)
        self.assertEqual(res.data['product']['base_price_naira'], 75000.0)
        slug = res.data['product']['slug']

        # Step 2: PENDING product is NOT visible to public customers
        public_list = APIClient().get(self.products_url)
        self.assertEqual(public_list.data['count'], 0)
        self.assertEqual(APIClient().get(self.products_url + '?search=Agbada').data['count'], 0)
        self.assertEqual(
            APIClient().get('/api/v1/products/%s/' % slug).status_code,
            status.HTTP_404_NOT_FOUND)

        # Step 3: Admin approves via Django Admin bulk action
        product = Product.objects.get(slug=slug)
        admin_client = self.make_admin_client()
        action_res = admin_client.post(
            '/admin/products/product/',
            {'action': 'approve_selected_products', ACTION_CHECKBOX_NAME: [str(product.pk)]},
        )
        self.assertIn(action_res.status_code, (status.HTTP_200_OK, status.HTTP_302_FOUND))
        product.refresh_from_db()
        self.assertEqual(product.approval_status, ApprovalStatus.APPROVED)
        self.assertEqual(product.status, ProductStatus.PUBLISHED)

        # Step 4: Product now appears in public search
        search = APIClient().get(self.products_url + '?search=Agbada')
        self.assertEqual(search.status_code, status.HTTP_200_OK)
        self.assertEqual(search.data['count'], 1)
        self.assertEqual(search.data['products'][0]['title'], 'Royal Silk Agbada')

        # Public detail resolves too
        detail = APIClient().get('/api/v1/products/%s/' % slug)
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['product']['title'], 'Royal Silk Agbada')

    def test_admin_reject_action_hides_product_and_records_state(self):
        product = self.make_product(approval=ApprovalStatus.PENDING, title='Rejected Gown')
        admin_client = self.make_admin_client('qa.admin2@aso.test')
        admin_client.post(
            '/admin/products/product/',
            {'action': 'reject_selected_products', ACTION_CHECKBOX_NAME: [str(product.pk)]},
        )
        product.refresh_from_db()
        self.assertEqual(product.approval_status, ApprovalStatus.REJECTED)
        self.assertEqual(APIClient().get(self.products_url).data['count'], 0)

    def test_approve_action_clears_previous_rejection_reason(self):
        product = self.make_product(
            approval=ApprovalStatus.REJECTED, prod_status=ProductStatus.DRAFT,
            title='Comeback Kaftan', rejection_reason='Blurry photos')
        admin_client = self.make_admin_client('qa.admin3@aso.test')
        admin_client.post(
            '/admin/products/product/',
            {'action': 'approve_selected_products', ACTION_CHECKBOX_NAME: [str(product.pk)]},
        )
        product.refresh_from_db()
        self.assertIsNone(product.rejection_reason)
        self.assertEqual(product.status, ProductStatus.PUBLISHED)


class CategoryTreeTests(ProductsQABase):
    def test_seed_command_creates_documented_tree_and_is_idempotent(self):
        from io import StringIO
        Category.objects.all().delete()
        call_command('seed_categories', stdout=StringIO())
        # Launch taxonomy (seed_categories.py): 4 roots + 18 subcategories
        self.assertEqual(Category.objects.count(), 22)
        roots = {c.name for c in Category.objects.filter(parent__isnull=True)}
        self.assertEqual(roots, {'Men', 'Women', 'Traditional & Heritage', 'Accessories'})
        men_children = {c.name for c in Category.objects.get(name='Men').children.all()}
        self.assertIn('Agbada & Grand Native Sets', men_children)
        self.assertEqual(Category.objects.get(name='Women').children.count(), 7)

        # Running twice must not duplicate
        call_command('seed_categories', stdout=StringIO())
        self.assertEqual(Category.objects.count(), 22)

    def test_public_category_list_is_nested_and_anonymous_friendly(self):
        # Tree view: roots only (display_order, then name) with children nested.
        res = APIClient().get('/api/v1/categories/?parent_only=true')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        names = [c['name'] for c in res.data['categories']]
        self.assertEqual(names, ['Men', 'Women'])
        men = res.data['categories'][0]
        child_names = {c['name'] for c in men['children']}
        self.assertEqual(child_names, {'Agbada', 'Kaftan'})

        # Default view (used by the studio picker): every active category, anonymously.
        flat = APIClient().get('/api/v1/categories/')
        self.assertEqual(flat.status_code, status.HTTP_200_OK)
        self.assertEqual({c['name'] for c in flat.data['categories']}, {'Men', 'Women', 'Agbada', 'Kaftan'})

    def test_inactive_categories_hidden_from_list_and_detail(self):
        self.women.is_active = False
        self.women.save()
        inactive_child = Category.objects.create(name='Retired', parent=self.men, is_active=False)

        res = APIClient().get('/api/v1/categories/')
        names = [c['name'] for c in res.data['categories']]
        self.assertNotIn('Women', names)
        men_children = {c['name'] for c in res.data['categories'][0]['children']}
        self.assertNotIn('Retired', men_children)

        self.assertEqual(
            APIClient().get('/api/v1/categories/%s/' % inactive_child.slug).status_code,
            status.HTTP_404_NOT_FOUND)

    def test_category_detail_404_for_unknown_slug(self):
        self.assertEqual(
            APIClient().get('/api/v1/categories/no-such-category/').status_code,
            status.HTTP_404_NOT_FOUND)


class PermissionBoundaryTests(ProductsQABase):
    def test_product_creation_forbidden_for_anonymous_customer_and_unapproved_vendors(self):
        payload = {'title': 'X', 'category_id': str(self.agbada.id),
                   'description': 'd', 'base_price_kobo': 100}
        # Anonymous
        self.assertEqual(APIClient().post(self.products_url, payload, format='json').status_code,
                         status.HTTP_403_FORBIDDEN)
        # Customer without vendor profile
        customer_client = APIClient()
        customer_client.force_authenticate(user=self.customer)
        self.assertEqual(customer_client.post(self.products_url, payload, format='json').status_code,
                         status.HTTP_403_FORBIDDEN)
        # Pending / rejected / suspended vendors
        for vendor_status in (VendorStatus.PENDING, VendorStatus.REJECTED, VendorStatus.SUSPENDED):
            user = User.objects.create_user(
                email='v.%s@qa.test' % vendor_status, password='Password123!',
                first_name='V', last_name=vendor_status)
            VendorProfile.objects.create(
                user=user, store_name='Store %s' % vendor_status, city='Lagos', state='Lagos',
                status=vendor_status)
            client = APIClient()
            client.force_authenticate(user=user)
            res = client.post(self.products_url, payload, format='json')
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, msg=vendor_status)

    def test_vendor_dashboard_requires_approved_vendor(self):
        customer_client = APIClient()
        customer_client.force_authenticate(user=self.customer)
        self.assertEqual(customer_client.get('/api/v1/vendor/products/').status_code,
                         status.HTTP_403_FORBIDDEN)
        self.assertEqual(APIClient().get('/api/v1/vendor/products/').status_code,
                         status.HTTP_403_FORBIDDEN)

    def test_cross_vendor_isolation_on_get_patch_delete(self):
        product_a = self.make_product(vendor=self.vendor_a, title='Vendor A Exclusive')
        vendor_b_client = APIClient()
        vendor_b_client.force_authenticate(user=self.vendor_b_user)
        base = '/api/v1/vendor/products/%s/' % product_a.id

        self.assertEqual(vendor_b_client.get(base).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(vendor_b_client.patch(base, {'title': 'Hijacked'}, format='json').status_code,
                         status.HTTP_404_NOT_FOUND)
        self.assertEqual(vendor_b_client.delete(base).status_code, status.HTTP_404_NOT_FOUND)

        # Owner still sees it untouched
        self.assertEqual(self.vendor_client.get(base).status_code, status.HTTP_200_OK)
        self.assertEqual(Product.objects.get(pk=product_a.pk).title, 'Vendor A Exclusive')

    def test_public_catalog_readable_anonymously(self):
        self.make_product(title='Public Kaftan')
        res = APIClient().get(self.products_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 1)


class ValidationTests(ProductsQABase):
    def test_missing_required_fields_rejected(self):
        for payload in (
            {},
            {'title': 'No Category'},
            {'title': 'No Price', 'category_id': str(self.agbada.id), 'description': 'd'},
            {'category_id': str(self.agbada.id), 'description': 'd', 'base_price_kobo': 100},
        ):
            res = self.vendor_client.post(self.products_url, payload, format='json')
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg=str(payload))

    def test_invalid_or_inactive_category_rejected(self):
        import uuid
        res_unknown = self.vendor_client.post(self.products_url, {
            'title': 'Ghost Category', 'category_id': str(uuid.uuid4()),
            'description': 'd', 'base_price_kobo': 100}, format='json')
        self.assertEqual(res_unknown.status_code, status.HTTP_400_BAD_REQUEST)

        self.women.is_active = False
        self.women.save()
        res_inactive = self.create_via_api(category=self.women, title='Inactive Category')
        self.assertEqual(res_inactive.status_code, status.HTTP_400_BAD_REQUEST)

    def test_price_and_prep_time_validation(self):
        for bad in (
            {'base_price_kobo': 0},
            {'base_price_kobo': -500},
            {'preparation_time_days': 0},
            {'preparation_time_days': 91},
        ):
            res = self.create_via_api(title='Bad %s' % bad, **bad)
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg=str(bad))

    def test_preparation_time_defaults_to_three_days(self):
        # Explicit payload WITHOUT preparation_time_days (helper always sends 5)
        res = self.vendor_client.post(self.products_url, {
            'title': 'Default Prep',
            'category_id': str(self.agbada.id),
            'description': 'd',
            'base_price_kobo': 100000,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['product']['preparation_time_days'], 3)

    def test_title_max_length_enforced(self):
        res = self.create_via_api(title='A' * 256)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_vendor_cannot_force_approval_status(self):
        # approval_status is read-only: a vendor attempting APPROVED must still land in PENDING
        res = self.create_via_api(title='Sneaky Approval', approval_status='APPROVED')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['product']['approval_status'], 'PENDING')

    def test_duplicate_titles_allowed_with_suffixed_slugs(self):
        r1 = self.create_via_api(title='Signature Kaftan')
        r2 = self.create_via_api(title='Signature Kaftan')
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r1.data['product']['slug'], 'signature-kaftan')
        self.assertEqual(r2.data['product']['slug'], 'signature-kaftan-1')


class VisibilityMatrixTests(ProductsQABase):
    """Only APPROVED approval + PUBLISHED status + is_active + APPROVED vendor may surface."""

    def test_public_list_excludes_every_non_visible_combination(self):
        self.make_product(title='Visible One')  # the only visible product
        self.make_product(title='Pending Approval', approval=ApprovalStatus.PENDING)
        self.make_product(title='Rejected Product', approval=ApprovalStatus.REJECTED)
        self.make_product(title='Approved Draft', prod_status=ProductStatus.DRAFT)
        self.make_product(title='Approved Archived', prod_status=ProductStatus.ARCHIVED)
        self.make_product(title='Soft Deleted', is_active=False)
        suspended_vendor = VendorProfile.objects.create(
            user=User.objects.create_user(email='susp@qa.test', password='Password123!',
                                          first_name='S', last_name='V'),
            store_name='Suspended Styles QA', city='Lagos', state='Lagos',
            status=VendorStatus.SUSPENDED)
        self.make_product(title='Suspended Vendor Product', vendor=suspended_vendor)

        res = APIClient().get(self.products_url)
        titles = [p['title'] for p in res.data['products']]
        self.assertEqual(titles, ['Visible One'])
        self.assertEqual(res.data['count'], 1)

    def test_public_detail_404_for_each_hidden_state(self):
        hidden = [
            self.make_product(title='H Pending', approval=ApprovalStatus.PENDING),
            self.make_product(title='H Rejected', approval=ApprovalStatus.REJECTED),
            self.make_product(title='H Draft', prod_status=ProductStatus.DRAFT),
            self.make_product(title='H Archived', prod_status=ProductStatus.ARCHIVED),
            self.make_product(title='H Inactive', is_active=False),
        ]
        for product in hidden:
            res = APIClient().get('/api/v1/products/%s/' % product.slug)
            self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND, msg=product.title)

    def test_owner_still_sees_own_pending_products_in_dashboard(self):
        self.make_product(title='My Pending Draft', approval=ApprovalStatus.PENDING,
                          prod_status=ProductStatus.DRAFT)
        res = self.vendor_client.get('/api/v1/vendor/products/')
        self.assertEqual(len(res.data['products']), 1)
        self.assertEqual(res.data['products'][0]['title'], 'My Pending Draft')


class SearchFilterSortTests(ProductsQABase):
    def setUp(self):
        super().setUp()
        self.cheap = self.make_product(title='Budget Kaftan', price=2000000,
                                       description='Everyday kaftan wear', category=self.kaftan)
        self.mid = self.make_product(title='Senator Deluxe', price=5000000,
                                     description='Premium senator suit', category=self.men)
        self.luxury = self.make_product(title='Royal Silk Agbada', price=9000000,
                                        description='Hand embroidered silk', category=self.agbada)

    def test_search_matches_title_description_and_store_name(self):
        for term, expected in (('kaftan', ['Budget Kaftan']),
                               ('embroidered', ['Royal Silk Agbada']),
                               ('Lagos Luxe QA', ['Budget Kaftan', 'Senator Deluxe', 'Royal Silk Agbada'])):
            res = APIClient().get(self.products_url + '?search=%s' % term)
            titles = sorted(p['title'] for p in res.data['products'])
            self.assertEqual(titles, sorted(expected), msg=term)

    def test_search_no_match_returns_empty_not_error(self):
        res = APIClient().get(self.products_url + '?search=zzzznothing')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 0)

    def test_category_filter_parent_includes_children_and_child_is_exact(self):
        res_parent = APIClient().get(self.products_url + '?category=men')
        self.assertEqual(res_parent.data['count'], 3)  # all three live under Men tree
        res_child = APIClient().get(self.products_url + '?category=agbada')
        self.assertEqual([p['title'] for p in res_child.data['products']], ['Royal Silk Agbada'])
        res_women = APIClient().get(self.products_url + '?category=women')
        self.assertEqual(res_women.data['count'], 0)

    def test_vendor_filter(self):
        self.make_product(vendor=self.vendor_b, title='Abuja Exclusive', category=self.women)
        res = APIClient().get(self.products_url + '?vendor=abuja-threads-qa')
        self.assertEqual([p['title'] for p in res.data['products']], ['Abuja Exclusive'])

    def test_price_range_filters(self):
        res = APIClient().get(self.products_url + '?min_price=5000000&max_price=8000000')
        self.assertEqual([p['title'] for p in res.data['products']], ['Senator Deluxe'])

    def test_sorting_options(self):
        asc = APIClient().get(self.products_url + '?sort=price_asc').data['products']
        self.assertEqual([p['title'] for p in asc], ['Budget Kaftan', 'Senator Deluxe', 'Royal Silk Agbada'])
        desc = APIClient().get(self.products_url + '?sort=price_desc').data['products']
        self.assertEqual([p['title'] for p in desc], ['Royal Silk Agbada', 'Senator Deluxe', 'Budget Kaftan'])
        newest = APIClient().get(self.products_url + '?sort=newest').data['products']
        self.assertEqual(len(newest), 3)

    def test_rating_sort_orders_by_average_rating(self):
        self.cheap.average_rating = 4.8
        self.cheap.review_count = 12
        self.cheap.save()
        res = APIClient().get(self.products_url + '?sort=rating').data['products']
        self.assertEqual(res[0]['title'], 'Budget Kaftan')

    def test_malformed_query_params_do_not_crash(self):
        for query in ('min_price=abc', 'max_price=xyz', 'category=no-such-cat',
                      'vendor=no-such-vendor', 'sort=bogus_value', 'search='):
            res = APIClient().get('%s?%s' % (self.products_url, query))
            self.assertEqual(res.status_code, status.HTTP_200_OK, msg=query)


class VendorManagementTests(ProductsQABase):
    def test_patch_non_core_field_keeps_approval_and_public_visibility(self):
        product = self.make_product(title='Stable Product')
        res = self.vendor_client.patch(
            '/api/v1/vendor/products/%s/' % product.id,
            {'preparation_time_days': 7}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['product']['approval_status'], 'APPROVED')
        self.assertEqual(APIClient().get(self.products_url).data['count'], 1)

    def test_patch_core_field_resets_approval_and_hides_product(self):
        product = self.make_product(title='Edited Product')
        self.assertEqual(APIClient().get(self.products_url).data['count'], 1)

        res = self.vendor_client.patch(
            '/api/v1/vendor/products/%s/' % product.id,
            {'base_price_kobo': 9999900}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['product']['approval_status'], 'PENDING')

        # Now hidden from public until re-approved
        self.assertEqual(APIClient().get(self.products_url).data['count'], 0)

    def test_rejected_product_edit_returns_to_pending_review(self):
        product = self.make_product(title='Fix And Resubmit', approval=ApprovalStatus.REJECTED,
                                    prod_status=ProductStatus.DRAFT, rejection_reason='Bad photos')
        res = self.vendor_client.patch(
            '/api/v1/vendor/products/%s/' % product.id,
            {'description': 'New improved photos attached'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['product']['approval_status'], 'PENDING')

    def test_vendor_product_lookup_by_id(self):
        product = self.make_product(title='Lookup Check')
        by_id = self.vendor_client.get('/api/v1/vendor/products/%s/' % product.id)
        self.assertEqual(by_id.status_code, status.HTTP_200_OK)
        self.assertEqual(by_id.data['product']['id'], str(product.id))

    def test_vendor_product_lookup_by_slug(self):
        """
        QA REGRESSION (formerly bug probe, fixed 2026-08-12): slug lookups on
        /api/v1/vendor/products/<slug>/ previously raised an uncaught
        ValidationError (HTTP 500) because only ValueError was caught.
        """
        product = self.make_product(title='Lookup Check Slug')
        by_slug = self.vendor_client.get('/api/v1/vendor/products/%s/' % product.slug)
        self.assertEqual(by_slug.status_code, status.HTTP_200_OK)
        self.assertEqual(by_slug.data['product']['id'], str(product.id))
        # Non-UUID garbage identifier should resolve to 404, not 500
        self.assertEqual(
            self.vendor_client.get('/api/v1/vendor/products/not-a-uuid-or-slug/').status_code,
            status.HTTP_404_NOT_FOUND)

    def test_vendor_product_patch_and_delete_by_slug(self):
        """Slug identifier must work for PATCH and DELETE too, not just GET."""
        product = self.make_product(title='Slug Managed Product')
        patch_res = self.vendor_client.patch(
            '/api/v1/vendor/products/%s/' % product.slug,
            {'preparation_time_days': 9}, format='json')
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data['product']['preparation_time_days'], 9)

        delete_res = self.vendor_client.delete('/api/v1/vendor/products/%s/' % product.slug)
        self.assertEqual(delete_res.status_code, status.HTTP_200_OK)
        product.refresh_from_db()
        self.assertFalse(product.is_active)

    def test_soft_delete_hides_everywhere_but_keeps_row(self):
        product = self.make_product(title='Doomed Product')
        res = self.vendor_client.delete('/api/v1/vendor/products/%s/' % product.id)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.assertEqual(APIClient().get(self.products_url).data['count'], 0)
        self.assertEqual(APIClient().get('/api/v1/products/%s/' % product.slug).status_code,
                         status.HTTP_404_NOT_FOUND)
        self.assertEqual(len(self.vendor_client.get('/api/v1/vendor/products/').data['products']), 0)

        product.refresh_from_db()
        self.assertFalse(product.is_active)  # row preserved for audit/orders

    def test_vendor_list_shows_all_own_approval_states(self):
        self.make_product(title='Mine Pending', approval=ApprovalStatus.PENDING)
        self.make_product(title='Mine Rejected', approval=ApprovalStatus.REJECTED)
        self.make_product(title='Mine Live')
        res = self.vendor_client.get('/api/v1/vendor/products/')
        self.assertEqual(len(res.data['products']), 3)


class SecurityTests(ProductsQABase):
    def test_product_public_payload_never_leaks_vendor_sensitive_fields(self):
        self.vendor_a.nin_number = '12345678901'
        self.vendor_a.cac_number = 'RC123456'
        self.vendor_a.save()
        self.make_product(title='Secure Product')

        listing = APIClient().get(self.products_url).data['products'][0]
        detail = APIClient().get('/api/v1/products/%s/' % listing['slug']).data['product']
        for body in (listing, detail):
            vendor_payload = body['vendor']
            for sensitive in ('nin_number', 'cac_number', 'bank_account', 'recipient_code', 'email'):
                self.assertNotIn(sensitive, vendor_payload)

    def test_product_creation_enforces_csrf_on_session_auth(self):
        from apps.vendors.models import VendorProfile as VP
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.get(reverse('csrf-token'))
        token = csrf_client.cookies['csrftoken'].value
        reg = csrf_client.post(reverse('auth-register'), {
            'email': 'csrf.vendor@qa.test', 'password': 'Password123!',
            'first_name': 'C', 'last_name': 'V'}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(reg.status_code, status.HTTP_201_CREATED)
        # Approve the vendor out-of-band so the session user is an approved vendor
        user = User.objects.get(email='csrf.vendor@qa.test')
        VP.objects.create(user=user, store_name='CSRF Vendor QA', city='Lagos', state='Lagos',
                          status=VendorStatus.APPROVED)

        payload = {'title': 'CSRF Check', 'category_id': str(self.agbada.id),
                   'description': 'd', 'base_price_kobo': 100000}
        res_no_csrf = csrf_client.post(self.products_url, payload, format='json')
        self.assertEqual(res_no_csrf.status_code, status.HTTP_403_FORBIDDEN)

        res_with_csrf = csrf_client.post(self.products_url, payload, format='json',
                                         HTTP_X_CSRFTOKEN=csrf_client.cookies['csrftoken'].value)
        self.assertEqual(res_with_csrf.status_code, status.HTTP_201_CREATED)


class ReviewNotificationTests(TestCase):
    """Designers hear back when a piece is approved or needs changes, and a fixed piece returns to review."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.vendors.models import VendorProfile, VendorStatus
        from apps.products.models import Category
        U = get_user_model()
        self.staff = U.objects.create_superuser(email='staff@aso.test', password='Password123!')
        owner = U.objects.create_user(email='maker@aso.test', password='Password123!')
        self.vendor = VendorProfile.objects.create(user=owner, store_name='Maker', city='Ikeja', state='Lagos',
                                                   status=VendorStatus.APPROVED)
        self.owner = owner
        self.category = Category.objects.create(name='Review Cat', description='c')

    def _product(self, approval):
        from apps.products.models import Product, ProductStatus
        return Product.objects.create(vendor=self.vendor, category=self.category, title='Kaftan', description='d',
                                      base_price_kobo=100000, approval_status=approval, status=ProductStatus.PUBLISHED)

    def test_approve_action_emails_designer(self):
        from django.core import mail
        from django.test import override_settings
        from apps.products.models import ApprovalStatus
        product = self._product(ApprovalStatus.PENDING)
        self.client.force_login(self.staff)
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            self.client.post('/admin/products/product/', {'action': 'approve_selected_products',
                                                          '_selected_action': [str(product.id)]})
            self.assertEqual(len(mail.outbox), 1)
            self.assertIn('live', mail.outbox[0].subject)
            self.assertEqual(mail.outbox[0].to, ['maker@aso.test'])

    def test_rejected_piece_returns_to_review_on_any_save(self):
        from apps.products.models import ApprovalStatus
        from apps.products.services import update_product
        product = self._product(ApprovalStatus.REJECTED)
        update_product(product, {})
        product.refresh_from_db()
        self.assertEqual(product.approval_status, ApprovalStatus.PENDING)
