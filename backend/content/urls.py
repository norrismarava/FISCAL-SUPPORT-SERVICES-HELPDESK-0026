from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from . import views

router = DefaultRouter()
router.register(r'blog/categories', views.BlogCategoryViewSet, basename='blog-category')
router.register(r'blog/posts', views.BlogPostViewSet, basename='blog-post')
router.register(r'faq/categories', views.FAQCategoryViewSet, basename='faq-category')
router.register(r'faq', views.FAQViewSet, basename='faq')
router.register(r'services', views.ServiceViewSet, basename='service')

# Nested router for service resources
service_router = routers.NestedDefaultRouter(router, r'services', lookup='service')
service_router.register(r'resources', views.ServiceResourceViewSet, basename='service-resource')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(service_router.urls)),
]