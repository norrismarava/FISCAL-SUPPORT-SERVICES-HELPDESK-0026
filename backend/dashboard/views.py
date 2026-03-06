# dashboard/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework.decorators import action
from django.http import HttpResponse
from django.db.models import Count, Q, Sum
from django.db.utils import OperationalError, ProgrammingError
from django.db.models.functions import TruncDate
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.utils.text import slugify
from django.core import signing
from urllib.parse import urlencode
import logging

from tickets.models import SupportTicket, ServiceType
from callogs.models import CallLog
from users.models import User
from .models import ReportSchedule
from .serializers import ReportScheduleSerializer
from .permissions import IsReportAuthorized
from .reporting import send_report, build_report_payload, report_as_csv, report_as_pdf, report_as_xlsx
from .tasks import send_report_now
from helpdesk_backend.assignment import (
    get_active_load_threshold,
    get_job_threshold,
    get_ticket_threshold,
    technician_workloads,
)

logger = logging.getLogger(__name__)


def _next_due_at(schedule, reference_time):
    if not schedule.last_sent_at:
        return reference_time
    if schedule.interval == 'hourly':
        return schedule.last_sent_at + timedelta(hours=1)
    if schedule.interval == 'daily':
        return schedule.last_sent_at + timedelta(days=1)
    if schedule.interval == 'monthly':
        return schedule.last_sent_at + timedelta(days=30)
    if schedule.interval == 'quarterly':
        return schedule.last_sent_at + timedelta(days=90)
    if schedule.interval == 'yearly':
        return schedule.last_sent_at + timedelta(days=365)
    return schedule.last_sent_at + timedelta(days=1)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    """
    Get comprehensive dashboard statistics based on user role
    """
    user = request.user
    period = request.query_params.get('period', 'week')
    cache_key = f'dashboard_stats:v2:{user.id}:{user.role}:{period}'
    cached_payload = cache.get(cache_key)
    if cached_payload:
        return Response(cached_payload)
    
    # Calculate date range based on period
    now = timezone.now()
    if period == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = now - timedelta(days=30)
    elif period == 'year':
        start_date = now - timedelta(days=365)
    else:
        start_date = now - timedelta(days=7)
    
    # Base querysets based on role
    if user.role == 'admin' or user.role == 'manager':
        all_tickets = SupportTicket.objects.all()
        all_jobs = CallLog.objects.all()
        tickets = SupportTicket.objects.filter(created_at__gte=start_date)
        jobs = CallLog.objects.filter(created_at__gte=start_date)
    elif user.role == 'technician':
        all_tickets = SupportTicket.objects.filter(assigned_to=user)
        all_jobs = CallLog.objects.filter(assigned_technician=user)
        tickets = all_tickets.filter(created_at__gte=start_date)
        jobs = all_jobs.filter(created_at__gte=start_date)
    elif user.role == 'accounts':
        all_tickets = SupportTicket.objects.none()
        all_jobs = CallLog.objects.all()
        tickets = all_tickets
        jobs = all_jobs.filter(created_at__gte=start_date)
    else:  # regular user
        all_tickets = SupportTicket.objects.filter(user=user)
        all_jobs = CallLog.objects.none()
        tickets = all_tickets.filter(created_at__gte=start_date)
        jobs = all_jobs
    
    # ========== Ticket Stats ==========
    ticket_stats = {
        'total': tickets.count(),
        'total_all': all_tickets.count(),
        'pending': tickets.filter(status='pending').count(),
        'open': tickets.filter(status='open').count(),
        'solved': tickets.filter(status='solved').count(),
        'reopened': tickets.filter(status='reopened').count(),
        'unassigned': tickets.filter(assigned_to__isnull=True).count(),
    }
    
    if user.role in ['technician', 'admin', 'manager']:
        ticket_stats['my_tickets'] = tickets.filter(assigned_to=user).count()
    
    # ========== Priority Breakdown ==========
    priority_breakdown = {key: 0 for key in ['low', 'medium', 'high', 'urgent']}
    for row in tickets.values('priority').annotate(count=Count('id')):
        key = row.get('priority')
        if key in priority_breakdown:
            priority_breakdown[key] = row.get('count', 0)
    
    # Urgent/high priority tickets
    urgent_tickets = tickets.filter(Q(priority='urgent') | Q(priority='high'))
    ticket_stats['urgent_count'] = urgent_tickets.count()
    ticket_stats['urgent_tickets'] = [{
        'id': t.id,
        'ticket_id': str(t.ticket_id),
        'company_name': t.company_name,
        'subject': t.subject,
        'priority': t.priority,
        'status': t.status,
        'created_at': t.created_at
    } for t in urgent_tickets[:5]]
    
    # ========== Service Type Distribution ==========
    service_type_dist = [
        {'name': row.get('service_type__name') or 'N/A', 'count': row.get('count', 0)}
        for row in tickets.values('service_type__name').annotate(count=Count('id')).filter(count__gt=0)
    ]
    
    # ========== Job Stats ==========
    job_stats = {
        'total': jobs.count(),
        'total_all': all_jobs.count(),
        'pending': jobs.filter(status='pending').count(),
        'assigned': jobs.filter(status='assigned').count(),
        'in_progress': jobs.filter(status='in_progress').count(),
        'complete': jobs.filter(status='complete').count(),
        'cancelled': jobs.filter(status='cancelled').count(),
        'unassigned': jobs.filter(assigned_technician__isnull=True).count(),
    }
    
    if user.role in ['technician', 'admin', 'manager']:
        job_stats['my_jobs'] = jobs.filter(assigned_technician=user).count()
    
    # ========== Fault Type Distribution ==========
    fault_keys = [
        'license_tax_rate',
        'tax_rate',
        'inhouse_license',
        'inhouse_license_reinstall',
        'makute_license_reinstall',
        'reinstallation',
        'virtual_installation',
        'support',
        'smartmini_new_install',
        'smartmini_license_renew',
        'makute_license_renewal',
    ]
    fault_types = {key: 0 for key in fault_keys}
    for row in jobs.values('fault_type').annotate(count=Count('id')):
        key = row.get('fault_type')
        if key in fault_types:
            fault_types[key] = row.get('count', 0)
    
    # ========== Job Type Stats ==========
    job_type_stats = {'normal': 0, 'emergency': 0}
    for row in jobs.values('job_type').annotate(count=Count('id')):
        key = row.get('job_type')
        if key in job_type_stats:
            job_type_stats[key] = row.get('count', 0)
    
    # Emergency jobs
    emergency_jobs = jobs.filter(job_type='emergency')
    job_stats['emergency_count'] = emergency_jobs.count()
    job_stats['emergency_jobs'] = [{
        'id': j.id,
        'job_number': j.job_number,
        'customer_name': j.customer_name,
        'fault_type': j.fault_type,
        'status': j.status,
        'created_at': j.created_at
    } for j in emergency_jobs[:5]]
    
    # ========== Financial Summary ==========
    completed_jobs = jobs.filter(status='complete')
    financial_summary = {
        'total_revenue': float(completed_jobs.aggregate(Sum('amount_charged'))['amount_charged__sum'] or 0),
        'completed_count': completed_jobs.count(),
        'by_currency': {}
    }
    
    for currency in ['USD', 'ZWG', 'ZAR']:
        if currency == 'ZWG':
            # Backward compatibility: include legacy ZWL-coded rows in ZWG totals.
            currency_total = completed_jobs.filter(currency__in=['ZWG', 'ZWL']).aggregate(Sum('amount_charged'))['amount_charged__sum'] or 0
        else:
            currency_total = completed_jobs.filter(currency=currency).aggregate(Sum('amount_charged'))['amount_charged__sum'] or 0
        financial_summary['by_currency'][currency] = float(currency_total)
    
    # ========== Technician Performance (Admin only) ==========
    technician_performance = []
    if user.role == 'admin':
        technicians = User.objects.filter(role='technician', is_active=True)
        ticket_counts = {
            row['assigned_to']: row
            for row in all_tickets.values('assigned_to').annotate(
                total=Count('id'),
                solved=Count('id', filter=Q(status='solved')),
            )
        }
        job_counts = {
            row['assigned_technician']: row
            for row in all_jobs.values('assigned_technician').annotate(
                total=Count('id'),
                completed=Count('id', filter=Q(status='complete')),
                pending=Count('id', filter=Q(status__in=['pending', 'assigned', 'in_progress'])),
            )
        }
        for tech in technicians:
            tech_ticket_summary = ticket_counts.get(tech.id, {})
            tech_job_summary = job_counts.get(tech.id, {})
            tickets_assigned = int(tech_ticket_summary.get('total') or 0)
            tickets_solved = int(tech_ticket_summary.get('solved') or 0)
            jobs_assigned = int(tech_job_summary.get('total') or 0)
            completed_jobs_count = int(tech_job_summary.get('completed') or 0)
            pending_jobs_count = int(tech_job_summary.get('pending') or 0)
            
            technician_performance.append({
                'id': tech.id,
                'name': tech.get_full_name() or tech.username,
                'avatar': tech.avatar.url if hasattr(tech, 'avatar') and tech.avatar else None,
                'tickets_assigned': tickets_assigned,
                'tickets_solved': tickets_solved,
                'jobs_assigned': jobs_assigned,
                'jobs_completed': completed_jobs_count,
                'jobs_pending': pending_jobs_count,
                'completion_rate': round((completed_jobs_count / jobs_assigned * 100) if jobs_assigned > 0 else 0, 1)
            })

    # ========== Manager/Admin Operations Data ==========
    technician_capacity = []
    reassignment_queue = []
    capacity_thresholds = {}
    if user.role in ['admin', 'manager']:
        active_load_threshold = get_active_load_threshold()
        ticket_threshold = get_ticket_threshold()
        job_threshold = get_job_threshold()
        capacity_thresholds = {
            'combined': active_load_threshold,
            'tickets': ticket_threshold,
            'jobs': job_threshold,
        }

        workloads = list(
            technician_workloads()
            .values(
                'id',
                'username',
                'first_name',
                'last_name',
                'open_ticket_count',
                'open_job_count',
                'active_load',
            )
            .order_by('-active_load', '-open_ticket_count', '-open_job_count', 'id')
        )
        overloaded_technician_ids = {
            w['id'] for w in workloads if (w.get('active_load') or 0) >= active_load_threshold
        }

        for w in workloads:
            full_name = f"{(w.get('first_name') or '').strip()} {(w.get('last_name') or '').strip()}".strip()
            open_tickets = int(w.get('open_ticket_count') or 0)
            open_jobs = int(w.get('open_job_count') or 0)
            active_load = int(w.get('active_load') or 0)
            if active_load >= active_load_threshold:
                availability = 'full'
            elif active_load >= max(active_load_threshold - 1, 0):
                availability = 'near_limit'
            else:
                availability = 'available'

            technician_capacity.append({
                'id': w['id'],
                'name': full_name or w.get('username') or 'Technician',
                'open_tickets': open_tickets,
                'open_jobs': open_jobs,
                'active_load': active_load,
                'threshold': active_load_threshold,
                'availability': availability,
            })

        attention_cutoff = now - timedelta(hours=12)
        ticket_attention = all_tickets.filter(status__in=['pending', 'open', 'reopened']).select_related('assigned_to')
        for t in ticket_attention[:200]:
            reasons = []
            if not t.assigned_to_id:
                reasons.append('unassigned')
            if t.assigned_to_id and t.assigned_to_id in overloaded_technician_ids:
                reasons.append('technician_full')
            if t.sla_breached_at:
                reasons.append('sla_breached')
            elif t.sla_due_at and t.sla_due_at <= now + timedelta(hours=2):
                reasons.append('sla_risk')
            if t.priority in ['urgent', 'high']:
                reasons.append('priority')
            if reasons:
                reassignment_queue.append({
                    'kind': 'ticket',
                    'id': t.id,
                    'ref': str(t.ticket_id),
                    'title': t.subject or t.company_name or 'Support ticket',
                    'company_or_customer': t.company_name,
                    'status': t.status,
                    'priority': t.priority,
                    'assigned_to_id': t.assigned_to_id,
                    'assigned_to_name': t.assigned_to.get_full_name() if t.assigned_to else None,
                    'created_at': t.created_at.isoformat() if t.created_at else None,
                    'updated_at': t.updated_at.isoformat() if t.updated_at else None,
                    'reasons': reasons,
                    'detail_path': f'/tickets/{t.id}',
                })

        job_attention = all_jobs.filter(status__in=['pending', 'assigned', 'in_progress']).select_related('assigned_technician')
        for j in job_attention[:200]:
            reasons = []
            if not j.assigned_technician_id:
                reasons.append('unassigned')
            if j.assigned_technician_id and j.assigned_technician_id in overloaded_technician_ids:
                reasons.append('technician_full')
            if j.job_type == 'emergency':
                reasons.append('emergency')
            if j.updated_at and j.updated_at <= attention_cutoff:
                reasons.append('stale')
            if reasons:
                reassignment_queue.append({
                    'kind': 'job',
                    'id': j.id,
                    'ref': j.job_number,
                    'title': j.fault_type.replace('_', ' ') if j.fault_type else 'Job card',
                    'company_or_customer': j.customer_name,
                    'status': j.status,
                    'priority': j.job_type,
                    'assigned_to_id': j.assigned_technician_id,
                    'assigned_to_name': j.assigned_technician.get_full_name() if j.assigned_technician else None,
                    'created_at': j.created_at.isoformat() if j.created_at else None,
                    'updated_at': j.updated_at.isoformat() if j.updated_at else None,
                    'reasons': reasons,
                    'detail_path': f'/call-logs/{j.id}',
                })

        reason_weight = {
            'sla_breached': 100,
            'emergency': 90,
            'unassigned': 80,
            'sla_risk': 70,
            'technician_full': 60,
            'priority': 50,
            'stale': 40,
        }
        reassignment_queue.sort(
            key=lambda item: (
                -max((reason_weight.get(r, 10) for r in item.get('reasons', [])), default=0),
                item.get('created_at') or '',
            )
        )
        reassignment_queue = reassignment_queue[:25]
    
    # ========== User Stats (Admin only) ==========
    user_stats = {}
    if user.role == 'admin':
        user_stats = {
            'total_users': User.objects.count(),
            'pending_activation': User.objects.filter(is_activated=False).count(),
            'active_users': User.objects.filter(is_active=True, is_activated=True).count(),
            'technicians': User.objects.filter(role='technician', is_active=True).count(),
            'managers': User.objects.filter(role='manager', is_active=True).count(),
            'regular_users': User.objects.filter(role='user', is_active=True).count(),
        }

    # ========== Reports Summary (admin/manager/accounts) ==========
    report_summary = {}
    if user.role in ['admin', 'manager', 'accounts']:
        try:
            schedules = ReportSchedule.objects.all().order_by('name')
            active_schedules = schedules.filter(is_active=True)

            last_sent = active_schedules.exclude(last_sent_at__isnull=True).order_by('-last_sent_at').first()
            next_schedule = None
            next_due = None
            for schedule in active_schedules:
                due_at = _next_due_at(schedule, now)
                if next_due is None or due_at < next_due:
                    next_due = due_at
                    next_schedule = schedule

            report_summary = {
                'total_schedules': schedules.count(),
                'active_schedules': active_schedules.count(),
                'last_sent_at': last_sent.last_sent_at if last_sent else None,
                'last_sent_schedule_name': last_sent.name if last_sent else None,
                'next_due_at': next_due,
                'next_due_schedule_name': next_schedule.name if next_schedule else None,
            }
        except (OperationalError, ProgrammingError):
            report_summary = {
                'total_schedules': 0,
                'active_schedules': 0,
                'last_sent_at': None,
                'last_sent_schedule_name': None,
                'next_due_at': None,
                'next_due_schedule_name': None,
                'warning': 'Report schedules table is not available yet. Run migrations.',
            }
    
    # ========== Recent Activity ==========
    recent_tickets = tickets.select_related('service_type', 'assigned_to').order_by('-created_at')[:10]
    recent_jobs = jobs.select_related('assigned_technician').order_by('-created_at')[:10]
    
    # ========== Upcoming Bookings ==========
    upcoming_bookings = jobs.filter(
        booking_date__gte=now.date(),
        status__in=['pending', 'assigned']
    ).order_by('booking_date', 'booking_time')[:10]
    
    booking_schedule = [{
        'id': j.id,
        'job_number': j.job_number,
        'customer_name': j.customer_name,
        'booking_date': j.booking_date,
        'booking_time': j.booking_time,
        'fault_type': j.fault_type,
        'assigned_to': j.assigned_technician.get_full_name() if j.assigned_technician else None,
        'status': j.status
    } for j in upcoming_bookings]
    
    # ========== Time Analytics (Last 7 days) ==========
    time_analytics = {'tickets_by_day': [], 'jobs_by_day': []}
    analytics_start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    ticket_by_day_map = {
        row['day'].strftime('%Y-%m-%d'): row['count']
        for row in all_tickets.filter(created_at__gte=analytics_start)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
    }
    job_by_day_map = {
        row['day'].strftime('%Y-%m-%d'): row['count']
        for row in all_jobs.filter(created_at__gte=analytics_start)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
    }
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_key = day.strftime('%Y-%m-%d')
        day_label = day.strftime('%a')
        time_analytics['tickets_by_day'].append({
            'date': day_key,
            'label': day_label,
            'count': int(ticket_by_day_map.get(day_key, 0)),
        })
        time_analytics['jobs_by_day'].append({
            'date': day_key,
            'label': day_label,
            'count': int(job_by_day_map.get(day_key, 0)),
        })
    
    # ========== Activity Timeline ==========
    activity_timeline = []
    
    # Recent ticket activities
    for ticket in recent_tickets[:5]:
        activity_timeline.append({
            'type': 'ticket',
            'action': 'created',
            'title': f"New ticket from {ticket.company_name}",
            'description': ticket.subject or ticket.message[:50],
            'id': ticket.id,
            'ticket_id': str(ticket.ticket_id),
            'timestamp': ticket.created_at,
            'icon': 'ticket'
        })
    
    # Recent job activities
    for job in recent_jobs[:5]:
        activity_timeline.append({
            'type': 'job',
            'action': job.status,
            'title': f"Job {job.status.replace('_', ' ')}",
            'description': f"{job.customer_name} - {job.fault_type}",
            'id': job.id,
            'job_number': job.job_number,
            'timestamp': job.created_at,
            'icon': 'briefcase'
        })
    
    # Sort by timestamp
    activity_timeline.sort(key=lambda x: x['timestamp'], reverse=True)
    activity_timeline = activity_timeline[:10]
    
    payload = {
        'ticket_stats': ticket_stats,
        'priority_breakdown': priority_breakdown,
        'service_type_dist': service_type_dist,
        'job_stats': job_stats,
        'fault_types': fault_types,
        'job_type_stats': job_type_stats,
        'financial_summary': financial_summary,
        'report_summary': report_summary,
        'technician_performance': technician_performance,
        'user_stats': user_stats,
        'recent_tickets': [{
            'id': t.id,
            'ticket_id': str(t.ticket_id),
            'company_name': t.company_name,
            'subject': t.subject,
            'priority': t.priority,
            'status': t.status,
            'service_type': t.service_type.name if t.service_type else None,
            'assigned_to': t.assigned_to.get_full_name() if t.assigned_to else None,
            'created_at': t.created_at
        } for t in recent_tickets],
        'recent_jobs': [{
            'id': j.id,
            'job_number': j.job_number,
            'customer_name': j.customer_name,
            'fault_type': j.fault_type,
            'job_type': j.job_type,
            'status': j.status,
            'amount_charged': float(j.amount_charged),
            'currency': j.currency,
            'assigned_to': j.assigned_technician.get_full_name() if j.assigned_technician else None,
            'created_at': j.created_at
        } for j in recent_jobs],
        'booking_schedule': booking_schedule,
        'time_analytics': time_analytics,
        'activity_timeline': [{
            **item,
            'timestamp': item['timestamp'].isoformat() if item['timestamp'] else None
        } for item in activity_timeline],
        'technician_capacity': technician_capacity,
        'reassignment_queue': reassignment_queue,
        'capacity_thresholds': capacity_thresholds,
    }
    cache.set(cache_key, payload, timeout=45)
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def global_search(request):
    """
    Global search across tickets, jobs, and users
    """
    query = request.query_params.get('q', '')
    
    if not query or len(query) < 3:
        return Response({
            'error': 'Search query must be at least 3 characters.'
        }, status=400)
    
    user = request.user
    results = {}
    
    # Search tickets
    if user.role in ['admin', 'manager', 'technician']:
        tickets = SupportTicket.objects.filter(
            Q(ticket_number__icontains=query) |
            Q(ticket_id__icontains=query) |
            Q(company_name__icontains=query) |
            Q(email__icontains=query) |
            Q(subject__icontains=query)
        )[:10]
        
        results['tickets'] = [{
            'id': t.id,
            'ticket_number': t.ticket_number,
            'ticket_id': str(t.ticket_id),
            'company_name': t.company_name,
            'status': t.status,
            'priority': t.priority
        } for t in tickets]
    
    # Search jobs
    if user.role in ['admin', 'manager', 'technician', 'accounts']:
        jobs = CallLog.objects.filter(
            Q(job_number__icontains=query) |
            Q(customer_name__icontains=query) |
            Q(customer_email__icontains=query)
        )[:10]
        
        results['jobs'] = [{
            'id': j.id,
            'job_number': j.job_number,
            'customer_name': j.customer_name,
            'status': j.status
        } for j in jobs]
    
    # Search users (admin only)
    if user.role == 'admin':
        users = User.objects.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )[:10]
        
        results['users'] = [{
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'full_name': u.get_full_name(),
            'role': u.role
        } for u in users]
    
    return Response(results)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsReportAuthorized])
def generate_report(request):
    """
    Generate and optionally email a report on demand.
    """
    interval = request.data.get('interval', 'daily')
    recipients = request.data.get('recipients') or None
    include_fields = request.data.get('include_fields') or None
    filters = request.data.get('filters') or None

    try:
        payload, used_recipients = send_report(
            interval=interval,
            recipients=recipients,
            include_fields=include_fields,
            filters=filters,
        )
    except Exception as exc:
        logger.exception('Failed to generate report')
        return Response(
            {'error': f'Failed to generate report: {str(exc)}'},
            status=500
        )

    return Response({
        'message': 'Report generated and emailed successfully.',
        'interval': interval,
        'recipients': used_recipients,
        'filters': filters or {},
        'summary': {
            'jobs_total': payload['jobs_total'],
            'jobs_completed': payload['jobs_completed'],
            'tickets_total': payload['tickets_total'],
            'estimated_revenue': payload['estimated_revenue'],
            'estimated_costs': payload.get('estimated_costs', 0),
            'pending_jobs': payload.get('pending_jobs', 0),
            'pending_tickets': payload.get('pending_tickets', 0),
            'escalated_tickets': payload.get('escalated_tickets', 0),
            'avg_job_resolution_hours': payload.get('avg_job_resolution_hours', 0),
            'avg_ticket_resolution_hours': payload.get('avg_ticket_resolution_hours', 0),
            'customer_satisfaction_avg': payload.get('customer_satisfaction_avg'),
            'customer_satisfaction_count': payload.get('customer_satisfaction_count', 0),
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsReportAuthorized])
def export_report(request):
    """
    Export a presentable summary report as CSV for admin/manager/accounts.
    """
    interval = request.query_params.get('interval', 'daily')
    export_format = (request.query_params.get('format', 'csv') or 'csv').lower()
    include_fields = request.query_params.getlist('include_fields')
    if not include_fields:
        include_fields = request.query_params.getlist('include_fields[]')
    if not include_fields:
        include_fields_csv = request.query_params.get('include_fields', '')
        if include_fields_csv:
            include_fields = [f.strip() for f in include_fields_csv.split(',') if f.strip()]

    filters = {
        'date_from': request.query_params.get('date_from'),
        'date_to': request.query_params.get('date_to'),
        'technician_ids': request.query_params.getlist('technician_ids') or request.query_params.getlist('technician_ids[]'),
        'service_type_ids': request.query_params.getlist('service_type_ids') or request.query_params.getlist('service_type_ids[]'),
        'fault_types': request.query_params.getlist('fault_types') or request.query_params.getlist('fault_types[]'),
        'ticket_statuses': request.query_params.getlist('ticket_statuses') or request.query_params.getlist('ticket_statuses[]'),
        'job_statuses': request.query_params.getlist('job_statuses') or request.query_params.getlist('job_statuses[]'),
        'regions': request.query_params.getlist('regions') or request.query_params.getlist('regions[]'),
        'priorities': request.query_params.getlist('priorities') or request.query_params.getlist('priorities[]'),
    }
    filters = {k: v for k, v in filters.items() if v}

    try:
        payload = build_report_payload(interval=interval, filters=filters)
        if export_format == 'pdf':
            content = report_as_pdf(payload, include_fields=include_fields)
            content_type = 'application/pdf'
            extension = 'pdf'
        elif export_format in ['xlsx', 'excel']:
            content = report_as_xlsx(payload, include_fields=include_fields)
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            extension = 'xlsx'
        else:
            content = report_as_csv(payload, include_fields=include_fields)
            content_type = 'text/csv'
            extension = 'csv'
    except Exception as exc:
        logger.exception('Failed to export report')
        return Response(
            {'error': f'Failed to export report: {str(exc)}'},
            status=500
        )

    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    if export_format in ['xlsx', 'excel'] and interval == 'monthly':
        filename = f"fss_main_monthly_report_{timestamp}.{extension}"
    else:
        filename = f"fss_report_{slugify(interval)}_{timestamp}.{extension}"

    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsReportAuthorized])
def create_secure_report_link(request):
    interval = request.data.get('interval', 'daily')
    include_fields = request.data.get('include_fields') or []
    filters = request.data.get('filters') or {}
    export_format = (request.data.get('format', 'csv') or 'csv').lower()
    if export_format not in ['csv', 'pdf', 'xlsx', 'excel']:
        export_format = 'csv'

    token_payload = {
        'interval': interval,
        'include_fields': include_fields,
        'filters': filters,
        'format': export_format,
        'created_by': request.user.id,
    }
    token = signing.dumps(token_payload, salt='report-export-link')
    query = urlencode({'token': token})
    secure_url = request.build_absolute_uri(f'/api/dashboard/reports/public-export/?{query}')
    max_age = int(getattr(settings, 'REPORT_SECURE_LINK_MAX_AGE_SECONDS', 86400))
    expires_at = timezone.now() + timedelta(seconds=max_age)
    return Response({
        'secure_url': secure_url,
        'expires_at': expires_at.isoformat(),
        'max_age_seconds': max_age,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def public_export_report(request):
    token = request.query_params.get('token')
    if not token:
        return Response({'error': 'Missing token.'}, status=400)

    max_age = int(getattr(settings, 'REPORT_SECURE_LINK_MAX_AGE_SECONDS', 86400))
    try:
        payload_data = signing.loads(token, salt='report-export-link', max_age=max_age)
    except Exception:
        return Response({'error': 'Invalid or expired secure link.'}, status=400)

    interval = payload_data.get('interval', 'daily')
    include_fields = payload_data.get('include_fields') or []
    filters = payload_data.get('filters') or {}
    export_format = (payload_data.get('format', 'csv') or 'csv').lower()

    try:
        payload = build_report_payload(interval=interval, filters=filters)
        if export_format == 'pdf':
            content = report_as_pdf(payload, include_fields=include_fields)
            content_type = 'application/pdf'
            extension = 'pdf'
        elif export_format in ['xlsx', 'excel']:
            content = report_as_xlsx(payload, include_fields=include_fields)
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            extension = 'xlsx'
        else:
            content = report_as_csv(payload, include_fields=include_fields)
            content_type = 'text/csv'
            extension = 'csv'
    except Exception as exc:
        logger.exception('Failed to export report from secure link')
        return Response({'error': f'Failed to export report: {str(exc)}'}, status=500)

    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    if export_format in ['xlsx', 'excel'] and interval == 'monthly':
        filename = f"fss_main_monthly_report_{timestamp}.{extension}"
    else:
        filename = f"fss_report_{slugify(interval)}_{timestamp}.{extension}"
    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsReportAuthorized])
def report_filter_options(request):
    technicians = User.objects.filter(role='technician', is_active=True).order_by('first_name', 'last_name', 'username')
    service_types = ServiceType.objects.filter(is_active=True).order_by('name')

    regions = (
        SupportTicket.objects.exclude(region__isnull=True)
        .exclude(region='')
        .values_list('region', flat=True)
        .distinct()
    )

    return Response({
        'technicians': [
            {
                'id': tech.id,
                'name': tech.get_full_name() or tech.username,
            }
            for tech in technicians
        ],
        'service_types': [
            {
                'id': st.id,
                'name': st.name,
            }
            for st in service_types
        ],
        'job_statuses': [value for value, _label in CallLog.STATUS_CHOICES],
        'ticket_statuses': [value for value, _label in SupportTicket.STATUS_CHOICES],
        'fault_types': [value for value, _label in CallLog.FAULT_TYPE_CHOICES],
        'priorities': [value for value, _label in SupportTicket.PRIORITY_CHOICES],
        'regions': sorted(set(regions)),
    })


class ReportScheduleViewSet(viewsets.ModelViewSet):
    """
    Configure scheduled report delivery.
    """
    serializer_class = ReportScheduleSerializer
    permission_classes = [IsAuthenticated, IsReportAuthorized]

    def get_queryset(self):
        try:
            return ReportSchedule.objects.all()
        except (OperationalError, ProgrammingError):
            return ReportSchedule.objects.none()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        schedule = self.get_object()
        try:
            send_report_now.delay(schedule.id)
            return Response({'message': 'Report dispatch queued.'})
        except Exception as exc:
            logger.warning('Queue dispatch failed, running report synchronously: %s', str(exc))
            try:
                send_report_now(schedule.id)
                return Response({'message': 'Queue unavailable. Report sent synchronously.'})
            except Exception as sync_exc:
                logger.exception('Failed to run scheduled report')
                return Response(
                    {'error': f'Failed to run report: {str(sync_exc)}'},
                    status=500
                )

