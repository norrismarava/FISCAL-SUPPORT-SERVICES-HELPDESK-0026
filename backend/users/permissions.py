# users/permissions.py
from rest_framework import permissions


class IsAdmin(permissions.BasePermission):
    """Only admins can access"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'


class IsAdminOrManager(permissions.BasePermission):
    """Admins and managers can access"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['admin', 'manager']


# tickets/permissions.py
from rest_framework import permissions


class IsTicketOwnerOrStaff(permissions.BasePermission):
    """
    Ticket owner can read, staff can read/write
    """
    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # Staff have full access
        if user.role in ['admin', 'manager', 'technician']:
            return True
        
        # User can only view their own tickets
        if request.method in permissions.SAFE_METHODS:
            return obj.user == user
        
        return False


# callogs/permissions.py
from rest_framework import permissions


class IsStaffUser(permissions.BasePermission):
    """Only staff (technician, manager, accounts, admin) can access"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in [
            'technician', 'manager', 'accounts', 'admin'
        ]


class IsAccountsOrAdmin(permissions.BasePermission):
    """Only accounts and admin can access"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['accounts', 'admin']


# content/permissions.py
from rest_framework import permissions


class IsAdminUser(permissions.BasePermission):
    """Only admins can modify content"""
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.role == 'admin'


# newsletter/permissions.py
from rest_framework import permissions


class IsAdminUser(permissions.BasePermission):
    """Only admins can manage newsletters"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'