from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid

class ServiceType(models.Model):
    """Service types for ticket categorization"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class SupportTicket(models.Model):
    """
    External support tickets (can be submitted by public or authenticated users)
    """
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('open', 'Open'),
        ('unassigned', 'Unassigned'),
        ('solved', 'Solved'),
        ('reopened', 'Reopened'),
    )
    
    # Ticket identification
    ticket_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    ticket_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    
    # Submitter information (can be public or authenticated)
    company_name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    contact_person = models.CharField(max_length=255, blank=True)
    
    # If submitted by authenticated user
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='submitted_tickets'
    )
    
    # Ticket details
    service_type = models.ForeignKey(ServiceType, on_delete=models.SET_NULL, null=True)
    region = models.CharField(max_length=100, blank=True)
    subject = models.CharField(max_length=255, blank=True)
    message = models.TextField()
    
    # Assignment and status
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tickets',
        limit_choices_to={'role__in': ['technician', 'manager', 'admin']}
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    merged_into = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='merged_children'
    )
    
    # Public submission tracking
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_public_submission = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    solved_at = models.DateTimeField(null=True, blank=True)
    reopened_at = models.DateTimeField(null=True, blank=True)
    sla_due_at = models.DateTimeField(null=True, blank=True)
    sla_breached_at = models.DateTimeField(null=True, blank=True)
    csat_score = models.PositiveSmallIntegerField(null=True, blank=True)
    csat_feedback = models.TextField(blank=True)
    csat_submitted_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        ref = self.ticket_number or str(self.ticket_id)
        return f"Ticket #{ref} - {self.company_name}"

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        # Generate human-friendly reference after first save when PK exists.
        if (creating or not self.ticket_number) and self.pk and not self.ticket_number:
            self.ticket_number = f'FSS{self.pk}'
            super().save(update_fields=['ticket_number'])
    
    def reopen(self):
        """Reopen a solved ticket"""
        self.status = 'reopened'
        self.reopened_at = timezone.now()
        self.save()
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['email']),
            models.Index(fields=['assigned_to']),
        ]


class TicketComment(models.Model):
    """Internal comments on support tickets"""
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    is_internal = models.BooleanField(default=True)  # Internal notes for staff only
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        ref = self.ticket.ticket_number or self.ticket.ticket_id
        return f"Comment by {self.author.username} on Ticket {ref}"
    
    class Meta:
        ordering = ['created_at']


class TicketAttachment(models.Model):
    """File attachments for support tickets"""
    ALLOWED_TYPES = ['pdf', 'jpg', 'jpeg', 'png']
    
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='ticket_attachments/%Y/%m/%d/')
    filename = models.CharField(max_length=255)
    file_size = models.IntegerField()
    file_type = models.CharField(max_length=10)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.filename
    
    class Meta:
        ordering = ['-uploaded_at']


class TicketRateLimit(models.Model):
    """Track public ticket submissions for rate limiting"""
    ip_address = models.GenericIPAddressField()
    email = models.EmailField()
    submission_count = models.IntegerField(default=1)
    first_submission = models.DateTimeField(auto_now_add=True)
    last_submission = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['ip_address', 'email']
        indexes = [
            models.Index(fields=['ip_address', 'last_submission']),
            models.Index(fields=['email', 'last_submission']),
        ]


class CannedResponse(models.Model):
    """Reusable ticket response templates."""
    title = models.CharField(max_length=120)
    content = models.TextField()
    category = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_canned_responses'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['title']


class TicketAuditLog(models.Model):
    """Immutable audit trail for ticket lifecycle events."""
    EVENT_TYPES = (
        ('created', 'Created'),
        ('auto_assigned', 'Auto Assigned'),
        ('updated', 'Updated'),
        ('status_changed', 'Status Changed'),
        ('merged', 'Merged'),
        ('comment_added', 'Comment Added'),
        ('attachment_added', 'Attachment Added'),
        ('reopened', 'Reopened'),
        ('solved', 'Solved'),
    )

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=30, choices=EVENT_TYPES)
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        ref = self.ticket.ticket_number or self.ticket.ticket_id
        return f'{self.event_type} - {ref}'

    class Meta:
        ordering = ['-created_at']


class TicketBacklogEntry(models.Model):
    """
    Waiting queue entry for tickets that could not be assigned due to thresholds.
    One active backlog record is maintained per ticket.
    """
    ticket = models.OneToOneField(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name='backlog_entry'
    )
    is_waiting = models.BooleanField(default=True, db_index=True)
    reason = models.CharField(max_length=100, blank=True, default='threshold_full')
    enqueued_at = models.DateTimeField(default=timezone.now, db_index=True)
    dequeued_at = models.DateTimeField(null=True, blank=True)
    dequeued_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dequeued_backlog_tickets',
        limit_choices_to={'role__in': ['technician', 'manager', 'admin']}
    )

    def __str__(self):
        ref = self.ticket.ticket_number or self.ticket.ticket_id
        state = 'waiting' if self.is_waiting else 'dequeued'
        return f'Backlog {state} - {ref}'

    class Meta:
        ordering = ['enqueued_at', 'id']
