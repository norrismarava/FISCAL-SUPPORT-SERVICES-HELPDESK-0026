from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView
from users.auth_views import EmailOrUsernameTokenObtainPairView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # JWT Auth tokens
    path('api/auth/token/', EmailOrUsernameTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/token/blacklist/', TokenBlacklistView.as_view(), name='token_blacklist'),

    # Authentication & Users
    path('api/auth/', include('users.urls')),
    
    # Support Tickets
    path('api/tickets/', include('tickets.urls')),
    
    # Call Logs / Job Cards
    path('api/call-logs/', include('callogs.urls')),
    
    # Content Management
    path('api/content/', include('content.urls')),
    
    # Newsletter
    path('api/newsletter/', include('newsletter.urls')),
    
    # Dashboard
    path('api/dashboard/', include('dashboard.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
