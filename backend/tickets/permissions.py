# backend/tickets/permissions.py
from rest_framework import permissions

class IsTicketOwnerOrStaff(permissions.BasePermission):
    """Allow ticket owners or staff to access tickets"""
    
    def has_object_permission(self, request, view, obj):
        # Staff can access any ticket
        if request.user.role in ['admin', 'manager', 'technician', 'accounts']:
            return True
        # Owner can access their own ticket
        return obj.created_by == request.user


class IsStaffOnly(permissions.BasePermission):
    """Only staff members can access"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in [
            'admin', 'manager', 'technician', 'accounts'
        ]


class IsAdminOnly(permissions.BasePermission):
    """Only admins can access"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'