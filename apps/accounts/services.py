from django.db import transaction
from .models import User, CustomerProfile, Address

def create_user_service(*, email: str, password: str, first_name: str, last_name: str, phone_number: str = None) -> User:
    """
    Creates a User and linked CustomerProfile inside an atomic transaction.
    """
    with transaction.atomic():
        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number or None
        )
        CustomerProfile.objects.create(user=user)
        return user


def create_address_service(*, user: User, address_data: dict) -> Address:
    """
    Creates a new shipping address for a user.
    """
    with transaction.atomic():
        # If this is the user's first address, set it as default automatically
        if not Address.objects.filter(user=user).exists():
            address_data['is_default'] = True

        address = Address.objects.create(user=user, **address_data)
        return address
