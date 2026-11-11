from rest_framework import permissions
from apps.vendors.models import VendorStatus

class IsStaffUser(permissions.BasePermission):
    """
    Allows access only to staff/admin users.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff


class CanApplyAsVendor(permissions.BasePermission):
    """
    Allows any authenticated user to create (or manage) their own vendor profile,
    except vendors who have been suspended. Unlike IsVendorOwner, it does NOT
    require an existing vendor_profile, so new designers can register.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        vendor_profile = getattr(request.user, 'vendor_profile', None)
        return vendor_profile is None or vendor_profile.status != VendorStatus.SUSPENDED


class IsVendorOwner(permissions.BasePermission):
    """
    Allows access to vendor owners accessing their own objects.
    Designers can post and manage their wares, profile, and orders immediately.
    """
    def has_permission(self, request, view):
        return bool(
            request.user 
            and request.user.is_authenticated 
            and hasattr(request.user, 'vendor_profile')
            and request.user.vendor_profile.status != VendorStatus.SUSPENDED
        )

    def has_object_permission(self, request, view, obj):
        if not (request.user and request.user.is_authenticated and hasattr(request.user, 'vendor_profile')):
            return False
        
        vendor_profile = request.user.vendor_profile
        if hasattr(obj, 'vendor'):
            return obj.vendor == vendor_profile
        if hasattr(obj, 'vendor_id'):
            return obj.vendor_id == vendor_profile.id
        return obj == vendor_profile
