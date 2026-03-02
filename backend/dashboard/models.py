from django.conf import settings
from django.db import models


class ReportSchedule(models.Model):
    INTERVAL_CHOICES = (
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    )

    name = models.CharField(max_length=120, unique=True)
    interval = models.CharField(max_length=20, choices=INTERVAL_CHOICES, default='daily')
    recipients = models.JSONField(default=list, blank=True)
    include_fields = models.JSONField(default=list, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_report_schedules'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name} ({self.interval})'

    class Meta:
        ordering = ['name']
