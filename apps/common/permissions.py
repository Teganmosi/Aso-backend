from rest_framework import permissions
from apps.vendors.models import VendorStatus

class IsStaffUser(permissions.BasePermission):
    """
    Allows access only to staff/admin users.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff


class IsVendorOwner(permissions.BasePermission):
    """
    Allows access only to approved vendor owners accessing their own objects.
    """
    def has_permission(self, request, view):
        return (
            request.user 
            and request.user.is_authenticated 
            and hasattr(request.user, 'vendor_profile')
            and request.user.vendor_profile.status == VendorStatus.APPROVED
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
