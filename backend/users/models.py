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
