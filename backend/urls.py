from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView
from users.auth_views import EmailOrUsernameTokenObtainPairView
from dashboard import views as dashboard_views

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
    # Fallback direct route for report export
    path('api/dashboard/reports/export/', dashboard_views.export_report, name='dashboard-export-report-direct'),
    path('api/dashboard/export/', dashboard_views.export_report, name='dashboard-export-report-alias'),
    path('api/reports/export/', dashboard_views.export_report, name='reports-export-root-alias'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
