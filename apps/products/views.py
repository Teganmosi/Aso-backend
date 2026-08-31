from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.http import Http404

from apps.products.models import ProductVariant, ProductMedia
from apps.products.serializers import (
    CategorySerializer,
    ProductCreateUpdateSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductVariantSerializer,
    ProductMediaSerializer,
    PresignedUploadUrlRequestSerializer,
    ReviewSerializer,
    CreateReviewSerializer
)
from apps.products.selectors import (
    get_active_categories,
    get_category_by_slug,
    get_public_products,
    get_public_product_by_id_or_slug,
    get_product_child_or_none,
    get_vendor_products,
    get_vendor_product_by_id_or_slug
)
from apps.products.services import (
    create_product,
    update_product,
    delete_product,
    create_product_variant,
    update_product_variant,
    delete_product_variant,
    attach_product_media,
    delete_product_media,
    create_verified_review
)
from apps.products.utils import generate_presigned_upload_url
from apps.products.permissions import IsApprovedVendor


class CategoryListView(APIView):
    """
    Public category list endpoint returning the category tree hierarchy.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        categories = get_active_categories(parent_only=True)
        serializer = CategorySerializer(categories, many=True)
        return Response({
            'success': True,
            'categories': serializer.data
        })


class CategoryDetailView(APIView):
    """
    Public category detail endpoint.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        category = get_category_by_slug(slug)
        serializer = CategorySerializer(category)
        return Response({
            'success': True,
            'category': serializer.data
        })


class PublicProductListView(APIView):
    """
    Product listing and creation endpoint:
    - GET: Public product search, filter, and catalog listing (AllowAny).
           Only returns APPROVED, PUBLISHED products from APPROVED vendors.
    - POST: Vendor product creation (IsApprovedVendor).
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsApprovedVendor()]
        return [permissions.AllowAny()]

    def get(self, request):
        search = request.query_params.get('search')
        category_slug = request.query_params.get('category')
        vendor_slug = request.query_params.get('vendor')
        min_price = request.query_params.get('min_price')
        max_price = request.query_params.get('max_price')
        sort_by = request.query_params.get('sort')

        products = get_public_products(
            search=search,
            category_slug=category_slug,
            vendor_slug=vendor_slug,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by
        )

        serializer = ProductListSerializer(products, many=True)
        return Response({
            'success': True,
            'count': len(serializer.data),
            'products': serializer.data
        })

    def post(self, request):
        serializer = ProductCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = create_product(
            vendor_profile=request.user.vendor_profile,
            validated_data=serializer.validated_data
        )

        return Response({
            'success': True,
            'message': 'Product created successfully and submitted for admin approval.',
            'product': ProductDetailSerializer(product).data
        }, status=status.HTTP_201_CREATED)


class PublicProductDetailView(APIView):
    """
    Public product detail endpoint by product UUID or slug.
    Returns the full media gallery and variant availability matrix.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, identifier):
        product = get_public_product_by_id_or_slug(identifier)
        if product is None:
            return Response({
                'success': False,
                'error': {
                    'code': 'not_found',
                    'message': 'Product not found.',
                    'details': {'detail': 'Product not found.'}
                }
            }, status=status.HTTP_404_NOT_FOUND)
        serializer = ProductDetailSerializer(product)
        return Response({
            'success': True,
            'product': serializer.data
        })


class PresignedUploadUrlView(APIView):
    """
    Generates a vendor-scoped presigned S3 / Cloudflare R2 upload URL for product media.
    """
    permission_classes = [IsApprovedVendor]

    def post(self, request):
        serializer = PresignedUploadUrlRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        filename = serializer.validated_data['filename']
        file_type = serializer.validated_data['file_type']

        result = generate_presigned_upload_url(
            filename=filename,
            file_type=file_type,
            vendor_id=str(request.user.vendor_profile.id)
        )

        return Response({
            'success': True,
            'data': result
        }, status=status.HTTP_200_OK)


class VendorProductListCreateView(APIView):
    """
    Vendor product management view:
    - GET: List all products created by the approved vendor.
    - POST: Create a new product (defaults to PENDING approval).
    """
    permission_classes = [IsApprovedVendor]

    def get(self, request):
        products = get_vendor_products(request.user.vendor_profile)
        serializer = ProductListSerializer(products, many=True)
        return Response({
            'success': True,
            'products': serializer.data
        })

    def post(self, request):
        serializer = ProductCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = create_product(
            vendor_profile=request.user.vendor_profile,
            validated_data=serializer.validated_data
        )

        return Response({
            'success': True,
            'message': 'Product created successfully and submitted for admin approval.',
            'product': ProductDetailSerializer(product).data
        }, status=status.HTTP_201_CREATED)


class VendorProductDetailView(APIView):
    """
    Vendor detail view for managing a specific product (GET, PATCH, DELETE).
    """
    permission_classes = [IsApprovedVendor]

    def get(self, request, identifier):
        product = get_vendor_product_by_id_or_slug(request.user.vendor_profile, identifier)
        serializer = ProductDetailSerializer(product)
        return Response({
            'success': True,
            'product': serializer.data
        })

    def patch(self, request, identifier):
        product = get_vendor_product_by_id_or_slug(request.user.vendor_profile, identifier)
        serializer = ProductCreateUpdateSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        updated_prod = update_product(product, serializer.validated_data)
        return Response({
            'success': True,
            'message': 'Product updated successfully.',
            'product': ProductDetailSerializer(updated_prod).data
        })

    def delete(self, request, identifier):
        product = get_vendor_product_by_id_or_slug(request.user.vendor_profile, identifier)
        delete_product(product)
        return Response({
            'success': True,
            'message': 'Product deleted successfully.'
        }, status=status.HTTP_200_OK)


class ProductVariantListCreateView(APIView):
    """
    Vendor view for managing product variants:
    - GET: List variants for a product owned by the vendor.
    - POST: Add a new size/color variant to the product.
    """
    permission_classes = [IsApprovedVendor]

    def get(self, request, product_id):
        product = get_vendor_product_by_id_or_slug(request.user.vendor_profile, product_id)
        variants = product.variants.filter(is_active=True)
        serializer = ProductVariantSerializer(variants, many=True)
        return Response({
            'success': True,
            'variants': serializer.data
        })

    def post(self, request, product_id):
        product = get_vendor_product_by_id_or_slug(request.user.vendor_profile, product_id)
        serializer = ProductVariantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        variant = create_product_variant(product, serializer.validated_data)
        return Response({
            'success': True,
            'message': 'Variant added successfully.',
            'variant': ProductVariantSerializer(variant).data
        }, status=status.HTTP_201_CREATED)


class ProductVariantDetailView(APIView):
    """
    Vendor view for retrieving, updating, or deleting a specific product variant.
    """
    permission_classes = [IsApprovedVendor]

    def get(self, request, product_id, variant_id):
        product = get_vendor_product_by_id_or_slug(request.user.vendor_profile, product_id)
        variant = get_product_child_or_none(product.variants.all(), variant_id)
        if variant is None:
            raise Http404('Variant not found.')
        serializer = ProductVariantSerializer(variant)
        return Response({
            'success': True,
            'variant': serializer.data
        })

    def patch(self, request, product_id, variant_id):
        product = get_vendor_product_by_id_or_slug(request.user.vendor_profile, product_id)
        variant = get_product_child_or_none(product.variants.all(), variant_id)
        if variant is None:
            raise Http404('Variant not found.')
        serializer = ProductVariantSerializer(variant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        updated_var = update_product_variant(variant, serializer.validated_data)
        return Response({
            'success': True,
            'message': 'Variant updated successfully.',
            'variant': ProductVariantSerializer(updated_var).data
        })

    def delete(self, request, product_id, variant_id):
        product = get_vendor_product_by_id_or_slug(request.user.vendor_profile, product_id)
        variant = get_product_child_or_none(product.variants.all(), variant_id)
        if variant is None:
            raise Http404('Variant not found.')
        delete_product_variant(variant)
        return Response({
            'success': True,
            'message': 'Variant deleted successfully.'
        }, status=status.HTTP_200_OK)


class ProductMediaListCreateView(APIView):
    """
    Vendor view for managing product media assets:
    - GET: List attached media for a product owned by the vendor.
    - POST: Attach an uploaded photo or video URL to the product.
    """
    permission_classes = [IsApprovedVendor]

    def get(self, request, product_id):
        product = get_vendor_product_by_id_or_slug(request.user.vendor_profile, product_id)
        media_qs = product.media.all()
        serializer = ProductMediaSerializer(media_qs, many=True)
        return Response({
            'success': True,
            'media': serializer.data
        })

    def post(self, request, product_id):
        product = get_vendor_product_by_id_or_slug(request.user.vendor_profile, product_id)
        serializer = ProductMediaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        media = attach_product_media(product, serializer.validated_data)
        return Response({
            'success': True,
            'message': 'Media asset attached to product successfully.',
            'media': ProductMediaSerializer(media).data
        }, status=status.HTTP_201_CREATED)


class ProductMediaDetailView(APIView):
    """
    Vendor view for deleting an attached product media asset.
    """
    permission_classes = [IsApprovedVendor]

    def delete(self, request, product_id, media_id):
        product = get_vendor_product_by_id_or_slug(request.user.vendor_profile, product_id)
        media = get_product_child_or_none(product.media.all(), media_id)
        if media is None:
            raise Http404('Media not found.')
        delete_product_media(media)
        return Response({
            'success': True,
            'message': 'Media asset deleted successfully.'
        }, status=status.HTTP_200_OK)


class ProductReviewListCreateView(APIView):
    """
    - GET: Public list of verified reviews for a specific product.
    - POST: Authenticated verified customer review submission.
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get(self, request, product_id):
        product = get_public_product_by_id_or_slug(product_id)
        reviews = product.reviews.select_related('customer', 'product').all()
        serializer = ReviewSerializer(reviews, many=True)
        return Response({
            'success': True,
            'count': product.review_count,
            'average_rating': float(product.average_rating),
            'reviews': serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request, product_id):
        product = get_public_product_by_id_or_slug(product_id)
        serializer = CreateReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        review = create_verified_review(
            customer=request.user,
            product=product,
            order_item_id=serializer.validated_data['order_item_id'],
            rating=serializer.validated_data['rating'],
            comment=serializer.validated_data['comment']
        )
        return Response({
            'success': True,
            'message': 'Review submitted successfully.',
            'review': ReviewSerializer(review).data
        }, status=status.HTTP_201_CREATED)


class VendorReviewListView(APIView):
    """
    Public list of reviews across all products belonging to a designer storefront.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        from apps.vendors.models import VendorProfile, VendorStatus
        try:
            vendor = VendorProfile.objects.get(slug=slug, status=VendorStatus.APPROVED)
        except VendorProfile.DoesNotExist:
            raise Http404('Vendor not found.')

        reviews = vendor.reviews.select_related('customer', 'product').all()
        serializer = ReviewSerializer(reviews, many=True)
        return Response({
            'success': True,
            'count': vendor.review_count,
            'average_rating': float(vendor.average_rating),
            'reviews': serializer.data
        }, status=status.HTTP_200_OK)

