from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Q
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponse
import csv

from users.models import User
from helpdesk_backend.assignment import (
    select_available_technician_for_job,
    get_overloaded_technicians,
    send_overload_notification,
    technician_is_available_for_job,
)
from tickets.backlog import assign_waiting_ticket_to_technician

from .models import CallLog, EngineerComment, CallLogActivity
from .serializers import (
    CallLogListSerializer, CallLogDetailSerializer,
    CallLogCreateSerializer, CallLogUpdateSerializer,
    EngineerCommentSerializer, CallLogActivitySerializer
)
from .permissions import IsStaffUser, IsAccountsOrAdmin


class CallLogViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for call logs/job cards
    """
    permission_classes = (IsAuthenticated, IsStaffUser)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'job_type', 'fault_type', 'assigned_technician']
    search_fields = ['job_number', 'customer_name', 'customer_email', 'fault_description']
    ordering_fields = ['created_at', 'booking_date', 'status']
    ordering = ['-created_at']
    active_job_statuses = ('pending', 'assigned', 'in_progress')

    def get_permissions(self):
        # Allow client users to access only customer_jobs endpoint.
        if self.action == 'customer_jobs':
            return [IsAuthenticated()]
        return [permission() for permission in self.permission_classes]

    def _get_accounts_notification_recipients(self):
        recipients = set()

        # All active accounts users.
        recipients.update(
            User.objects.filter(role='accounts', is_active=True).exclude(email='').values_list('email', flat=True)
        )

        # Named/static recipients from settings for leadership.
        for key in ['REPORT_MR_DANIEL_EMAIL', 'REPORT_MR_TAPIWA_EMAIL']:
            value = getattr(settings, key, '')
            if value:
                recipients.add(value)

        extra = getattr(settings, 'ACCOUNTS_NOTIFICATION_RECIPIENTS', []) or []
        recipients.update([email for email in extra if email])
        return sorted(recipients)

    def _get_job_event_notification_recipients(self):
        """
        Accounts + admin + static distribution list for finance hand-off events.
        """
        recipients = set(self._get_accounts_notification_recipients())
        recipients.update(
            User.objects.filter(role='admin', is_active=True).exclude(email='').values_list('email', flat=True)
        )
        return sorted(recipients)

    def _should_notify_for_status(self, status_value):
        configured = getattr(settings, 'JOB_STATUS_NOTIFY_EVENTS', ['complete']) or ['complete']
        configured = [str(item).strip().lower() for item in configured if str(item).strip()]
        return str(status_value or '').lower() in configured

    def _build_accounts_handoff_message(self, call_log, old_status, new_status, changed_by, request=None):
        job_url = None
        if request:
            job_url = request.build_absolute_uri(f'/api/call-logs/{call_log.id}/')

        return (
            f'Hello Team,\n\n'
            f'Job status changed and requires finance visibility.\n\n'
            f'Job Number: {call_log.job_number}\n'
            f'Customer: {call_log.customer_name}\n'
            f'Customer Email: {call_log.customer_email}\n'
            f'Customer Phone: {call_log.customer_phone}\n'
            f'Fault Type/Service: {call_log.get_fault_type_display()}\n'
            f'Fault Description: {call_log.fault_description or "N/A"}\n'
            f'Status Change: {old_status} -> {new_status}\n'
            f'Changed By: {changed_by.get_full_name() if changed_by else "System"}\n'
            f'Assigned Technician: {call_log.assigned_technician.get_full_name() if call_log.assigned_technician else "Unassigned"}\n\n'
            f'Financial Details:\n'
            f'Full Amount: {call_log.currency} {call_log.full_amount}\n'
            f'Amount Deposited: {call_log.currency} {call_log.amount_deposited}\n'
            f'Balance Due: {call_log.currency} {call_log.balance_due}\n'
            f'Amount Charged: {call_log.currency} {call_log.amount_charged}\n'
            f'Payment Terms Type: {call_log.get_payment_terms_type_display() if call_log.payment_terms_type else "N/A"}\n'
            f'Discount Amount: {call_log.currency} {call_log.discount_amount}\n'
            f'Special Terms Notes: {call_log.special_terms_notes or "N/A"}\n'
            f'Invoice Number: {call_log.invoice_number or "N/A"}\n'
            f'ZIMRA Reference: {call_log.zimra_reference or "N/A"}\n\n'
            f'Operational Dates:\n'
            f'Date Booked: {call_log.booking_date or "N/A"}\n'
            f'Date Resolved: {call_log.resolution_date or "N/A"}\n'
            f'Time Start: {call_log.time_start or "N/A"}\n'
            f'Time Finish: {call_log.time_finish or "N/A"}\n'
            f'Billed Hours: {call_log.billed_hours or "N/A"}\n'
            f'Completed At: {call_log.completed_at or "N/A"}\n'
            f'Created At: {call_log.created_at}\n'
            f'Updated At: {call_log.updated_at}\n\n'
            f'Internal API Link: {job_url or "N/A"}\n\n'
            f'Please review and update billing/ledger records accordingly.\n\n'
            f'Best regards,\nFSSHELPDESK'
        )

    def _notify_job_status_event(self, call_log, old_status, new_status, changed_by, request=None):
        if not self._should_notify_for_status(new_status):
            return

        recipients = self._get_job_event_notification_recipients()
        if not recipients:
            return

        send_mail(
            subject=f'Job Status Event - {call_log.job_number} ({old_status} -> {new_status})',
            message=self._build_accounts_handoff_message(
                call_log=call_log,
                old_status=old_status,
                new_status=new_status,
                changed_by=changed_by,
                request=request,
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=True,
        )

    def _auto_assign_job(self, call_log, originator=None):
        rules = getattr(settings, 'AUTO_ASSIGN_JOB_RULES', {}) or {}

        preferred_usernames = rules.get((call_log.fault_type or '').lower(), []) or []
        preferred_ids = list(
            User.objects.filter(username__in=preferred_usernames, role='technician', is_active=True).values_list('id', flat=True)
        )

        technician = select_available_technician_for_job(preferred_user_ids=preferred_ids)
        if technician:
            call_log.assigned_technician = technician
            call_log.status = 'assigned'
            call_log.save(update_fields=['assigned_technician', 'status', 'updated_at'])
            CallLogActivity.objects.create(
                call_log=call_log,
                user=originator,
                activity_type='assigned',
                description=f'Auto-assigned to {technician.get_full_name()} based on requestor/category rules.'
            )
            if technician.email:
                send_mail(
                    subject=f'Job Assigned to You - {call_log.job_number}',
                    message=f'Hello {technician.get_full_name()},\n\n'
                            f'A job has been auto-assigned to you.\n\n'
                            f'Job Number: {call_log.job_number}\n'
                            f'Customer: {call_log.customer_name}\n'
                            f'Fault Type: {call_log.get_fault_type_display()}\n\n'
                            f'Best regards,\nFSSHELPDESK Team',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[technician.email],
                    fail_silently=True,
                )
            return technician

        send_overload_notification(
            get_overloaded_technicians(),
            context='Job auto-assignment'
        )
        return None
    
    def get_queryset(self):
        user = self.request.user
        
        # Admins and managers see all jobs
        if user.role in ['admin', 'manager', 'accounts']:
            return CallLog.objects.all()
        
        # Technicians can view all jobs (read-only for non-assigned enforced on mutation endpoints).
        elif user.role == 'technician':
            return CallLog.objects.all()
        
        return CallLog.objects.none()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return CallLogListSerializer
        elif self.action == 'create':
            return CallLogCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return CallLogUpdateSerializer
        return CallLogDetailSerializer
    
    def perform_create(self, serializer):
        if self.request.user.role != 'accounts':
            raise PermissionDenied('Only Accounts users are allowed to create job cards.')

        call_log = serializer.save()
        assigned_technician = self._auto_assign_job(call_log, originator=self.request.user)
        
        # Notify managers
        managers = User.objects.filter(role='manager', is_active=True)
        manager_emails = [m.email for m in managers]
        
        if manager_emails:
            send_mail(
                subject=f'New Job Card Created - {call_log.job_number}',
                message=f'A new job card has been created.\n\n'
                        f'Job Number: {call_log.job_number}\n'
                        f'Customer: {call_log.customer_name}\n'
                        f'Fault Type: {call_log.get_fault_type_display()}\n'
                        f'Amount: {call_log.currency} {call_log.amount_charged}\n\n'
                        f'Assignment: {assigned_technician.get_full_name() if assigned_technician else "Pending manual assignment"}\n\n'
                        f'Please review and assign.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=manager_emails,
                fail_silently=True,
            )

    def perform_update(self, serializer):
        user = self.request.user
        if user.role == 'manager':
            raise PermissionDenied('Managers have read-only access to job cards. Use reassignment when needed.')
        old_status = serializer.instance.status
        assigned_technician = serializer.instance.assigned_technician
        if user.role == 'technician':
            if serializer.instance.assigned_technician_id != user.id:
                raise PermissionDenied('Technicians can only modify job cards assigned to them.')

            allowed_fields = {'status', 'resolution_notes', 'resolution_date', 'resolution_time'}
            incoming_fields = set(serializer.validated_data.keys())
            forbidden_fields = incoming_fields - allowed_fields
            if forbidden_fields:
                raise PermissionDenied('Technicians can only update job status and resolution time/details.')

            if serializer.validated_data.get('status') == 'unassigned':
                raise PermissionDenied('Technicians are not allowed to unassign job cards.')

        call_log = serializer.save()
        if (
            assigned_technician
            and old_status in self.active_job_statuses
            and call_log.status not in self.active_job_statuses
        ):
            assign_waiting_ticket_to_technician(
                technician=assigned_technician,
                actor=user,
                trigger='job_status_transition',
            )
    
    @action(detail=False, methods=['get'])
    def my_jobs(self, request):
        """Get jobs assigned to current user"""
        jobs = CallLog.objects.filter(assigned_technician=request.user)
        
        page = self.paginate_queryset(jobs)
        if page is not None:
            serializer = CallLogListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = CallLogListSerializer(jobs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def customer_jobs(self, request):
        """Customer portal endpoint: jobs matching the authenticated client's email."""
        if request.user.role != 'user':
            raise PermissionDenied('This endpoint is only available to client users.')

        email = (request.user.email or '').strip()
        if not email:
            return Response([], status=status.HTTP_200_OK)

        jobs = CallLog.objects.filter(customer_email__iexact=email).order_by('-created_at')
        page = self.paginate_queryset(jobs)
        if page is not None:
            serializer = CallLogListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = CallLogListSerializer(jobs, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_status(self, request):
        """Get jobs filtered by status"""
        status_param = request.query_params.get('status', 'pending')
        
        queryset = self.get_queryset()
        
        if status_param == 'all':
            jobs = queryset
        elif status_param == 'unassigned':
            jobs = queryset.filter(assigned_technician__isnull=True)
        else:
            jobs = queryset.filter(status=status_param)
        
        page = self.paginate_queryset(jobs)
        if page is not None:
            serializer = CallLogListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = CallLogListSerializer(jobs, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """
        Manual reassignment override for managers/admins with reason capture.
        """
        if request.user.role not in ['admin', 'manager']:
            raise PermissionDenied('Only managers or admins can manually reassign jobs.')

        call_log = self.get_object()
        reassignment_reason = (request.data.get('reason') or '').strip()
        if request.user.role == 'manager' and not reassignment_reason:
            return Response(
                {'error': 'Reassignment reason is required for managers.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        technician_id = request.data.get('technician_id')
        chosen_technician = None

        if technician_id:
            chosen_technician = User.objects.filter(
                id=technician_id,
                role='technician',
                is_active=True,
            ).first()
            if not chosen_technician:
                return Response(
                    {'error': 'Selected technician is invalid or inactive.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not technician_is_available_for_job(chosen_technician):
                return Response(
                    {'error': 'Selected technician is currently at workload threshold.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            chosen_technician = select_available_technician_for_job()
            if not chosen_technician:
                return Response(
                    {'error': 'No available technician found within workload threshold.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        old_assigned = call_log.assigned_technician
        call_log.assigned_technician = chosen_technician
        call_log.status = 'assigned' if call_log.status in ['pending'] else call_log.status
        call_log.save(update_fields=['assigned_technician', 'status', 'updated_at'])

        CallLogActivity.objects.create(
            call_log=call_log,
            user=request.user,
            activity_type='assigned',
            description=(
                f'Reassigned from '
                f'{old_assigned.get_full_name() if old_assigned else "Unassigned"} '
                f'to {chosen_technician.get_full_name() or chosen_technician.username}. '
                f'Reason: {reassignment_reason or "Not provided"}.'
            ),
        )

        if chosen_technician.email:
            send_mail(
                subject=f'Job Assigned to You - {call_log.job_number}',
                message=f'Hello {chosen_technician.get_full_name() or chosen_technician.username},\n\n'
                        f'A job has been manually reassigned to you by '
                        f'{request.user.get_full_name() or request.user.username}.\n\n'
                        f'Job Number: {call_log.job_number}\n'
                        f'Customer: {call_log.customer_name}\n'
                        f'Fault Type: {call_log.get_fault_type_display()}\n'
                        f'Reassignment Reason: {reassignment_reason or "Not provided"}\n\n'
                        f'Best regards,\nFSSHELPDESK Team',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[chosen_technician.email],
                fail_silently=True,
            )

        serializer = CallLogDetailSerializer(call_log)
        return Response(
            {
                'message': f'Job reassigned to {chosen_technician.get_full_name() or chosen_technician.username}.',
                'job': serializer.data,
            },
            status=status.HTTP_200_OK,
        )
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update job status"""
        call_log = self.get_object()
        if request.user.role == 'manager':
            raise PermissionDenied('Managers have read-only access on job cards.')
        if request.user.role == 'technician' and call_log.assigned_technician_id != request.user.id:
            raise PermissionDenied('Technicians can only update status for jobs assigned to them.')
        new_status = request.data.get('status')
        
        if new_status not in dict(CallLog.STATUS_CHOICES):
            return Response(
                {'error': 'Invalid status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status_code = call_log.status
        old_status = call_log.get_status_display()
        call_log.status = new_status
        resolution_notes = request.data.get('resolution_notes', '')
        resolution_date = request.data.get('resolution_date')
        resolution_time = request.data.get('resolution_time')
        time_start = request.data.get('time_start')
        time_finish = request.data.get('time_finish')
        billed_hours = request.data.get('billed_hours')
        
        if new_status == 'complete':
            missing_fields = []
            if not resolution_notes:
                missing_fields.append('resolution_notes')
            if not resolution_date:
                missing_fields.append('resolution_date')
            if not time_start:
                missing_fields.append('time_start')
            if not time_finish:
                missing_fields.append('time_finish')
            if not billed_hours:
                missing_fields.append('billed_hours')

            if missing_fields:
                return Response(
                    {'error': f'Required completion fields missing: {", ".join(missing_fields)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            call_log.completed_at = timezone.now()
            call_log.resolution_notes = resolution_notes
            call_log.resolution_date = resolution_date
            call_log.resolution_time = resolution_time or timezone.now().time()
            call_log.time_start = time_start
            call_log.time_finish = time_finish
            call_log.billed_hours = str(billed_hours)
        
        call_log.save()
        if (
            call_log.assigned_technician
            and old_status_code in self.active_job_statuses
            and call_log.status not in self.active_job_statuses
        ):
            assign_waiting_ticket_to_technician(
                technician=call_log.assigned_technician,
                actor=request.user,
                trigger='job_update_status',
            )
        
        # Log activity
        CallLogActivity.objects.create(
            call_log=call_log,
            user=request.user,
            activity_type='status_changed',
            description=f'Status changed from {old_status} to {call_log.get_status_display()}'
        )
        
        # Notify customer on completion
        if new_status == 'complete':
            if resolution_notes:
                EngineerComment.objects.create(
                    call_log=call_log,
                    engineer=request.user,
                    comment=resolution_notes
                )

            send_mail(
                subject=f'Job Completed - {call_log.job_number}',
                message=f'Hello {call_log.customer_name},\n\n'
                        f'Your job has been completed.\n\n'
                        f'Job Number: {call_log.job_number}\n'
                        f'Fault Type: {call_log.get_fault_type_display()}\n'
                        f'Resolution Notes: {call_log.resolution_notes}\n\n'
                        f'Thank you for your business.\n\n'
                        f'Best regards,\nFSSHELPDESK Team',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[call_log.customer_email],
                fail_silently=True,
            )

        # Configurable finance/admin event notifications for status changes.
        self._notify_job_status_event(
            call_log=call_log,
            old_status=old_status,
            new_status=call_log.get_status_display(),
            changed_by=request.user,
            request=request,
        )
        
        serializer = CallLogDetailSerializer(call_log)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def notify_customer(self, request, pk=None):
        """Manually notify customer about job completion"""
        call_log = self.get_object()
        
        send_mail(
            subject=f'Job Update - {call_log.job_number}',
            message=f'Hello {call_log.customer_name},\n\n'
                    f'We have an update on your job.\n\n'
                    f'Job Number: {call_log.job_number}\n'
                    f'Status: {call_log.get_status_display()}\n'
                    f'Resolution Notes: {call_log.resolution_notes}\n\n'
                    f'Best regards,\nFSSHELPDESK Team',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[call_log.customer_email],
            fail_silently=True,
        )
        
        return Response({'message': 'Customer notified successfully.'})
    
    @action(detail=False, methods=['get'], permission_classes=[IsAccountsOrAdmin])
    def export_completed(self, request):
        """Export completed jobs to CSV"""
        jobs = CallLog.objects.filter(status='complete')
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="completed_jobs.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Job Number', 'Customer Name', 'Customer Email', 'Fault Type',
            'Full Amount', 'Amount Deposited', 'Balance Due', 'Amount Charged', 'Currency', 'ZIMRA Reference', 'Invoice Number',
            'Technician', 'Booking Date', 'Completed Date'
        ])
        
        for job in jobs:
            writer.writerow([
                job.job_number,
                job.customer_name,
                job.customer_email,
                job.get_fault_type_display(),
                job.full_amount,
                job.amount_deposited,
                job.balance_due,
                job.amount_charged,
                job.currency,
                job.zimra_reference,
                job.invoice_number,
                job.assigned_technician.get_full_name() if job.assigned_technician else '',
                job.booking_date,
                job.completed_at
            ])
        
        return response


class EngineerCommentViewSet(viewsets.ModelViewSet):
    """Engineer comments on call logs"""
    serializer_class = EngineerCommentSerializer
    permission_classes = (IsAuthenticated, IsStaffUser)

    def _get_accessible_jobs(self):
        user = self.request.user
        if user.role in ['admin', 'manager', 'accounts']:
            return CallLog.objects.all()
        if user.role == 'technician':
            return CallLog.objects.all()
        return CallLog.objects.none()
    
    def get_queryset(self):
        call_log_id = self.kwargs.get('calllog_pk')
        return EngineerComment.objects.filter(
            call_log_id=call_log_id,
            call_log__in=self._get_accessible_jobs()
        )
    
    def perform_create(self, serializer):
        call_log_id = self.kwargs.get('calllog_pk')
        call_log = self._get_accessible_jobs().filter(id=call_log_id).first()
        if not call_log:
            raise PermissionDenied('You are not allowed to comment on this job card.')
        if self.request.user.role == 'manager':
            raise PermissionDenied('Managers have read-only access on job cards.')

        if self.request.user.role == 'technician' and call_log.assigned_technician_id != self.request.user.id:
            raise PermissionDenied('Technicians can only comment on job cards assigned to them.')
        
        comment = serializer.save(
            call_log=call_log,
            engineer=self.request.user
        )
        
        # Log activity
        CallLogActivity.objects.create(
            call_log=call_log,
            user=self.request.user,
            activity_type='comment_added',
            description=f'{self.request.user.get_full_name()} added a comment'
        )
