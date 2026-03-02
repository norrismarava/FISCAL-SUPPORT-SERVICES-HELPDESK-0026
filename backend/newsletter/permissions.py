# backend/newsletter/permissions.py
from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """Only admins can manage newsletter"""
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.role == 'admin'