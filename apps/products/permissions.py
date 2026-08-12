from rest_framework import permissions
from apps.vendors.models import VendorStatus


class IsApprovedVendor(permissions.BasePermission):
    """
    Allows access only to authenticated users with an APPROVED vendor profile.
    """

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, 'vendor_profile')
            and request.user.vendor_profile.status == VendorStatus.APPROVED
        )

    def has_object_permission(self, request, view, obj):
        if not self.has_permission(request, view):
            return False
        vendor_profile = request.user.vendor_profile
        if hasattr(obj, 'vendor'):
            return obj.vendor == vendor_profile
        return False
