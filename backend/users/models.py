from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

class User(AbstractUser):
    USER_ROLES = (
        ('user', 'User'),
        ('technician', 'Technician'),
        ('manager', 'Manager'),
        ('accounts', 'Accounts'),
        ('admin', 'Admin'),
    )
    
    role = models.CharField(max_length=20, choices=USER_ROLES, default='user')
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    
    # Department
    department = models.ForeignKey(
        'Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='members'
    )
    
    # Account activation
    is_activated = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activated_users'
    )
    
    # Preferences
    preferences = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"
    
    def activate(self, admin_user):
        self.is_activated = True
        self.is_active = True
        self.activated_at = timezone.now()
        self.activated_by = admin_user
        self.save()
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['role', 'is_activated']),
        ]


class Department(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    email = models.EmailField(unique=True)
    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_departments',  # FIXED - was clashing
        limit_choices_to={'role__in': ['manager', 'admin']}
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class ClientProfile(models.Model):
    """
    Snapshot table for client (role=user) registration details.
    Keeps auditable signup metadata separate from auth user records.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='client_profile',
    )
    registration_email = models.EmailField()
    registration_phone = models.CharField(max_length=20, blank=True)
    registration_address = models.TextField(blank=True)
    registration_username = models.CharField(max_length=150)
    registration_full_name = models.CharField(max_length=255, blank=True)
    registration_role = models.CharField(max_length=20, default='user')
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'ClientProfile - {self.registration_email}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['registration_email']),
            models.Index(fields=['created_at']),
        ]


class Client(models.Model):
    """
    Canonical client record.
    Keeps one row per external customer and links all tickets/job-cards to it.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='client_account',
        limit_choices_to={'role': 'user'},
    )
    full_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.email

    class Meta:
        db_table = 'clients'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['created_at']),
        ]


class ClientWorkItem(models.Model):
    """
    Unified ledger row for any client-facing workload item (ticket or job-card).
    This is the single searchable place for client operations history.
    """
    ITEM_TYPE_CHOICES = (
        ('ticket', 'Ticket'),
        ('job', 'Job Card'),
    )

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='work_items',
    )
    item_type = models.CharField(max_length=10, choices=ITEM_TYPE_CHOICES)
    ticket = models.OneToOneField(
        'tickets.SupportTicket',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='client_work_item',
    )
    job_card = models.OneToOneField(
        'callogs.CallLog',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='client_work_item',
    )
    reference_number = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=40, blank=True)
    priority = models.CharField(max_length=20, blank=True)
    assigned_technician = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_client_work_items',
        limit_choices_to={'role__in': ['technician', 'manager', 'admin']},
    )
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_client_work_items',
        limit_choices_to={'role__in': ['technician', 'manager', 'admin']},
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_client_work_items',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    source_created_at = models.DateTimeField(null=True, blank=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.item_type}:{self.reference_number}'

    class Meta:
        db_table = 'client_work_items'
        ordering = ['-source_created_at', '-created_at']
        indexes = [
            models.Index(fields=['item_type', 'status']),
            models.Index(fields=['reference_number']),
            models.Index(fields=['source_created_at']),
        ]


class LeaveRequest(models.Model):
    LEAVE_TYPE_CHOICES = (
        ('annual', 'Annual Leave'),
        ('sick', 'Sick Leave'),
        ('compassionate', 'Compassionate Leave'),
        ('unpaid', 'Unpaid Leave'),
        ('day_off', 'Just a day off'),
        ('other', 'Other'),
    )

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    )

    requester = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='leave_requests',
    )
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES, default='annual')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    contact_phone = models.CharField(max_length=20, blank=True)
    handover_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    manager_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_leave_requests',
        limit_choices_to={'role__in': ['manager', 'admin']},
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'LeaveRequest<{self.requester_id}> {self.start_date} -> {self.end_date}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'start_date']),
            models.Index(fields=['requester', 'created_at']),
        ]


class Notification(models.Model):
    """
    In-app notification delivered to a single authenticated user.
    """
    CATEGORY_CHOICES = (
        ('ticket_feedback', 'Ticket Feedback'),
        ('system', 'System'),
    )

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    title = models.CharField(max_length=160)
    message = models.TextField()
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='system')
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f'Notification<{self.recipient_id}> {self.title}'

    class Meta:
        ordering = ['-created_at']
