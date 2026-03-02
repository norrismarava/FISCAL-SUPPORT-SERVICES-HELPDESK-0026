from rest_framework import generics, viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings

from .models import Department, ClientProfile
from .serializers import (
    UserSerializer, RegisterSerializer, UserProfileSerializer,
    UserActivationSerializer, PasswordChangeSerializer, DepartmentSerializer,
    ClientProfileSerializer,
    NotificationSerializer,
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
        if self.action in ['list', 'retrieve', 'pending_activation', 'activate', 'deactivate', 'clients']:
            permission_classes = [IsAuthenticated, IsAdminOrManager]
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
