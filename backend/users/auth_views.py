from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.exceptions import AuthenticationFailed

User = get_user_model()
INTERNAL_ROLES = {'admin', 'manager', 'technician', 'accounts'}


class EmailOrUsernameTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Allow login with either email or username in the `username` field.
    Also normalizes legacy client users (role=user) to active/activated.
    """

    def validate(self, attrs):
        identifier = (attrs.get(self.username_field) or '').strip()
        matched_user = None

        if identifier:
            if '@' in identifier:
                matched_user = User.objects.filter(email__iexact=identifier).first()
            if not matched_user:
                matched_user = User.objects.filter(username__iexact=identifier).first()
            if matched_user:
                attrs[self.username_field] = getattr(matched_user, self.username_field)

        # Backward-compatible fix for earlier client registrations that may not be activated.
        if matched_user and matched_user.role == 'user' and (not matched_user.is_active or not matched_user.is_activated):
            matched_user.is_active = True
            matched_user.is_activated = True
            matched_user.save(update_fields=['is_active', 'is_activated'])

        try:
            return super().validate(attrs)
        except AuthenticationFailed:
            if matched_user and matched_user.role in INTERNAL_ROLES and (not matched_user.is_active or not matched_user.is_activated):
                raise AuthenticationFailed('Account pending activation. Please contact an administrator.')
            raise


class EmailOrUsernameTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailOrUsernameTokenObtainPairSerializer
