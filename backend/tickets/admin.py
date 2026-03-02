# tickets/admin.py
from django.contrib import admin
from .models import (
    ServiceType, SupportTicket, TicketComment, TicketAttachment,
    CannedResponse, TicketAuditLog, TicketBacklogEntry
)


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ['ticket_number', 'ticket_id', 'company_name', 'email', 'status', 'priority', 'assigned_to', 'created_at']
    list_filter = ['status', 'priority', 'service_type', 'is_public_submission']
    search_fields = ['ticket_number', 'ticket_id', 'company_name', 'email', 'subject']
    readonly_fields = ['ticket_number', 'ticket_id', 'created_at', 'updated_at']


@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'author', 'is_internal', 'created_at']
    list_filter = ['is_internal']
    search_fields = ['content']


@admin.register(TicketAttachment)
class TicketAttachmentAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'filename', 'file_type', 'file_size', 'uploaded_at']
    list_filter = ['file_type', 'uploaded_at']
    search_fields = ['filename']


@admin.register(CannedResponse)
class CannedResponseAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'is_active', 'created_by', 'created_at']
    list_filter = ['category', 'is_active']
    search_fields = ['title', 'content']


@admin.register(TicketAuditLog)
class TicketAuditLogAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'event_type', 'user', 'created_at']
    list_filter = ['event_type', 'created_at']
    search_fields = ['description']
    readonly_fields = ['ticket', 'user', 'event_type', 'description', 'metadata', 'created_at']


@admin.register(TicketBacklogEntry)
class TicketBacklogEntryAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'is_waiting', 'reason', 'enqueued_at', 'dequeued_at', 'dequeued_to']
    list_filter = ['is_waiting', 'reason']
    search_fields = ['ticket__ticket_number', 'ticket__company_name', 'ticket__email']
