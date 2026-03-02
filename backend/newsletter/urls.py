from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'subscribers', views.NewsletterSubscriberViewSet, basename='subscriber')
router.register(r'campaigns', views.NewsletterCampaignViewSet, basename='campaign')

urlpatterns = [
    # Public endpoints
    path('subscribe/', views.subscribe_newsletter, name='subscribe'),
    path('unsubscribe/', views.unsubscribe_newsletter, name='unsubscribe'),
    
    # Admin endpoints
    path('', include(router.urls)),
]