from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from . import views

router = DefaultRouter()
router.register(r'service-types', views.ServiceTypeViewSet, basename='service-type')
router.register(r'canned-responses', views.CannedResponseViewSet, basename='canned-response')
router.register(r'', views.SupportTicketViewSet, basename='ticket')

# Nested routers for comments and attachments
tickets_router = routers.NestedDefaultRouter(router, r'', lookup='ticket')
tickets_router.register(r'comments', views.TicketCommentViewSet, basename='ticket-comment')
tickets_router.register(r'attachments', views.TicketAttachmentViewSet, basename='ticket-attachment')

urlpatterns = [
    # Public ticket submission
    path('public/submit/', views.PublicTicketSubmissionView.as_view(), name='public-ticket-submit'),
    path('public/status/', views.PublicTicketStatusView.as_view(), name='public-ticket-status'),
    
    # Router URLs
    path('', include(router.urls)),
    path('', include(tickets_router.urls)),
]
