"""
Image storage on the server's own media volume (no external object storage).

Every image is re-encoded with Pillow before it is stored. That means:
  * only real images are accepted (anything Pillow cannot decode is rejected),
  * EXIF data (including phone GPS location) is stripped,
  * phone photos are rotated upright using their EXIF orientation,
  * files are resized and saved as WebP, so a 6 MB phone photo becomes ~100-200 KB.

Each upload produces a full-size image and a small thumbnail for product grids.
Files are named with random UUIDs, so they can be cached by browsers forever.

The public URL returned is a site-relative path ("/media/..."). Caddy routes
/media/* to Django, which serves it from MEDIA_ROOT (see config/urls.py).
To move to S3/R2 later, swap DEFAULT_FILE_STORAGE; callers do not change.
"""
from __future__ import annotations

import base64
import binascii
import io
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps, UnidentifiedImageError

# Pillow refuses images above this many pixels (decompression-bomb guard).
Image.MAX_IMAGE_PIXELS = 60_000_000

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB, matches the studio's client-side limit

# Longest edge in pixels for each kind of image.
FULL_SIZE = {
    'product': 1600,
    'banner': 1920,
    'logo': 512,
    'avatar': 512,
    'category': 1200,
}
THUMB_SIZE = 480          # product grid cards
WEBP_QUALITY = 82
THUMB_QUALITY = 75


class InvalidImageError(ValueError):
    """Raised when the uploaded bytes are not a usable image."""


@dataclass(frozen=True)
class StoredImage:
    url: str
    thumbnail_url: str | None


def _public_url(name: str) -> str:
    base = '/' + settings.MEDIA_URL.strip('/') + '/'
    return base + name.lstrip('/')


def _encode_webp(img: Image.Image, max_edge: int, quality: int) -> bytes:
    copy = img.copy()
    copy.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    copy.save(buf, format='WEBP', quality=quality, method=4)
    return buf.getvalue()


def _open_image(raw: bytes, max_bytes: int) -> Image.Image:
    if not raw:
        raise InvalidImageError('The file is empty.')
    if len(raw) > max_bytes:
        raise InvalidImageError('Images must be 10 MB or smaller.')
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImageError('This file is not a supported image. Please upload a JPG, PNG or WebP photo.') from exc

    img = ImageOps.exif_transpose(img)  # rotate phone photos upright
    # Flatten transparency onto white; WebP supports alpha but product photos look
    # inconsistent on cards when some have transparent backgrounds.
    if img.mode in ('RGBA', 'LA', 'P'):
        rgba = img.convert('RGBA')
        background = Image.new('RGB', rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    return img


def store_image(raw: bytes, *, kind: str, folder: str, max_bytes: int = MAX_UPLOAD_BYTES) -> StoredImage:
    """
    Re-encode and store image bytes. `folder` is a relative path such as
    "vendors/<vendor_id>/products". Returns site-relative URLs.
    `max_bytes` is raised only by the one-off migration of legacy inline images.
    """
    if kind not in FULL_SIZE:
        raise ValueError(f'Unknown image kind: {kind}')
    img = _open_image(raw, max_bytes)

    stem = uuid.uuid4().hex
    folder = folder.strip('/')
    full_name = default_storage.save(
        f'{folder}/{stem}.webp',
        ContentFile(_encode_webp(img, FULL_SIZE[kind], WEBP_QUALITY)),
    )

    thumb_url = None
    if kind == 'product':
        thumb_name = default_storage.save(
            f'{folder}/{stem}_thumb.webp',
            ContentFile(_encode_webp(img, THUMB_SIZE, THUMB_QUALITY)),
        )
        thumb_url = _public_url(thumb_name)

    return StoredImage(url=_public_url(full_name), thumbnail_url=thumb_url)


def is_data_uri(value: object) -> bool:
    return isinstance(value, str) and value.lstrip()[:5].lower() == 'data:'


def decode_data_uri(value: str) -> bytes:
    """Decode a base64 `data:image/...;base64,...` URI into raw bytes."""
    try:
        header, payload = value.strip().split(',', 1)
    except ValueError as exc:
        raise InvalidImageError('Malformed data URI.') from exc
    if ';base64' not in header.lower():
        raise InvalidImageError('Only base64 data URIs are supported.')
    try:
        return base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise InvalidImageError('Data URI is not valid base64.') from exc
