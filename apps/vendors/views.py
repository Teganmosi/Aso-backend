from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .serializers import (
    VendorRegistrationSerializer, VendorProfileSerializer, PublicVendorProfileSerializer, BankAccountSerializer
)
from .services import register_vendor_service, update_bank_account_service
from .selectors import get_vendor_by_slug, get_vendor_bank_account
from apps.common.permissions import IsVendorOwner

class VendorRegisterView(APIView):
    """
    Allows an authenticated user to apply for a designer vendor storefront.
    """
    permission_classes = [permissions.IsAuthenticated]

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

        return Response({
            'success': True,
            'message': 'Vendor application submitted successfully. Pending admin approval.',
            'vendor': VendorProfileSerializer(vendor_profile).data
        }, status=status.HTTP_201_CREATED)



class VendorDetailView(APIView):
    """
    Public storefront detail endpoint for an approved designer.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        vendor = get_vendor_by_slug(slug)
        return Response({
            'success': True,
            'vendor': PublicVendorProfileSerializer(vendor).data
        })


class BankAccountView(APIView):
    """
    Allows an approved vendor to view or update their payout bank account details.
    """
    permission_classes = [IsVendorOwner]

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


