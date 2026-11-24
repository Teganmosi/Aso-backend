"""The home page shows a small, fair selection: hand-picks first, max 2 per designer, newcomers get seen."""
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.products.home_feed import HOME_DESIGNERS, HOME_PIECES
from apps.products.models import ApprovalStatus, Category, Product, ProductMedia, ProductStatus
from apps.vendors.models import VendorProfile, VendorStatus


class HomeFeedTests(TestCase):
    def setUp(self):
        cache.clear()
        self.cat = Category.objects.create(name='Gowns', description='x')
        self.n = 0

    def tearDown(self):
        cache.clear()

    def studio(self, name, joined_days_ago=200, featured=False):
        self.n += 1
        u = User.objects.create_user(email=f'd{self.n}@aso.test', password='x')
        v = VendorProfile.objects.create(user=u, store_name=name, city='Ikeja', state='Lagos',
                                         status=VendorStatus.APPROVED, is_featured=featured)
        VendorProfile.objects.filter(pk=v.pk).update(created_at=timezone.now() - timedelta(days=joined_days_ago))
        v.refresh_from_db()
        return v

    def piece(self, vendor, title, photo=True, featured=False, live=True):
        p = Product.objects.create(
            vendor=vendor, category=self.cat, title=title, description='x', base_price_kobo=5_000_000,
            approval_status=ApprovalStatus.APPROVED if live else ApprovalStatus.REJECTED,
            status=ProductStatus.PUBLISHED, is_featured=featured)
        if photo:
            ProductMedia.objects.create(product=p, url=f'/media/vendors/x/{p.id}.webp', is_primary=True)
        return p

    def feed(self):
        res = self.client.get('/api/v1/home/')
        self.assertEqual(res.status_code, 200)
        return res.json()

    def test_one_busy_designer_cannot_flood_the_home_page(self):
        busy = self.studio('Busy Studio')
        for i in range(30):
            self.piece(busy, f'Busy piece {i}')
        for i in range(6):
            v = self.studio(f'Studio {i}')
            self.piece(v, f'Studio {i} gown')
            self.piece(v, f'Studio {i} kaftan')
        pieces = self.feed()['pieces']
        self.assertEqual(len(pieces), HOME_PIECES)
        from_busy = [p for p in pieces if p['vendor']['store_name'] == 'Busy Studio']
        self.assertLessEqual(len(from_busy), 2)

    def test_hand_picks_come_first_and_hidden_pieces_never_show(self):
        v = self.studio('Studio')
        for i in range(20):
            self.piece(v, f'Piece {i}')
        picked = self.piece(self.studio('Picked Studio'), 'Hand picked gown', featured=True)
        self.piece(v, 'Taken down but picked', featured=True, live=False)
        self.piece(v, 'No photo', photo=False)
        pieces = self.feed()['pieces']
        self.assertEqual(pieces[0]['id'], str(picked.id))
        titles = {p['title'] for p in pieces}
        self.assertNotIn('Taken down but picked', titles)
        self.assertNotIn('No photo', titles)

    def test_new_designers_get_seen(self):
        for i in range(10):
            v = self.studio(f'Old {i}')
            self.piece(v, f'Old piece {i}a')
            self.piece(v, f'Old piece {i}b')
        newbie = self.studio('New Studio', joined_days_ago=3)
        self.piece(newbie, 'Fresh gown')
        feed = self.feed()
        self.assertIn('Fresh gown', {p['title'] for p in feed['pieces']})
        self.assertIn('New Studio', {d['store_name'] for d in feed['designers']})

    def test_designers_row_is_capped_and_picks_first(self):
        for i in range(15):
            self.piece(self.studio(f'Studio {i}'), f'Gown {i}')
        star = self.studio('Star Studio', featured=True)
        self.piece(star, 'Star gown')
        self.studio('Empty Studio', featured=True)  # no live pieces: never shown
        designers = self.feed()['designers']
        self.assertEqual(len(designers), HOME_DESIGNERS)
        self.assertEqual(designers[0]['store_name'], 'Star Studio')
        self.assertNotIn('Empty Studio', {d['store_name'] for d in designers})

    def test_same_selection_all_day(self):
        for i in range(8):
            v = self.studio(f'S{i}')
            for j in range(3):
                self.piece(v, f'P{i}-{j}')
        first = [p['id'] for p in self.feed()['pieces']]
        cache.clear()
        self.assertEqual(first, [p['id'] for p in self.feed()['pieces']])

    def test_category_pills_with_pieces(self):
        v = self.studio('Studio')
        self.cat = Category.objects.create(name='Native wear', description='x')
        self.piece(v, 'Royal Agbada Set')
        pills = self.feed()['categories_with_pieces']
        self.assertIn('agbada', pills)
        self.assertIn('men', pills)
        self.assertNotIn('boubou', pills)
        self.assertNotIn('women', pills)  # menswear words must not light up the Women pill


class CatalogPagingTests(TestCase):
    def setUp(self):
        cache.clear()
        u = User.objects.create_user(email='d@aso.test', password='x')
        v = VendorProfile.objects.create(user=u, store_name='S', city='I', state='L', status=VendorStatus.APPROVED)
        cat = Category.objects.create(name='Gowns', description='x')
        for i in range(30):
            Product.objects.create(vendor=v, category=cat, title=f'Agbada {i}', description='x',
                                   base_price_kobo=1000, status=ProductStatus.PUBLISHED)

    def tearDown(self):
        cache.clear()

    def test_pages(self):
        first = self.client.get('/api/v1/products/', {'page': 1, 'page_size': 24}).json()
        self.assertEqual((first['count'], len(first['products']), first['has_more']), (30, 24, True))
        second = self.client.get('/api/v1/products/', {'page': 2, 'page_size': 24}).json()
        self.assertEqual((len(second['products']), second['has_more']), (6, False))
        ids = {p['id'] for p in first['products']} | {p['id'] for p in second['products']}
        self.assertEqual(len(ids), 30)

    def test_page_size_is_capped(self):
        res = self.client.get('/api/v1/products/', {'page': 1, 'page_size': 5000}).json()
        self.assertEqual(res['page_size'], 48)

    def test_without_page_the_full_list_is_returned_as_before(self):
        self.assertEqual(len(self.client.get('/api/v1/products/').json()['products']), 30)

    def test_pill_that_is_not_a_real_category_still_finds_pieces(self):
        res = self.client.get('/api/v1/products/', {'category': 'agbada', 'page': 1}).json()
        self.assertEqual(res['count'], 30)


class HomePickAdminTests(TestCase):
    def tearDown(self):
        cache.clear()

    def test_pick_action_updates_home_page_right_away(self):
        cache.clear()
        staff = User.objects.create_superuser(email='ops@aso.test', password='x')
        self.client.force_login(staff)
        u = User.objects.create_user(email='d@aso.test', password='x')
        v = VendorProfile.objects.create(user=u, store_name='S', city='I', state='L', status=VendorStatus.APPROVED)
        cat = Category.objects.create(name='Gowns', description='x')
        pieces = []
        for i in range(14):
            p = Product.objects.create(vendor=v, category=cat, title=f'Gown {i}', description='x',
                                       base_price_kobo=1000, status=ProductStatus.PUBLISHED)
            ProductMedia.objects.create(product=p, url='/media/a.webp', is_primary=True)
            pieces.append(p)
        self.client.get('/api/v1/home/')  # now cached
        self.client.post(reverse('admin:products_product_changelist'),
                         {'action': 'show_on_home_page', '_selected_action': [str(pieces[0].pk)]})
        pieces[0].refresh_from_db()
        self.assertTrue(pieces[0].is_featured)
        self.assertEqual(self.client.get('/api/v1/home/').json()['pieces'][0]['id'], str(pieces[0].id))
