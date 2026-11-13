from django.db.models import Count, Min, Q
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import VendorProfile, VendorStatus, VerificationStatus
from apps.common.notifications import send_verification_submitted_notification
from apps.common.media_storage import is_data_uri
from .serializers import (
    VendorRegistrationSerializer, VendorProfileSerializer, PublicVendorProfileSerializer, BankAccountSerializer
)
from .services import register_vendor_service, update_bank_account_service
from .selectors import get_vendor_by_slug, get_vendor_bank_account
from apps.common.permissions import IsVendorOwner, CanApplyAsVendor
from apps.orders.serializers import VendorOrderSerializer
from apps.orders.models import Order, OrderStatus


def _notify_if_newly_submitted(vendor, previous_submitted_at=None):
    """Alert the Aso verification team when a save put NIN/CAC into the review queue."""
    if (vendor.verification_status == VerificationStatus.PENDING_REVIEW
            and vendor.verification_submitted_at
            and vendor.verification_submitted_at != previous_submitted_at):
        send_verification_submitted_notification(vendor)


class VendorRegisterView(APIView):
    """
    Allows an authenticated user to apply for a designer vendor storefront.
    """
    permission_classes = [CanApplyAsVendor]

    def post(self, request):
        serializer = VendorRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        bank_data = None
        bank_fields = ['account_name', 'account_number', 'bank_name', 'bank_code']
        if all(data.get(f) for f in bank_fields):
            bank_data = {f: data[f] for f in bank_fields}

        vendor_profile = register_vendor_service(
            user=request.user,
            store_name=data['store_name'],
            city=data['city'],
            state=data['state'],
            description=data.get('description', ''),
            instagram_handle=data.get('instagram_handle', ''),
            workshop_address=data.get('workshop_address', ''),
            landmark=data.get('landmark', ''),
            nin_number=data.get('nin_number', ''),
            cac_number=data.get('cac_number', ''),
            bank_data=bank_data
        )
        _notify_if_newly_submitted(vendor_profile)

        return Response({
            'success': True,
            'message': 'Your studio is live. Add your first piece; each piece is reviewed before it appears publicly.',
            'vendor': VendorProfileSerializer(vendor_profile).data
        }, status=status.HTTP_201_CREATED)



class VendorListView(APIView):
    """
    Public directory of approved fashion ateliers and designers.
    Supports filtering by verification and category.
    Optimized with single-query annotations and Redis response caching.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        verified_param = request.query_params.get('verified', '')
        category_param = request.query_params.get('category', '')

        cache_key = f"aso_vendors_list_v2_{verified_param}_{category_param}"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        # Only products a shopper can actually see count (approved, published, active),
        # so pending pieces never set a studio's "from" price.
        live_products = Q(products__status='PUBLISHED', products__is_active=True,
                          products__approval_status='APPROVED')
        qs = VendorProfile.objects.select_related('user').filter(
            status=VendorStatus.APPROVED
        ).annotate(
            annotated_product_count=Count('products', filter=live_products, distinct=True),
            annotated_starting_price=Min('products__base_price_kobo', filter=live_products)
        ).filter(
            # The public directory lists studios with something to buy. Empty studios
            # are still reachable by their direct /store/<slug> link.
            annotated_product_count__gt=0
        ).prefetch_related('products__media').order_by('-average_rating', '-created_at')

        if verified_param in ['true', '1', 'True']:
            qs = qs.filter(is_verified=True)

        if category_param:
            qs = qs.filter(products__category__slug=category_param, products__status='PUBLISHED',
                           products__is_active=True, products__approval_status='APPROVED').distinct()

        serializer = PublicVendorProfileSerializer(qs, many=True)
        data = serializer.data
        cache.set(cache_key, data, timeout=300)  # 5 min cache
        return Response(data)


class VendorDetailView(APIView):
    """
    Storefront detail endpoint:
    - Public anonymous users can view APPROVED designer storefronts.
    - Vendor owners and Staff can view their own storefront even while PENDING approval (live preview).
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        if request.user.is_authenticated and (
            request.user.is_staff or 
            (hasattr(request.user, 'vendor_profile') and request.user.vendor_profile.slug == slug)
        ):
            vendor = get_object_or_404(
                VendorProfile.objects.select_related('user').exclude(status=VendorStatus.SUSPENDED),
                slug=slug
            )
        else:
            vendor = get_vendor_by_slug(slug)

        return Response({
            'success': True,
            'vendor': PublicVendorProfileSerializer(vendor).data
        })


from apps.products.permissions import IsApprovedVendor

class BankAccountView(APIView):
    """
    Allows an approved vendor to view or update their payout bank account details.
    """
    permission_classes = [IsApprovedVendor]

    def get(self, request):
        account = get_vendor_bank_account(request.user.vendor_profile)
        return Response({
            'success': True,
            'bank_account': BankAccountSerializer(account).data if account else None
        })

    def post(self, request):
        serializer = BankAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        account, created = update_bank_account_service(
            vendor_profile=request.user.vendor_profile,
            bank_data=serializer.validated_data
        )

        msg = 'Bank account created successfully.' if created else 'Bank account updated successfully.'
        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK

        return Response({
            'success': True,
            'message': msg,
            'bank_account': BankAccountSerializer(account).data
        }, status=http_status)


class VendorOrderListView(APIView):
    """
    GET: List orders for authenticated vendors, filterable by status.
    Permission: Only the vendor associated with the orders can view them.
    """
    permission_classes = [IsVendorOwner]

    def get(self, request):
        # Unpaid checkouts are not orders yet: a designer must never start sewing for one.
        orders = Order.objects.filter(
            vendor__user=request.user
        ).exclude(order_status=OrderStatus.PENDING_PAYMENT).select_related('vendor').prefetch_related('items', 'items__variant__product__media').order_by('-created_at')

        serializer = VendorOrderSerializer(orders, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)


class VendorOrderDetailView(APIView):
    """
    GET: Retrieve vendor order detail summary.
    """
    permission_classes = [IsVendorOwner]

    def get(self, request, order_id):
        try:
            order = Order.objects.select_related('vendor').prefetch_related('items').exclude(
                order_status=OrderStatus.PENDING_PAYMENT
            ).get(
                id=order_id,
                vendor__user=request.user
            )
        except Order.DoesNotExist:
            return Response({
                'detail': 'Order not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = VendorOrderSerializer(order)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)




class VendorProfileMeView(APIView):
    """
    GET: Retrieve the authenticated vendor's full profile details.
    PATCH / PUT / POST: Create or Update vendor profile details.
    """
    permission_classes = [CanApplyAsVendor]

    def get(self, request):
        if not hasattr(request.user, 'vendor_profile'):
            return Response({
                'success': True,
                'vendor': None,
                'message': 'No vendor profile registered yet.'
            }, status=status.HTTP_200_OK)
        serializer = VendorProfileSerializer(request.user.vendor_profile)
        return Response({'success': True, 'vendor': serializer.data})

    def patch(self, request):
        user = request.user
        data = request.data.copy()

        # Update user first_name/last_name or phone if provided
        updated_user_fields = []
        if 'first_name' in data and data['first_name']:
            user.first_name = data['first_name']
            updated_user_fields.append('first_name')
        if 'last_name' in data and data['last_name']:
            user.last_name = data['last_name']
            updated_user_fields.append('last_name')
        if 'phone_number' in data and data['phone_number']:
            user.phone_number = data['phone_number']
            updated_user_fields.append('phone_number')
        if updated_user_fields:
            user.save(update_fields=updated_user_fields)

        # If user does not have a vendor profile yet, register one
        if not hasattr(user, 'vendor_profile'):
            for image_field in ('logo_url', 'banner_url'):
                if is_data_uri(data.get(image_field)):
                    return Response({
                        'success': False,
                        'message': 'Upload images first (POST /api/v1/media/upload/) and save the returned URL.',
                        'errors': {image_field: ['Inline image data is not accepted.']},
                    }, status=status.HTTP_400_BAD_REQUEST)
            store_name = data.get('store_name') or f"{user.first_name or 'Artisan'} Atelier"
            city = data.get('city') or 'Lagos'
            state = data.get('state') or 'Lagos'
            vendor = register_vendor_service(
                user=user,
                store_name=store_name,
                city=city,
                state=state,
                description=data.get('description', ''),
                instagram_handle=data.get('instagram_handle', ''),
                workshop_address=data.get('workshop_address', ''),
                landmark=data.get('landmark', ''),
                nin_number=data.get('nin_number', ''),
                cac_number=data.get('cac_number', '')
            )
            _notify_if_newly_submitted(vendor)
            if data.get('logo_url') or data.get('banner_url'):
                if data.get('logo_url'):
                    vendor.logo_url = data['logo_url']
                if data.get('banner_url'):
                    vendor.banner_url = data['banner_url']
                vendor.save()
        else:
            vendor = user.vendor_profile
            previous_submitted_at = vendor.verification_submitted_at
            # A blank NIN/CAC in a profile save means "not edited", never "erase my identity":
            # erasing it would silently drop the designer's verification.
            for identity_field in ('nin_number', 'cac_number'):
                if identity_field in data and not str(data.get(identity_field) or '').strip():
                    data.pop(identity_field)
            serializer = VendorProfileSerializer(vendor, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            _notify_if_newly_submitted(vendor, previous_submitted_at)

        return Response({
            'success': True,
            'message': 'Vendor profile saved successfully.',
            'vendor': VendorProfileSerializer(vendor).data
        }, status=status.HTTP_200_OK)

    def put(self, request):
        return self.patch(request)

    def post(self, request):
        return self.patch(request)

