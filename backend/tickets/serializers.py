from rest_framework import serializers
from django.utils import timezone
from django.db import models
from callogs.models import CallLog
from .models import (
    ServiceType, SupportTicket, TicketComment,
    TicketAttachment, TicketRateLimit, CannedResponse, TicketAuditLog
)
from users.serializers import UserSerializer


class ServiceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceType
        fields = ['id', 'name', 'description', 'is_active', 'created_at']
        read_only_fields = ['created_at']


class TicketAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = TicketAttachment
        fields = [
            'id', 'file', 'file_url', 'filename', 
            'file_size', 'file_type', 'uploaded_at'
        ]
        read_only_fields = ['uploaded_at', 'file_size', 'file_type', 'filename']
    
    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None
    
    def validate_file(self, value):
        # Validate file type
        allowed_extensions = ['pdf', 'jpg', 'jpeg', 'png']
        ext = value.name.split('.')[-1].lower()
        
        if ext not in allowed_extensions:
            raise serializers.ValidationError(
                f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
            )
        
        # Validate file size (max 5MB)
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("File size cannot exceed 5MB.")
        
        return value


class TicketCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)
    author_role = serializers.CharField(source='author.role', read_only=True)
    
    class Meta:
        model = TicketComment
        fields = [
            'id', 'ticket', 'author', 'author_name', 'author_role',
            'content', 'is_internal', 'created_at', 'updated_at'
        ]
        read_only_fields = ['ticket', 'author', 'created_at', 'updated_at']


class TicketAuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = TicketAuditLog
        fields = ['id', 'event_type', 'description', 'metadata', 'created_at', 'user', 'user_name']
        read_only_fields = ['created_at']


class CannedResponseSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = CannedResponse
        fields = [
            'id', 'title', 'content', 'category', 'is_active',
            'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']


class SupportTicketListSerializer(serializers.ModelSerializer):
    """Serializer for ticket list view"""
    service_type_name = serializers.CharField(source='service_type.name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    comments_count = serializers.IntegerField(source='comments.count', read_only=True)
    sla_remaining_seconds = serializers.SerializerMethodField()
    
    class Meta:
        model = SupportTicket
        fields = [
            'id', 'ticket_id', 'ticket_number', 'company_name', 'email', 'subject',
            'service_type', 'service_type_name', 'status', 'priority',
            'assigned_to', 'assigned_to_name', 'is_public_submission',
            'comments_count', 'region', 'sla_due_at', 'sla_breached_at', 'sla_remaining_seconds',
            'merged_into', 'created_at', 'updated_at'
        ]
        read_only_fields = ['ticket_id', 'ticket_number', 'created_at', 'updated_at']

    def get_sla_remaining_seconds(self, obj):
        if not obj.sla_due_at or obj.status == 'solved':
            return None
        return int((obj.sla_due_at - timezone.now()).total_seconds())


class SupportTicketDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed ticket view"""
    service_type_details = ServiceTypeSerializer(source='service_type', read_only=True)
    user_details = UserSerializer(source='user', read_only=True)
    assigned_to_details = UserSerializer(source='assigned_to', read_only=True)
    comments = serializers.SerializerMethodField()
    attachments = TicketAttachmentSerializer(many=True, read_only=True)
    audit_trail = serializers.SerializerMethodField()
    sla_remaining_seconds = serializers.SerializerMethodField()
    technicians_helped = serializers.SerializerMethodField()
    related_jobs = serializers.SerializerMethodField()
    
    class Meta:
        model = SupportTicket
        fields = [
            'id', 'ticket_id', 'ticket_number', 'company_name', 'email', 'phone', 
            'contact_person', 'user', 'user_details',
            'service_type', 'service_type_details', 'subject', 'message',
            'assigned_to', 'assigned_to_details', 'status', 'priority',
            'is_public_submission', 'ip_address',
            'comments', 'attachments', 'audit_trail',
            'region', 'sla_due_at', 'sla_breached_at', 'sla_remaining_seconds', 'merged_into',
            'technicians_helped', 'related_jobs',
            'csat_score', 'csat_feedback', 'csat_submitted_at',
            'created_at', 'updated_at', 'solved_at', 'reopened_at'
        ]
        read_only_fields = [
            'ticket_id', 'ticket_number', 'user', 'ip_address', 'is_public_submission',
            'created_at', 'updated_at', 'solved_at', 'reopened_at'
        ]

    def get_sla_remaining_seconds(self, obj):
        if not obj.sla_due_at or obj.status == 'solved':
            return None
        return int((obj.sla_due_at - timezone.now()).total_seconds())

    def get_comments(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        qs = obj.comments.all()

        if not user or not user.is_authenticated or user.role == 'user':
            qs = qs.filter(is_internal=False)

        return TicketCommentSerializer(qs, many=True).data

    def get_audit_trail(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated or user.role == 'user':
            return []
        return TicketAuditLogSerializer(obj.audit_logs.all(), many=True).data

    def get_technicians_helped(self, obj):
        helped = []
        seen = set()

        if obj.assigned_to and obj.assigned_to.role in ['technician', 'manager', 'admin']:
            name = obj.assigned_to.get_full_name() or obj.assigned_to.username
            if name and name not in seen:
                seen.add(name)
                helped.append(name)

        for comment in obj.comments.select_related('author').all():
            author = comment.author
            if author and author.role in ['technician', 'manager', 'admin']:
                name = author.get_full_name() or author.username
                if name and name not in seen:
                    seen.add(name)
                    helped.append(name)
        return helped

    def get_related_jobs(self, obj):
        jobs = (
            CallLog.objects.filter(
                models.Q(related_ticket=obj) | models.Q(customer_email__iexact=obj.email)
            )
            .select_related('assigned_technician')
            .order_by('-created_at')[:20]
        )
        return [
            {
                'id': job.id,
                'job_number': job.job_number,
                'customer_name': job.customer_name,
                'customer_email': job.customer_email,
                'customer_phone': job.customer_phone,
                'fault_type': job.get_fault_type_display() if job.fault_type else '',
                'fault_description': job.fault_description,
                'job_type': job.get_job_type_display() if job.job_type else '',
                'status': job.get_status_display() if job.status else '',
                'booking_date': job.booking_date,
                'resolution_date': job.resolution_date,
                'time_start': job.time_start,
                'time_finish': job.time_finish,
                'billed_hours': job.billed_hours,
                'amount_charged': job.amount_charged,
                'currency': job.currency,
                'assigned_technician_name': job.assigned_technician.get_full_name() if job.assigned_technician else None,
                'created_at': job.created_at,
                'updated_at': job.updated_at,
            }
            for job in jobs
        ]


class PublicTicketSubmissionSerializer(serializers.ModelSerializer):
    """
    Serializer for public ticket submission (unauthenticated)
    Includes rate limiting and reCAPTCHA validation
    """
    recaptcha_token = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = SupportTicket
        fields = [
            'ticket_id', 'ticket_number', 'company_name', 'email', 'phone', 'contact_person',
            'service_type', 'region', 'subject', 'message', 'recaptcha_token'
        ]
        read_only_fields = ['ticket_id', 'ticket_number']
    
    def validate_recaptcha_token(self, value):
        """Validate reCAPTCHA token"""
        import requests
        from django.conf import settings
        
        secret_key = settings.RECAPTCHA_SECRET_KEY
        verify_url = 'https://www.google.com/recaptcha/api/siteverify'
        
        data = {
            'secret': secret_key,
            'response': value
        }
        
        response = requests.post(verify_url, data=data)
        result = response.json()
        
        if not result.get('success'):
            raise serializers.ValidationError("reCAPTCHA verification failed.")
        
        return value
    
    def validate(self, attrs):
        """Check rate limits"""
        request = self.context.get('request')
        ip_address = self.get_client_ip(request)
        email = attrs.get('email')
        
        # Check IP-based rate limit (3 per hour)
        self.check_ip_rate_limit(ip_address)
        
        # Check email-based rate limit (5 per day)
        self.check_email_rate_limit(email)
        
        return attrs


class PublicTicketStatusSerializer(serializers.ModelSerializer):
    """
    Public-safe serializer for ticket status checks (no internal comments/audit).
    """
    service_type_name = serializers.CharField(source='service_type.name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    related_jobs = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            'ticket_id',
            'ticket_number',
            'company_name',
            'email',
            'subject',
            'status',
            'priority',
            'service_type_name',
            'assigned_to_name',
            'created_at',
            'updated_at',
            'solved_at',
            'csat_score',
            'csat_feedback',
            'csat_submitted_at',
            'related_jobs',
        ]

    def get_related_jobs(self, obj):
        jobs = (
            CallLog.objects.filter(
                models.Q(related_ticket=obj) | models.Q(customer_email__iexact=obj.email)
            )
            .select_related('assigned_technician')
            .order_by('-created_at')[:20]
        )
        return [
            {
                'id': job.id,
                'job_number': job.job_number,
                'fault_type': job.get_fault_type_display() if job.fault_type else '',
                'status': job.get_status_display() if job.status else '',
                'assigned_technician_name': job.assigned_technician.get_full_name() if job.assigned_technician else None,
                'created_at': job.created_at,
                'updated_at': job.updated_at,
            }
            for job in jobs
        ]
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def check_ip_rate_limit(self, ip_address):
        """Check if IP has exceeded rate limit (3 submissions per hour)"""
        one_hour_ago = timezone.now() - timezone.timedelta(hours=1)
        
        recent_submissions = SupportTicket.objects.filter(
            ip_address=ip_address,
            created_at__gte=one_hour_ago
        ).count()
        
        if recent_submissions >= 3:
            raise serializers.ValidationError(
                "Rate limit exceeded. You can submit up to 3 tickets per hour."
            )
    
    def check_email_rate_limit(self, email):
        """Check if email has exceeded rate limit (5 submissions per day)"""
        one_day_ago = timezone.now() - timezone.timedelta(days=1)
        
        recent_submissions = SupportTicket.objects.filter(
            email=email,
            created_at__gte=one_day_ago
        ).count()
        
        if recent_submissions >= 5:
            raise serializers.ValidationError(
                "Rate limit exceeded. You can submit up to 5 tickets per day."
            )
    
    def create(self, validated_data):
        """Create public ticket submission"""
        validated_data.pop('recaptcha_token')  # Remove reCAPTCHA token
        
        request = self.context.get('request')
        validated_data['ip_address'] = self.get_client_ip(request)
        validated_data['is_public_submission'] = True
        validated_data['status'] = 'pending'
        
        ticket = SupportTicket.objects.create(**validated_data)
        return ticket


class AuthenticatedTicketCreateSerializer(serializers.ModelSerializer):
    """Serializer for authenticated users creating tickets"""
    assigned_to_name = serializers.SerializerMethodField()
    service_type = serializers.CharField()
    
    class Meta:
        model = SupportTicket
        fields = [
            'id', 'ticket_id', 'ticket_number', 'status', 'assigned_to', 'assigned_to_name',
            'company_name', 'email', 'phone', 'contact_person',
            'service_type', 'region', 'subject', 'message', 'priority'
        ]
        read_only_fields = ['id', 'ticket_id', 'ticket_number', 'status', 'assigned_to', 'assigned_to_name']

    def get_assigned_to_name(self, obj):
        tech = getattr(obj, 'assigned_to', None)
        if not tech:
            return None
        return tech.get_full_name() or tech.username

    def validate_service_type(self, value):
        """
        Accept either:
        - numeric service type id
        - service type name key (e.g. "support")
        If name does not exist, create a new active service type.
        """
        raw = str(value).strip()
        if not raw:
            raise serializers.ValidationError('Service type is required.')

        # ID path
        if raw.isdigit():
            service_type = ServiceType.objects.filter(id=int(raw), is_active=True).first()
            if service_type:
                return service_type
            raise serializers.ValidationError('Invalid service type selected.')

        # Name path: match by normalized text
        display_name = raw.replace('_', ' ').replace('-', ' ').strip()
        service_type = ServiceType.objects.filter(name__iexact=display_name).first()
        if service_type:
            if not service_type.is_active:
                service_type.is_active = True
                service_type.save(update_fields=['is_active'])
            return service_type

        # Create missing type so fallback options can be used immediately.
        return ServiceType.objects.create(name=display_name.title(), is_active=True)
    
    def create(self, validated_data):
        """Create ticket from authenticated user"""
        user = self.context['request'].user
        
        validated_data['user'] = user
        validated_data['is_public_submission'] = False
        validated_data['status'] = 'open'
        
        # Auto-fill from user profile if not provided
        if not validated_data.get('email'):
            validated_data['email'] = user.email
        if not validated_data.get('company_name'):
            validated_data['company_name'] = user.get_full_name()
        
        ticket = SupportTicket.objects.create(**validated_data)
        return ticket


class TicketUpdateSerializer(serializers.ModelSerializer):
    """Update ticket (status, priority, assignment)"""
    
    class Meta:
        model = SupportTicket
        fields = ['status', 'priority', 'assigned_to', 'subject', 'message', 'region']
    
    def update(self, instance, validated_data):
        # Track status change
        if 'status' in validated_data and validated_data['status'] == 'solved':
            instance.solved_at = timezone.now()
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance
