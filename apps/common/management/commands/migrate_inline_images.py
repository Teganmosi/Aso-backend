"""
One-off migration: move images stored inline as base64 `data:` URIs in the
database into files on the media volume (apps/common/media_storage.py).

    python manage.py migrate_inline_images --dry-run   # report only
    python manage.py migrate_inline_images             # convert

Safe to re-run: only rows that still hold `data:` values are touched. Rows that
cannot be decoded are reported and left unchanged. Take a database backup first.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import CustomerProfile
from apps.common.media_storage import InvalidImageError, decode_data_uri, store_image
from apps.products.models import Category, ProductMedia
from apps.products.services import invalidate_product_caches
from apps.vendors.models import VendorProfile

# Legacy inline images were never resized, so allow larger sources than the
# 10 MB limit on new uploads. Output is still resized and re-encoded.
LEGACY_MAX_BYTES = 40 * 1024 * 1024


class Command(BaseCommand):
    help = 'Move base64 data: URI images from the database into media files.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report what would change without writing.')

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.converted = 0
        self.failed = 0
        self.bytes_before = 0

        self._product_media()
        self._vendor_images()
        self._category_images()
        self._avatars()

        if not self.dry_run and self.converted:
            # Cached catalogue lists still hold the old inline images.
            invalidate_product_caches()
            self.stdout.write('Cleared cached product, category and designer lists.')

        verb = 'Would convert' if self.dry_run else 'Converted'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} {self.converted} image(s), {self.failed} failed. '
            f'Inline data found: {self.bytes_before / 1024 / 1024:.1f} MB.'
        ))
        if self.failed:
            self.stdout.write(self.style.WARNING('Failed rows were left unchanged; see messages above.'))

    # ── helpers ───────────────────────────────────────────────────────────

    def _convert(self, label, data_uri, *, kind, folder):
        """Returns StoredImage, or None on dry run / failure."""
        self.bytes_before += len(data_uri)
        try:
            raw = decode_data_uri(data_uri)
            if self.dry_run:
                self.converted += 1
                return None
            stored = store_image(raw, kind=kind, folder=folder, max_bytes=LEGACY_MAX_BYTES)
        except InvalidImageError as exc:
            self.failed += 1
            self.stdout.write(self.style.WARNING(f'  skipped {label}: {exc}'))
            return None
        self.converted += 1
        return stored

    # ── per-table passes (one row in memory at a time) ───────────────────

    def _product_media(self):
        ids = list(
            ProductMedia.objects.filter(url__startswith='data:').values_list('id', flat=True)
        )
        thumb_only_ids = list(
            ProductMedia.objects.filter(thumbnail_url__startswith='data:')
            .exclude(url__startswith='data:').values_list('id', flat=True)
        )
        self.stdout.write(f'Product photos: {len(ids)} inline, {len(thumb_only_ids)} inline thumbnails only')

        for media_id in ids:
            media = ProductMedia.objects.select_related('product').get(id=media_id)
            stored = self._convert(
                f'ProductMedia {media.id}', media.url,
                kind='product', folder=f'vendors/{media.product.vendor_id}/products',
            )
            if stored:
                with transaction.atomic():
                    ProductMedia.objects.filter(id=media.id).update(
                        url=stored.url, thumbnail_url=stored.thumbnail_url
                    )

        # A data: thumbnail next to a real URL is just dead weight: drop it.
        if thumb_only_ids and not self.dry_run:
            ProductMedia.objects.filter(id__in=thumb_only_ids).update(thumbnail_url=None)

    def _vendor_images(self):
        for field, kind in (('logo_url', 'logo'), ('banner_url', 'banner')):
            ids = list(
                VendorProfile.objects.filter(**{f'{field}__startswith': 'data:'}).values_list('id', flat=True)
            )
            self.stdout.write(f'Designer {kind}s: {len(ids)} inline')
            for vendor_id in ids:
                value = VendorProfile.objects.values_list(field, flat=True).get(id=vendor_id)
                stored = self._convert(f'VendorProfile {vendor_id} {field}', value,
                                       kind=kind, folder=f'vendors/{vendor_id}/{kind}')
                if stored:
                    VendorProfile.objects.filter(id=vendor_id).update(**{field: stored.url})

    def _category_images(self):
        ids = list(Category.objects.filter(image_url__startswith='data:').values_list('id', flat=True))
        self.stdout.write(f'Category images: {len(ids)} inline')
        for category_id in ids:
            value = Category.objects.values_list('image_url', flat=True).get(id=category_id)
            stored = self._convert(f'Category {category_id}', value, kind='category', folder='categories')
            if stored:
                Category.objects.filter(id=category_id).update(image_url=stored.url)

    def _avatars(self):
        ids = list(
            CustomerProfile.objects.filter(avatar_url__startswith='data:').values_list('id', flat=True)
        )
        self.stdout.write(f'Customer avatars: {len(ids)} inline')
        for profile_id in ids:
            value = CustomerProfile.objects.values_list('avatar_url', flat=True).get(id=profile_id)
            stored = self._convert(f'CustomerProfile {profile_id} avatar', value,
                                   kind='avatar', folder=f'customers/{profile_id}/avatar')
            if stored:
                CustomerProfile.objects.filter(id=profile_id).update(avatar_url=stored.url)
