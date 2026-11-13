from django.conf import settings
from django.views.static import serve
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.common.media_storage import InvalidImageError, store_image
from apps.vendors.models import VendorStatus

# Images a signed-in user may upload, and who may upload each kind.
#   product -> approved designers only (same rule as creating a product)
#   logo / banner -> any signed-in user (designers upload these while registering,
#                    before their vendor profile exists)
#   avatar -> any signed-in user
UPLOAD_KINDS = {'product', 'logo', 'banner', 'avatar'}


class ImageUploadThrottle(UserRateThrottle):
    scope = 'image_upload'
    rate = '120/hour'


class ImageUploadView(APIView):
    """
    POST /api/v1/media/upload/  (multipart: file=<image>, kind=product|logo|banner|avatar)

    Re-encodes the image, stores it on the media volume and returns
    {"url": "/media/...", "thumbnail_url": "/media/..._thumb.webp" | null}.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ImageUploadThrottle]

    def post(self, request):
        kind = (request.data.get('kind') or 'product').strip().lower()
        if kind not in UPLOAD_KINDS:
            return Response(
                {'success': False, 'message': f'Unknown image kind "{kind}".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        upload = request.FILES.get('file')
        if upload is None:
            return Response(
                {'success': False, 'message': 'No image file was sent.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        vendor = getattr(user, 'vendor_profile', None)
        if kind == 'product':
            if vendor is None or vendor.status != VendorStatus.APPROVED:
                return Response(
                    {'success': False, 'message': 'Only approved designers can upload product photos.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            folder = f'vendors/{vendor.id}/products'
        elif kind in ('logo', 'banner'):
            folder = f'vendors/{vendor.id}/{kind}' if vendor else f'users/{user.id}/{kind}'
        else:
            folder = f'users/{user.id}/avatar'

        try:
            stored = store_image(upload.read(), kind=kind, folder=folder)
        except InvalidImageError as exc:
            return Response({'success': False, 'message': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {'success': True, 'url': stored.url, 'thumbnail_url': stored.thumbnail_url},
            status=status.HTTP_201_CREATED,
        )


def serve_media(request, path):
    """
    Serves uploaded media from MEDIA_ROOT in every environment (Caddy proxies
    /media/* here). Filenames are random UUIDs and never overwritten, so they
    are cached by browsers for a year.
    """
    response = serve(request, path, document_root=settings.MEDIA_ROOT)
    response['Cache-Control'] = 'public, max-age=31536000, immutable'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
