from django.db import models
from django.conf import settings
import uuid

class CallLog(models.Model):
    """
    Internal job cards/call logs for tracking work performed
    Often created from support tickets or direct requests
    """
    JOB_TYPE_CHOICES = (
        ('normal', 'Normal'),
        ('emergency', 'Emergency'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('complete', 'Complete'),
        ('cancelled', 'Cancelled'),
    )
    
    FAULT_TYPE_CHOICES = (
        ('license_tax_rate', 'License & Tax Rate'),
        ('tax_rate', 'Tax Rate'),
        ('inhouse_license', 'In-House License'),
        ('inhouse_license_reinstall', 'In-House License & Re-Installation'),
        ('makute_license_reinstall', 'Makute License & Re-Installation'),
        ('reinstallation', 'Re-Installation'),
        ('virtual_installation', 'Virtual Installation'),
        ('support', 'Support'),
        ('smartmini_new_install', 'Smart-Mini New Installation'),
        ('smartmini_license_renew', 'Smart Mini License Renewal'),
        ('makute_license_renewal', 'Makute License Renewal'),
    )
    
    CURRENCY_CHOICES = (
        ('USD', 'US Dollar'),
        ('ZWG', 'ZWG'),
        ('ZAR', 'South African Rand'),
    )

    PAYMENT_TERMS_CHOICES = (
        ('none', 'None'),
        ('partial', 'Partial Payment'),
        ('periodic', 'Periodic Payment'),
        ('lay_by', 'Lay-By Arrangement'),
        ('discount', 'Discount Applied'),
    )
    
    # Job identification
    job_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    job_number = models.CharField(max_length=50, unique=True, blank=True)
    
    # Customer information
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20)
    customer_address = models.TextField(blank=True)
    
    # Related ticket (if created from ticket)
    related_ticket = models.ForeignKey(
        'tickets.SupportTicket',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='call_logs'
    )
    
    # Job details
    job_type = models.CharField(max_length=20, choices=JOB_TYPE_CHOICES, default='normal')
    fault_type = models.CharField(max_length=40, choices=FAULT_TYPE_CHOICES)
    fault_description = models.TextField()
    resolution_notes = models.TextField(blank=True)
    
    # Financial information
    full_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    amount_deposited = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    amount_charged = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD')
    zimra_reference = models.CharField(max_length=100, blank=True)  # Tax reference
    invoice_number = models.CharField(max_length=100, blank=True)
    payment_terms_type = models.CharField(max_length=20, choices=PAYMENT_TERMS_CHOICES, default='none')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    special_terms_notes = models.TextField(blank=True)
    
    # Assignment and status
    assigned_technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_jobs',
        limit_choices_to={'role__in': ['technician', 'manager', 'admin']}
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Scheduling
    booking_date = models.DateField(null=True, blank=True)
    booking_time = models.TimeField(null=True, blank=True)
    resolution_date = models.DateField(null=True, blank=True)
    resolution_time = models.TimeField(null=True, blank=True)
    time_start = models.TimeField(null=True, blank=True)
    time_finish = models.TimeField(null=True, blank=True)
    billed_hours = models.CharField(max_length=20, blank=True)
    
    # Created by
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_jobs'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Job #{self.job_number or self.job_id} - {self.customer_name}"

    @property
    def balance_due(self):
        return (self.full_amount or 0) - (self.amount_deposited or 0)
    
    def save(self, *args, **kwargs):
        # Auto-generate job number if not set
        if not self.job_number:
            from django.utils import timezone
            date_str = timezone.now().strftime('%Y%m%d')
            count = CallLog.objects.filter(job_number__startswith=f'JOB-{date_str}').count()
            self.job_number = f'JOB-{date_str}-{count + 1:04d}'
        super().save(*args, **kwargs)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['assigned_technician', 'status']),
            models.Index(fields=['created_at']),
        ]


class EngineerComment(models.Model):
    """Engineer/technician comments on call logs"""
    call_log = models.ForeignKey(CallLog, on_delete=models.CASCADE, related_name='engineer_comments')
    engineer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Comment by {self.engineer.get_full_name()} on Job {self.call_log.job_number}"
    
    class Meta:
        ordering = ['created_at']


class CallLogActivity(models.Model):
    """Activity log for call logs"""
    ACTIVITY_TYPES = (
        ('created', 'Created'),
        ('assigned', 'Assigned'),
        ('status_changed', 'Status Changed'),
        ('updated', 'Updated'),
        ('comment_added', 'Comment Added'),
        ('completed', 'Completed'),
    )
    
    call_log = models.ForeignKey(CallLog, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    activity_type = models.CharField(max_length=30, choices=ACTIVITY_TYPES)
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.activity_type} - {self.call_log.job_number}"
    
    class Meta:
        verbose_name_plural = 'Call Log Activities'
        ordering = ['-created_at']

