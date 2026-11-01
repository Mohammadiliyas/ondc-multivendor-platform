from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)

class IsVendorOwner(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and hasattr(request.user, 'vendor_profile'))
    def has_object_permission(self, request, view, obj):
        vendor = getattr(obj, 'vendor', obj)
        return vendor.owner_id == request.user.id and vendor.is_approved and not vendor.is_suspended
