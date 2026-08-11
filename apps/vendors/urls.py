from django.urls import path
from .views import VendorRegisterView, VendorDetailView, BankAccountView

urlpatterns = [
    path('register/', VendorRegisterView.as_view(), name='vendor-register'),
    path('bank-account/', BankAccountView.as_view(), name='vendor-bank-account'),
    path('<slug:slug>/', VendorDetailView.as_view(), name='vendor-detail'),
]
