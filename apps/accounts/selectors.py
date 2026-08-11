from django.shortcuts import get_object_or_404
from .models import User, Address

def get_user_by_id(user_id) -> User:
    return get_object_or_404(User.objects.select_related('customer_profile'), id=user_id)


def get_user_addresses(user: User):
    return Address.objects.filter(user=user).order_by('-is_default', '-created_at')
