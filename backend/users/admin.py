# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Department, ClientProfile, Notification


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'role', 'is_activated', 'is_active', 'created_at']
    list_filter = ['role', 'is_activated', 'is_active', 'department']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('role', 'phone', 'address', 'avatar', 'department')}),
        ('Activation', {'fields': ('is_activated', 'activated_at', 'activated_by')}),
        ('Preferences', {'fields': ('preferences',)}),
    )
    
    readonly_fields = ['activated_at', 'activated_by', 'created_at', 'updated_at']


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'manager', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'email']


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ['registration_email', 'registration_full_name', 'registration_username', 'source_ip', 'created_at']
    search_fields = ['registration_email', 'registration_full_name', 'registration_username']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'title', 'category', 'is_read', 'created_at', 'read_at']
    list_filter = ['category', 'is_read', 'created_at']
    search_fields = ['recipient__email', 'recipient__username', 'title', 'message']
    readonly_fields = ['created_at', 'read_at']
