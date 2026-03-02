# backend/callogs/permissions.py
from rest_framework import permissions

class IsStaffUser(permissions.BasePermission):
    """Only staff members can access call logs"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in [
            'admin', 'manager', 'technician', 'accounts'
        ]

    def has_object_permission(self, request, view, obj):
        return request.user.role in ['admin', 'manager', 'technician', 'accounts']


class IsAccountsOrAdmin(permissions.BasePermission):
    """Only accounts or admin can access"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in [
            'admin', 'accounts'
        ]