from rest_framework import generics, viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.contrib.auth import get_user_model
from django.db import models
from django.core.mail import send_mail
from django.conf import settings

from .models import Department, ClientProfile, Client, LeaveRequest, Notification
from .serializers import (
    UserSerializer, RegisterSerializer, UserProfileSerializer,
    UserActivationSerializer, PasswordChangeSerializer, DepartmentSerializer,
    ClientProfileSerializer,
    ClientDirectorySerializer,
    NotificationSerializer,
    LeaveRequestSerializer,
)
from .permissions import IsAdmin, IsAdminOrManager
from django.utils import timezone

User = get_user_model()
ACTIVATABLE_ROLES = ['technician', 'accounts', 'manager', 'admin']
MANAGER_ACTIVATABLE_ROLES = ['technician', 'accounts']


class RegisterView(generics.CreateAPIView):
    """
    User registration endpoint - Creates inactive users pending admin activation
    """
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer
    
    def perform_create(self, serializer):
        user = serializer.save()

        # Internal staff registrations require admin review.
        if user.role in ACTIVATABLE_ROLES:
            admins = User.objects.filter(role='admin', is_active=True)
            admin_emails = [admin.email for admin in admins]
            if admin_emails:
                send_mail(
                    subject='New User Registration - Awaiting Activation',
                    message=f'A new user has registered: {user.get_full_name()} ({user.email}). '
                            f'Role: {user.get_role_display()}. Please review and activate their account.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=admin_emails,
                    fail_silently=True,
                )
        
        return user


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Get and update authenticated user's profile
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = UserProfileSerializer
    
    def get_object(self):
        return self.request.user


class PasswordChangeView(generics.GenericAPIView):
    """
    Change password for authenticated users
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = PasswordChangeSerializer
    
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response({
            'message': 'Password changed successfully.'
        }, status=status.HTTP_200_OK)


class UserViewSet(viewsets.ModelViewSet):
    """
    User management endpoints.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = (IsAuthenticated, IsAdmin)
    filterset_fields = ['role', 'is_activated', 'is_active', 'department']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['created_at', 'username']
    ordering = ['-created_at']

    def get_permissions(self):
        """
        Managers can view users and activate/deactivate permitted internal accounts.
        All other user-management operations remain admin-only.
        """
        if self.action == 'technicians':
            permission_classes = [IsAuthenticated]
        elif self.action in ['list', 'retrieve', 'pending_activation', 'activate', 'deactivate', 'clients']:
            permission_classes = [IsAuthenticated, IsAdminOrManager]
        elif self.action == 'client_directory':
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAuthenticated, IsAdmin]
        return [permission() for permission in permission_classes]
    
    @action(detail=False, methods=['get'])
    def pending_activation(self, request):
        """Get users pending activation"""
        roles = request.query_params.getlist('role') or request.query_params.getlist('role[]')
        if not roles:
            roles = ACTIVATABLE_ROLES
        if request.user.role == 'manager':
            roles = [role for role in roles if role in MANAGER_ACTIVATABLE_ROLES]
        users = User.objects.filter(is_activated=False, role__in=roles)
        serializer = self.get_serializer(users, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a user account"""
        user = self.get_object()

        if user.role not in ACTIVATABLE_ROLES:
            return Response(
                {'error': f'Only {", ".join(ACTIVATABLE_ROLES)} users can be activated from this workflow.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if request.user.role == 'manager' and user.role not in MANAGER_ACTIVATABLE_ROLES:
            return Response(
                {'error': 'Managers can only activate technician and accounts users.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if user.is_active and user.is_activated:
            return Response(
                {'error': 'User is already activated.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.activate(request.user)
        
        # Send activation email to user
        send_mail(
            subject='Your Account Has Been Activated',
            message=f'Hello {user.get_full_name()},\n\n'
                    f'Your account has been activated by an administrator. '
                    f'You can now log in to the FSSHELPDESK system.\n\n'
                    f'Best regards,\nFSSHELPDESK Team',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
        
        serializer = self.get_serializer(user)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a user account"""
        user = self.get_object()
        if request.user.id == user.id:
            return Response(
                {'error': 'You cannot deactivate your own account.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if request.user.role == 'manager' and user.role not in MANAGER_ACTIVATABLE_ROLES:
            return Response(
                {'error': 'Managers can only deactivate technician and accounts users.'},
                status=status.HTTP_403_FORBIDDEN
            )
        user.is_active = False
        user.is_activated = False
        user.activated_at = None
        user.activated_by = None
        user.save()
        
        serializer = self.get_serializer(user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def technicians(self, request):
        """Get all technicians for assignment"""
        if request.user.role not in ['admin', 'manager', 'accounts', 'technician']:
            return Response(
                {'error': 'You are not allowed to view technicians.'},
                status=status.HTTP_403_FORBIDDEN
            )

        technicians = User.objects.filter(
            role__in=['technician', 'admin'],
            is_active=True
        )
        serializer = self.get_serializer(technicians, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def clients(self, request):
        """List registered client profiles for managers and admins."""
        queryset = ClientProfile.objects.select_related('user').all()
        serializer = ClientProfileSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def client_directory(self, request):
        """
        Search canonical client records for fast job/ticket autofill.
        Accessible to authenticated users.
        """
        query = (request.query_params.get('q') or '').strip()
        limit = request.query_params.get('limit', 20)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 100))

        queryset = Client.objects.filter(is_active=True)
        if query:
            queryset = queryset.filter(
                models.Q(full_name__icontains=query)
                | models.Q(company_name__icontains=query)
                | models.Q(email__icontains=query)
                | models.Q(phone__icontains=query)
            )

        queryset = queryset.order_by('company_name', 'full_name', 'email')[:limit]
        serializer = ClientDirectorySerializer(queryset, many=True)
        return Response(serializer.data)


class DepartmentViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for departments
    """
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = (IsAuthenticated,)
    filterset_fields = ['is_active']
    search_fields = ['name']


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Authenticated user notifications for bell/dropdown.
    """
    serializer_class = NotificationSerializer
    permission_classes = (IsAuthenticated,)
    ordering = ['-created_at']

    def get_queryset(self):
        return self.request.user.notifications.all()

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'count': count})

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=['is_read', 'read_at'])
        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        now = timezone.now()
        self.get_queryset().filter(is_read=False).update(is_read=True, read_at=now)
        return Response({'message': 'All notifications marked as read.'}, status=status.HTTP_200_OK)


class LeaveRequestViewSet(viewsets.ModelViewSet):
    """
    Leave requests:
    - Staff users create their own requests.
    - Managers/Admins can see all and review status.
    """
    serializer_class = LeaveRequestSerializer
    permission_classes = (IsAuthenticated,)
    filterset_fields = ['status', 'leave_type']
    search_fields = ['requester__first_name', 'requester__last_name', 'requester__email', 'reason']
    ordering_fields = ['created_at', 'start_date', 'end_date', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        queryset = LeaveRequest.objects.select_related('requester', 'reviewed_by').all()
        if user.role in ['admin', 'manager']:
            return queryset
        return queryset.filter(requester=user)

    def perform_create(self, serializer):
        requester = self.request.user
        if requester.role == 'user':
            raise PermissionDenied('Client users cannot submit internal leave requests.')

        leave_request = serializer.save(
            requester=requester,
            status='pending',
            manager_notes='',
            reviewed_by=None,
            reviewed_at=None,
        )

        manager_recipients = User.objects.filter(
            role='manager',
            is_active=True,
            is_activated=True,
        )
        if not manager_recipients.exists():
            manager_recipients = User.objects.filter(
                role='admin',
                is_active=True,
                is_activated=True,
            )

        notifications = [
            Notification(
                recipient=recipient,
                title='New Leave Request',
                message=(
                    f'{requester.get_full_name() or requester.username} submitted '
                    f'a {leave_request.get_leave_type_display().lower()} request '
                    f'for {leave_request.start_date} to {leave_request.end_date}.'
                ),
                category='system',
                link='/profile',
            )
            for recipient in manager_recipients
            if recipient.id != requester.id
        ]
        if notifications:
            Notification.objects.bulk_create(notifications)

    def perform_update(self, serializer):
        user = self.request.user
        instance = self.get_object()

        if user.role not in ['admin', 'manager']:
            raise PermissionDenied('Only managers or admins can review leave requests.')

        previous_status = instance.status
        incoming_status = serializer.validated_data.get('status', instance.status)
        manager_notes = (serializer.validated_data.get('manager_notes', instance.manager_notes) or '').strip()

        if incoming_status in ['approved', 'rejected'] and not manager_notes:
            raise ValidationError({'manager_notes': 'Manager comment is required when approving or rejecting leave.'})

        leave_request = serializer.save(manager_notes=manager_notes)
        if leave_request.status != previous_status and leave_request.status in ['approved', 'rejected', 'cancelled']:
            leave_request.reviewed_by = user
            leave_request.reviewed_at = timezone.now()
            leave_request.save(update_fields=['reviewed_by', 'reviewed_at', 'updated_at'])

            note_suffix = f' Comment: {manager_notes}' if manager_notes else ''
            Notification.objects.create(
                recipient=leave_request.requester,
                title='Leave Request Update',
                message=(
                    f'Your leave request ({leave_request.start_date} to {leave_request.end_date}) '
                    f'was {leave_request.status}.{note_suffix}'
                ),
                category='system',
                link='/profile',
            )

            # For approved sick leave, notify all internal staff of availability impact
            # without exposing manager notes/private comments.
            if leave_request.status == 'approved' and leave_request.leave_type == 'sick':
                staff_recipients = User.objects.filter(
                    role__in=['admin', 'manager', 'technician', 'accounts'],
                    is_active=True,
                    is_activated=True,
                ).exclude(id__in=[leave_request.requester_id, user.id])

                requester_name = leave_request.requester.get_full_name() or leave_request.requester.username
                broadcast_notifications = [
                    Notification(
                        recipient=recipient,
                        title='Staff Availability Notice',
                        message=(
                            f'{requester_name} is on approved sick leave '
                            f'from {leave_request.start_date} to {leave_request.end_date}.'
                        ),
                        category='system',
                        link='/profile',
                    )
                    for recipient in staff_recipients
                ]
                if broadcast_notifications:
                    Notification.objects.bulk_create(broadcast_notifications)
