from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView
from users.auth_views import EmailOrUsernameTokenObtainPairView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # JWT Auth endpoints
    path('api/auth/token/', EmailOrUsernameTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/token/blacklist/', TokenBlacklistView.as_view(), name='token_blacklist'),

    # App endpoints - FIXED to match frontend
    path('api/auth/', include('users.urls')),        # was api/users/
    path('api/tickets/', include('tickets.urls')),
    path('api/call-logs/', include('callogs.urls')), # was api/callogs/
    path('api/content/', include('content.urls')),
    path('api/newsletter/', include('newsletter.urls')),
    path('api/dashboard/', include('dashboard.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
