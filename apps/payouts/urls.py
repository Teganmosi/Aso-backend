from django.urls import path
from .views import VendorBalanceView, PayoutWithdrawView

urlpatterns = [
    path('balance/', VendorBalanceView.as_view(), name='payout-balance'),
    path('withdraw/', PayoutWithdrawView.as_view(), name='payout-withdraw'),
]
