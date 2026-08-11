from django.db import transaction
from rest_framework.exceptions import ValidationError
from .models import VendorProfile, BankAccount, VendorStatus
from apps.accounts.models import User

def register_vendor_service(*, user: User, store_name: str, city: str, state: str, description: str = '', bank_data: dict = None) -> VendorProfile:
    """
    Registers a user as a Vendor with a PENDING profile status and optional BankAccount.
    """
    if hasattr(user, 'vendor_profile'):
        raise ValidationError("User has already registered a vendor profile.")

    with transaction.atomic():
        vendor_profile = VendorProfile.objects.create(
            user=user,
            store_name=store_name,
            city=city,
            state=state,
            description=description or '',
            status=VendorStatus.PENDING
        )

        if bank_data and all(k in bank_data for k in ['account_name', 'account_number', 'bank_name', 'bank_code']):
            BankAccount.objects.create(
                vendor=vendor_profile,
                account_name=bank_data['account_name'],
                account_number=bank_data['account_number'],
                bank_name=bank_data['bank_name'],
                bank_code=bank_data['bank_code']
            )

        return vendor_profile


def update_bank_account_service(*, vendor_profile: VendorProfile, bank_data: dict) -> BankAccount:
    """
    Creates or updates the bank account details for an approved vendor.
    """
    with transaction.atomic():
        account, _ = BankAccount.objects.update_or_create(
            vendor=vendor_profile,
            defaults={
                'account_name': bank_data['account_name'],
                'account_number': bank_data['account_number'],
                'bank_name': bank_data['bank_name'],
                'bank_code': bank_data['bank_code']
            }
        )
        return account
