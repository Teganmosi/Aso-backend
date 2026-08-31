from django.urls import path
from apps.products.views import (
    CategoryListView,
    CategoryDetailView,
    PublicProductListView,
    PublicProductDetailView,
    PresignedUploadUrlView,
    VendorProductListCreateView,
    VendorProductDetailView,
    ProductVariantListCreateView,
    ProductVariantDetailView,
    ProductMediaListCreateView,
    ProductMediaDetailView,
    ProductReviewListCreateView
)

urlpatterns = [
    # Category Endpoints
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('categories/<slug:slug>/', CategoryDetailView.as_view(), name='category-detail'),

    # Presigned S3/R2 Upload URL Generator
    path('products/upload-url/', PresignedUploadUrlView.as_view(), name='product-upload-url'),

    # Product Reviews
    path('products/<str:product_id>/reviews/', ProductReviewListCreateView.as_view(), name='product-review-list-create'),

    # Public Product Catalog & Vendor Creation Endpoints
    path('products/', PublicProductListView.as_view(), name='product-list-create'),
    path('products/<str:identifier>/', PublicProductDetailView.as_view(), name='product-detail'),

    # Vendor Dashboard Product Management Endpoints
    path('vendor/products/', VendorProductListCreateView.as_view(), name='vendor-product-list-create'),
    path('vendor/products/<str:identifier>/', VendorProductDetailView.as_view(), name='vendor-product-detail'),

    # Vendor Product Variant Endpoints
    path('products/<str:product_id>/variants/', ProductVariantListCreateView.as_view(), name='product-variant-list-create'),
    path('products/<str:product_id>/variants/<str:variant_id>/', ProductVariantDetailView.as_view(), name='product-variant-detail'),

    # Vendor Product Media Endpoints
    path('products/<str:product_id>/media/', ProductMediaListCreateView.as_view(), name='product-media-list-create'),
    path('products/<str:product_id>/media/<str:media_id>/', ProductMediaDetailView.as_view(), name='product-media-detail'),
]
