from django.contrib import admin
from .models import ReportSchedule

@admin.register(ReportSchedule)
class ReportScheduleAdmin(admin.ModelAdmin):
    list_display = ('name', 'interval', 'is_active', 'last_sent_at', 'created_by')
    list_filter = ('interval', 'is_active')
    search_fields = ('name',)
