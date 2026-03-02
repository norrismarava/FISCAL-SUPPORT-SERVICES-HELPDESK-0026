# callogs/admin.py
from django.contrib import admin
from .models import CallLog, EngineerComment, CallLogActivity


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = ['job_number', 'customer_name', 'status', 'assigned_technician', 'amount_charged', 'created_at']
    list_filter = ['status', 'job_type', 'fault_type']
    search_fields = ['job_number', 'customer_name', 'customer_email']
    readonly_fields = ['job_id', 'job_number', 'created_at', 'updated_at']