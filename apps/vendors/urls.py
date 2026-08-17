from django.urls import path
from .views import VendorRegisterView, VendorDetailView, BankAccountView, VendorOrderListView, VendorOrderDetailView

urlpatterns = [
    path('register/', VendorRegisterView.as_view(), name='vendor-register'),
    path('bank-account/', BankAccountView.as_view(), name='vendor-bank-account'),
    path('orders/', VendorOrderListView.as_view(), name='vendor-orders'),
    path('orders/<uuid:order_id>/', VendorOrderDetailView.as_view(), name='vendor-order-detail'),
    path('<slug:slug>/', VendorDetailView.as_view(), name='vendor-detail'),
]
