from django.urls import path
from .views import VendorBalanceView, PayoutWithdrawView, PayoutRequestsView, LedgerListView

urlpatterns = [
    path('balance/', VendorBalanceView.as_view(), name='payout-balance'),
    path('withdraw/', PayoutWithdrawView.as_view(), name='payout-withdraw'),
    path('requests/', PayoutRequestsView.as_view(), name='payout-requests'),
    path('ledger/', LedgerListView.as_view(), name='payout-ledger'),
]
