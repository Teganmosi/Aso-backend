from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from apps.common.permissions import IsVendorOwner
from .models import PayoutRequest, LedgerEntry
from apps.vendors.serializers import VendorProfileSerializer
from .serializers import VendorBalanceSerializer, PayoutWithdrawalSerializer, PayoutRequestSerializer, LedgerEntrySerializer
from .services import get_or_create_vendor_balance, request_payout, process_payout, resolve_and_verify_kyc


class VendorBalanceView(APIView):
    """
    GET: Exposes the authenticated vendor's balance components (pending, available, reserved).
    """
    permission_classes = [IsVendorOwner]

    def get(self, request):
        vendor_profile = request.user.vendor_profile
        balance = get_or_create_vendor_balance(vendor_profile)
        serializer = VendorBalanceSerializer(balance)
        return Response({
            'success': True,
            'balance': serializer.data
        }, status=status.HTTP_200_OK)


class PayoutWithdrawView(APIView):
    """
    POST: Requests a withdrawal of available balance.
    """
    permission_classes = [IsVendorOwner]

    def post(self, request):
        vendor_profile = request.user.vendor_profile
        serializer = PayoutWithdrawalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount_kobo = serializer.validated_data['amount_kobo']

        # Create payout request (reserves funds atomically)
        payout_request = request_payout(vendor_profile, amount_kobo)

        # Trigger Paystack transfer initiation synchronously/asynchronously
        payout_request = process_payout(payout_request)

        # Re-fetch updated balance
        balance = get_or_create_vendor_balance(vendor_profile)
        balance_serializer = VendorBalanceSerializer(balance)

        return Response({
            'success': True,
            'message': 'Payout requested and is processing.',
            'payout': PayoutRequestSerializer(payout_request).data,
            'balance': balance_serializer.data
        }, status=status.HTTP_201_CREATED)


class VendorVerifyKYCView(APIView):
    """
    POST: Triggers automated KYC NUBAN name resolution and NIN/CAC verification.
    Accessible to any user with a vendor profile (pending or approved).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not hasattr(request.user, 'vendor_profile'):
            return Response({
                'detail': 'Vendor profile not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        vendor_profile = request.user.vendor_profile
        
        # Verify KYC details
        vendor_profile = resolve_and_verify_kyc(vendor_profile)

        return Response({
            'success': True,
            'message': 'KYC verification process completed.',
            'vendor': VendorProfileSerializer(vendor_profile).data
        }, status=status.HTTP_200_OK)


class PayoutRequestsView(APIView):
    """
    GET: Lists all payout requests for the authenticated vendor.
    """
    permission_classes = [IsVendorOwner]

    def get(self, request):
        vendor_profile = request.user.vendor_profile
        requests_qs = PayoutRequest.objects.filter(vendor=vendor_profile).order_by('-created_at')
        serializer = PayoutRequestSerializer(requests_qs, many=True)
        return Response({
            'success': True,
            'payout_requests': serializer.data,
            'requests': serializer.data
        }, status=status.HTTP_200_OK)


class LedgerListView(APIView):
    """
    GET: Lists financial ledger entries for the authenticated vendor.
    """
    permission_classes = [IsVendorOwner]

    def get(self, request):
        vendor_profile = request.user.vendor_profile
        ledger_qs = LedgerEntry.objects.filter(vendor=vendor_profile).order_by('-created_at')
        serializer = LedgerEntrySerializer(ledger_qs, many=True)
        return Response({
            'success': True,
            'ledger': serializer.data
        }, status=status.HTTP_200_OK)
