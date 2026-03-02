from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'departments', views.DepartmentViewSet, basename='department')
router.register(r'notifications', views.NotificationViewSet, basename='notification')

urlpatterns = [
    # PUBLIC endpoints - no authentication required
    path('users/register/', views.RegisterView.as_view(), name='register'),
    path('users/me/', views.UserProfileView.as_view(), name='me'),
    path('profile/', views.UserProfileView.as_view(), name='profile'),
    path('change-password/', views.PasswordChangeView.as_view(), name='change-password'),
    
    # Router URLs
    path('', include(router.urls)),
]
