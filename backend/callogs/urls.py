from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from . import views

router = DefaultRouter()
router.register(r'', views.CallLogViewSet, basename='calllog')

# Nested router for engineer comments
calllog_router = routers.NestedDefaultRouter(router, r'', lookup='calllog')
calllog_router.register(r'comments', views.EngineerCommentViewSet, basename='calllog-comment')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(calllog_router.urls)),
]