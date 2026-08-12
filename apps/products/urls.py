from django.urls import path
from apps.products.views import (
    CategoryListView,
    CategoryDetailView,
    PublicProductListView,
    PublicProductDetailView,
    VendorProductListCreateView,
    VendorProductDetailView
)

urlpatterns = [
    # Category Endpoints
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('categories/<slug:slug>/', CategoryDetailView.as_view(), name='category-detail'),

    # Public Product Catalog & Vendor Creation Endpoints
    path('products/', PublicProductListView.as_view(), name='product-list-create'),
    path('products/<slug:slug>/', PublicProductDetailView.as_view(), name='product-detail'),

    # Vendor Dashboard Product Management Endpoints
    path('vendor/products/', VendorProductListCreateView.as_view(), name='vendor-product-list-create'),
    path('vendor/products/<str:identifier>/', VendorProductDetailView.as_view(), name='vendor-product-detail'),
]
