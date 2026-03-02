from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from .models import User, Department, ClientProfile, Notification


class DepartmentSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    
    class Meta:
        model = Department
        fields = [
            'id', 'name', 'description', 'email', 
            'manager', 'manager_name', 'is_active', 'created_at'
        ]
        read_only_fields = ['created_at']


class UserSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    activated_by_name = serializers.CharField(source='activated_by.get_full_name', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'phone', 'address', 'avatar', 'department', 'department_name',
            'is_activated', 'is_active', 'activated_at', 'activated_by', 'activated_by_name',
            'preferences', 'date_joined', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'is_activated', 'activated_at', 'activated_by', 
            'date_joined', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }


class ClientProfileSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    user_active = serializers.BooleanField(source='user.is_active', read_only=True)
    user_activated = serializers.BooleanField(source='user.is_activated', read_only=True)

    class Meta:
        model = ClientProfile
        fields = [
            'id',
            'user_id',
            'registration_full_name',
            'registration_email',
            'registration_phone',
            'registration_address',
            'registration_username',
            'registration_role',
            'source_ip',
            'user_agent',
            'user_active',
            'user_activated',
            'created_at',
            'updated_at',
        ]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id',
            'title',
            'message',
            'category',
            'link',
            'is_read',
            'read_at',
            'created_at',
        ]
        read_only_fields = ['id', 'title', 'message', 'category', 'link', 'created_at', 'read_at']


class RegisterSerializer(serializers.ModelSerializer):
    """
    Registration serializer - creates inactive users pending admin activation
    """
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        validators=[validate_password]
    )
    password2 = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'password2',
            'first_name', 'last_name', 'phone', 'address', 'role'
        ]
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})

        # Allow self-registration by selected role.
        # Clients (role=user) are auto-activated; operational roles remain pending activation.
        allowed_roles = ['admin', 'technician', 'manager', 'accounts', 'user']
        if attrs.get('role') not in allowed_roles:
            attrs['role'] = 'user'
        
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')

        role = validated_data.get('role', 'user')
        is_client = role == 'user'

        # Clients are activated immediately; internal roles remain pending admin activation.
        user = User.objects.create(
            **validated_data,
            is_active=True if is_client else False,
            is_activated=True if is_client else False
        )
        user.set_password(password)
        user.save()

        if is_client:
            request = self.context.get('request')
            source_ip = None
            user_agent = ''
            if request:
                xff = (request.META.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip()
                source_ip = xff or request.META.get('REMOTE_ADDR')
                user_agent = request.META.get('HTTP_USER_AGENT', '') or ''

            ClientProfile.objects.update_or_create(
                user=user,
                defaults={
                    'registration_email': user.email,
                    'registration_phone': user.phone or '',
                    'registration_address': user.address or '',
                    'registration_username': user.username,
                    'registration_full_name': user.get_full_name() or '',
                    'registration_role': user.role,
                    'source_ip': source_ip,
                    'user_agent': user_agent,
                }
            )
        
        return user


class UserActivationSerializer(serializers.Serializer):
    """Activate user account"""
    user_id = serializers.IntegerField()
    
    def validate_user_id(self, value):
        try:
            user = User.objects.get(id=value)
            if user.is_activated:
                raise serializers.ValidationError("User is already activated.")
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")
        return value
    
    def save(self):
        user = User.objects.get(id=self.validated_data['user_id'])
        admin_user = self.context['request'].user
        user.activate(admin_user)
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    """User profile with full details"""
    department_details = DepartmentSerializer(source='department', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'phone', 'address', 'avatar', 
            'department', 'department_details', 'preferences',
            'is_activated', 'is_active', 'date_joined', 'created_at'
        ]
        read_only_fields = [
            'username', 'email', 'role', 'is_activated', 
            'is_active', 'date_joined', 'created_at'
        ]


class PasswordChangeSerializer(serializers.Serializer):
    """Change password for authenticated users"""
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    new_password2 = serializers.CharField(required=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": "Password fields didn't match."})
        return attrs
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value
    
    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user
