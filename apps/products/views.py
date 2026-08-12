from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from apps.products.serializers import (
    CategorySerializer,
    ProductCreateUpdateSerializer,
    ProductListSerializer,
    ProductDetailSerializer
)
from apps.products.selectors import (
    get_active_categories,
    get_category_by_slug,
    get_public_products,
    get_public_product_by_slug,
    get_vendor_products,
    get_vendor_product_by_id_or_slug
)
from apps.products.services import (
    create_product,
    update_product,
    delete_product
)
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
    Public product detail endpoint by slug.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        product = get_public_product_by_slug(slug)
        serializer = ProductDetailSerializer(product)
        return Response({
            'success': True,
            'product': serializer.data
        })


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
