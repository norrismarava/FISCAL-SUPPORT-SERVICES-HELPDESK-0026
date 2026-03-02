# backend/dashboard/permissions.py
from rest_framework import permissions

class IsStaffUser(permissions.BasePermission):
    """Only staff can access dashboard"""
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in [
            'admin', 'manager', 'technician', 'accounts'
        ]


class IsReportAuthorized(permissions.BasePermission):
    """Managers, accounts, and admins can generate/schedule reports."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in [
            'admin', 'manager', 'accounts'
        ]
