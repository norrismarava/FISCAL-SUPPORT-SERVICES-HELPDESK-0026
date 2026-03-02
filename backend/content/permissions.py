# backend/content/permissions.py
from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """Content editors can modify content."""
    
    def has_permission(self, request, view):
        # Allow read-only for everyone
        if request.method in permissions.SAFE_METHODS:
            return True
        # Write access for content editors
        return (
            request.user.is_authenticated
            and request.user.role in ['admin', 'manager', 'accounts']
        )
