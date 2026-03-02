from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'report-schedules', views.ReportScheduleViewSet, basename='report-schedule')

urlpatterns = [
    path('stats/', views.dashboard_stats, name='dashboard-stats'),
    path('search/', views.global_search, name='global-search'),
    path('reports/generate/', views.generate_report, name='generate-report'),
    path('reports/export/', views.export_report, name='export-report'),
    path('reports/secure-link/', views.create_secure_report_link, name='report-secure-link'),
    path('reports/public-export/', views.public_export_report, name='report-public-export'),
    path('reports/filter-options/', views.report_filter_options, name='report-filter-options'),
    path('', include(router.urls)),
]
