from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Q
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import uuid

from users.models import User, Notification
from helpdesk_backend.assignment import (
    select_available_technician_for_ticket,
    get_overloaded_technicians,
    send_overload_notification,
    technician_is_available_for_ticket,
)
from .backlog import (
    enqueue_ticket,
    clear_ticket_backlog,
    assign_waiting_ticket_to_technician,
)

from .models import (
    ServiceType, SupportTicket, TicketComment, TicketAttachment, CannedResponse, TicketAuditLog
)
from .serializers import (
    ServiceTypeSerializer, SupportTicketListSerializer, SupportTicketDetailSerializer,
    PublicTicketSubmissionSerializer, AuthenticatedTicketCreateSerializer,
    TicketUpdateSerializer, TicketCommentSerializer, TicketAttachmentSerializer,
    CannedResponseSerializer, PublicTicketStatusSerializer
)


DEFAULT_SLA_HOURS = {
    'low': 72,
    'medium': 24,
    'high': 8,
    'urgent': 4,
}
ACTIVE_TICKET_STATUSES = ('pending', 'open', 'reopened')


def _normalize_text(value):
    return (value or '').strip().lower()


def _split_csv(value):
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _match_contains(haystack, needle):
    needle = _normalize_text(needle)
    return bool(needle and needle in _normalize_text(haystack))


def _calculate_sla_due_at(priority):
    config = getattr(settings, 'SLA_HOURS_BY_PRIORITY', {}) or {}
    hours = config.get(priority, DEFAULT_SLA_HOURS.get(priority, DEFAULT_SLA_HOURS['medium']))
    try:
        hours = float(hours)
    except (TypeError, ValueError):
        hours = float(DEFAULT_SLA_HOURS['medium'])
    return timezone.now() + timezone.timedelta(hours=hours)


def _update_sla_state(ticket):
    changed_fields = []
    if not ticket.sla_due_at:
        ticket.sla_due_at = _calculate_sla_due_at(ticket.priority)
        changed_fields.append('sla_due_at')

    if ticket.status == 'solved':
        if ticket.sla_breached_at:
            ticket.sla_breached_at = None
            changed_fields.append('sla_breached_at')
    elif ticket.sla_due_at and timezone.now() > ticket.sla_due_at and not ticket.sla_breached_at:
        ticket.sla_breached_at = timezone.now()
        changed_fields.append('sla_breached_at')

    if changed_fields:
        changed_fields.append('updated_at')
        ticket.save(update_fields=list(set(changed_fields)))


def _log_ticket_event(ticket, event_type, description, user=None, metadata=None):
    TicketAuditLog.objects.create(
        ticket=ticket,
        user=user if getattr(user, 'is_authenticated', False) else None,
        event_type=event_type,
        description=description,
        metadata=metadata or {},
    )


def _create_in_app_notifications(recipients, title, message, link='', category='system'):
    notifications = [
        Notification(
            recipient=recipient,
            title=title,
            message=message,
            category=category,
            link=link or '',
        )
        for recipient in recipients
    ]
    if notifications:
        Notification.objects.bulk_create(notifications)


def _extract_preferred_usernames(ticket):
    """
    Supports:
    - legacy mapping: {"support": ["tech1", "tech2"]}
    - rule mapping:
      {
        "customer": {"acme": ["tech1"]},
        "fault_type": {"support": ["tech2"]},
        "region": {"harare": ["tech3"]},
        "keyword": {"zimra": ["tech4"]}
      }
    """
    rules = getattr(settings, 'AUTO_ASSIGN_TICKET_RULES', {}) or {}
    usernames = []

    # Legacy flat service-type map
    service_name = _normalize_text(getattr(ticket.service_type, 'name', ''))
    if isinstance(rules, dict) and service_name:
        legacy_hits = rules.get(service_name)
        if isinstance(legacy_hits, list):
            usernames.extend(_split_csv(legacy_hits))

    if not isinstance(rules, dict):
        return list(dict.fromkeys(usernames))

    customer_sections = rules.get('customer', {}) or {}
    fault_sections = rules.get('fault_type', {}) or {}
    region_sections = rules.get('region', {}) or {}
    keyword_sections = rules.get('keyword', {}) or {}

    customer_blob = ' '.join([
        ticket.company_name or '',
        ticket.email or '',
        ticket.contact_person or '',
    ])
    ticket_text = ' '.join([ticket.subject or '', ticket.message or ''])
    region_text = ticket.region or ''

    if isinstance(customer_sections, dict):
        for customer_key, mapped in customer_sections.items():
            if _match_contains(customer_blob, customer_key):
                usernames.extend(_split_csv(mapped))

    if isinstance(fault_sections, dict):
        for fault_key, mapped in fault_sections.items():
            if _match_contains(service_name, fault_key):
                usernames.extend(_split_csv(mapped))

    if isinstance(region_sections, dict):
        for region_key, mapped in region_sections.items():
            if _match_contains(region_text, region_key):
                usernames.extend(_split_csv(mapped))

    if isinstance(keyword_sections, dict):
        for keyword, mapped in keyword_sections.items():
            if _match_contains(ticket_text, keyword):
                usernames.extend(_split_csv(mapped))

    return list(dict.fromkeys(usernames))


def _resolve_preferred_technician_ids(usernames):
    if not usernames:
        return []
    return list(
        User.objects.filter(
            username__in=usernames,
            role='technician',
            is_active=True,
        ).values_list('id', flat=True)
    )


class ServiceTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public endpoint for service types
    """
    queryset = ServiceType.objects.filter(is_active=True)
    serializer_class = ServiceTypeSerializer
    permission_classes = (AllowAny,)


class CannedResponseViewSet(viewsets.ModelViewSet):
    queryset = CannedResponse.objects.all()
    serializer_class = CannedResponseSerializer
    permission_classes = (IsAuthenticated,)
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['title', 'content', 'category']
    ordering_fields = ['title', 'created_at', 'updated_at']
    ordering = ['title']

    def get_queryset(self):
        qs = CannedResponse.objects.all()
        user = self.request.user
        if user.role == 'user':
            qs = qs.filter(is_active=True)
        return qs

    def perform_create(self, serializer):
        if self.request.user.role not in ['admin', 'manager', 'technician', 'accounts']:
            raise PermissionDenied('You are not allowed to create canned responses.')
        serializer.save(created_by=self.request.user)


class PublicTicketSubmissionView(generics.CreateAPIView):
    """
    Public ticket submission endpoint (unauthenticated users)
    Includes reCAPTCHA validation and rate limiting
    """
    permission_classes = (AllowAny,)
    serializer_class = PublicTicketSubmissionSerializer

    def _auto_assign_ticket(self, ticket):
        preferred_usernames = _extract_preferred_usernames(ticket)
        preferred_ids = _resolve_preferred_technician_ids(preferred_usernames)
        strategy = getattr(settings, 'AUTO_ASSIGN_TICKET_STRATEGY', 'round_robin')
        technician = select_available_technician_for_ticket(
            preferred_user_ids=preferred_ids,
            strategy=strategy,
        )
        if technician:
            ticket.assigned_to = technician
            ticket.status = 'open'
            ticket.save(update_fields=['assigned_to', 'status', 'updated_at'])
            clear_ticket_backlog(ticket)
            _log_ticket_event(
                ticket=ticket,
                event_type='auto_assigned',
                description=f'Auto-assigned to {technician.get_full_name() or technician.username}',
                metadata={'technician_id': technician.id, 'strategy': strategy},
            )
            if technician.email:
                send_mail(
                    subject=f'Ticket Assigned to You - #{ticket.ticket_number or ticket.ticket_id}',
                    message=f'Hello {technician.get_full_name()},\n\n'
                            f'A support ticket has been auto-assigned to you.\n\n'
                            f'Ticket ID: {ticket.ticket_number or ticket.ticket_id}\n'
                            f'Company: {ticket.company_name}\n'
                            f'Service Type: {ticket.service_type.name if ticket.service_type else "N/A"}\n'
                            f'Priority: {ticket.get_priority_display()}\n\n'
                            f'Best regards,\nFSSHELPDESK Team',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[technician.email],
                    fail_silently=True,
                )
        else:
            ticket.status = 'unassigned'
            ticket.save(update_fields=['status', 'updated_at'])
            enqueue_ticket(ticket, reason='threshold_full')
            _log_ticket_event(
                ticket=ticket,
                event_type='updated',
                description='Ticket left unassigned because all technicians are at threshold.',
                metadata={'strategy': strategy},
            )
            send_overload_notification(
                get_overloaded_technicians(),
                context='Ticket auto-assignment'
            )
        return technician
    
    def perform_create(self, serializer):
        ticket = serializer.save()
        _update_sla_state(ticket)
        _log_ticket_event(
            ticket=ticket,
            event_type='created',
            description='Ticket created via public submission.',
            metadata={'public_submission': True},
        )
        assigned_technician = self._auto_assign_ticket(ticket)
        
        # Send confirmation email to customer
        send_mail(
            subject=f'Ticket Submitted - #{ticket.ticket_number or ticket.ticket_id}',
            message=f'Hello {ticket.company_name},\n\n'
                    f'Your support ticket has been successfully submitted.\n'
                    f'Ticket ID: {ticket.ticket_number or ticket.ticket_id}\n'
                    f'Service Type: {ticket.service_type.name}\n\n'
                    f'We will review your request and get back to you shortly.\n\n'
                    f'Best regards,\nFSSHELPDESK Team',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[ticket.email],
            fail_silently=True,
        )
        
        # Notify admins and technicians
        staff = User.objects.filter(
            role__in=['admin', 'technician'],
            is_active=True
        )
        staff_emails = [user.email for user in staff]
        
        if staff_emails:
            send_mail(
                subject=f'New Support Ticket - #{ticket.ticket_number or ticket.ticket_id}',
                message=f'A new support ticket has been submitted.\n\n'
                        f'Company: {ticket.company_name}\n'
                        f'Email: {ticket.email}\n'
                        f'Service Type: {ticket.service_type.name}\n'
                        f'Message: {ticket.message}\n\n'
                        f'Assignment: {assigned_technician.get_full_name() if assigned_technician else "Unassigned (all technicians are at workload threshold)"}\n\n'
                        f'Please review and assign this ticket.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=staff_emails,
                fail_silently=True,
            )
        
        return ticket


class PublicTicketStatusView(generics.GenericAPIView):
    """
    Public ticket status lookup and CSAT submission by ticket reference + email.
    """
    permission_classes = (AllowAny,)
    serializer_class = PublicTicketStatusSerializer

    def _resolve_ticket(self, request):
        ref = (request.query_params.get('ticket_ref') or request.data.get('ticket_ref') or '').strip()
        email = (request.query_params.get('email') or request.data.get('email') or '').strip().lower()
        if not ref or not email:
            return None, Response(
                {'error': 'ticket_ref and email are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = SupportTicket.objects.filter(email__iexact=email)
        ticket = queryset.filter(ticket_number__iexact=ref).first()
        if not ticket:
            try:
                ref_uuid = uuid.UUID(ref)
            except (ValueError, TypeError):
                ref_uuid = None
            if ref_uuid:
                ticket = queryset.filter(ticket_id=ref_uuid).first()
        if not ticket:
            return None, Response(
                {'error': 'No ticket found for the provided reference and email.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return ticket, None

    def get(self, request, *args, **kwargs):
        ticket, error_response = self._resolve_ticket(request)
        if error_response:
            return error_response
        serializer = self.get_serializer(ticket, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        """
        Public CSAT submission:
        - thumbs: up/down (optional quick mode)
        - score: 1..5 (optional explicit score, overrides thumbs)
        """
        ticket, error_response = self._resolve_ticket(request)
        if error_response:
            return error_response
        if ticket.status != 'solved':
            return Response(
                {'error': 'CSAT can only be submitted after a ticket is solved.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        thumbs = (request.data.get('thumbs') or '').strip().lower()
        score = request.data.get('score')
        feedback = (request.data.get('feedback') or '').strip()

        if score in [None, ''] and thumbs in ['up', 'down']:
            score = 5 if thumbs == 'up' else 1
        try:
            score = int(score)
        except (TypeError, ValueError):
            return Response({'error': 'Score must be between 1 and 5.'}, status=status.HTTP_400_BAD_REQUEST)
        if score < 1 or score > 5:
            return Response({'error': 'Score must be between 1 and 5.'}, status=status.HTTP_400_BAD_REQUEST)

        ticket.csat_score = score
        ticket.csat_feedback = feedback
        ticket.csat_submitted_at = timezone.now()
        ticket.save(update_fields=['csat_score', 'csat_feedback', 'csat_submitted_at', 'updated_at'])

        _log_ticket_event(
            ticket=ticket,
            user=None,
            event_type='updated',
            description='Public CSAT feedback submitted.',
            metadata={'score': score, 'public': True},
        )

        serializer = self.get_serializer(ticket, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class SupportTicketViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for support tickets (authenticated users)
    """
    permission_classes = (IsAuthenticated,)
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'priority', 'service_type', 'assigned_to']
    search_fields = ['ticket_id', 'ticket_number', 'company_name', 'email', 'subject', 'message']
    ordering_fields = ['created_at', 'updated_at', 'priority']
    ordering = ['-created_at']

    def _auto_assign_ticket(self, ticket, originator=None):
        preferred_usernames = _extract_preferred_usernames(ticket)
        preferred_ids = _resolve_preferred_technician_ids(preferred_usernames)
        strategy = getattr(settings, 'AUTO_ASSIGN_TICKET_STRATEGY', 'round_robin')

        technician = select_available_technician_for_ticket(
            preferred_user_ids=preferred_ids,
            strategy=strategy,
        )
        if technician:
            ticket.assigned_to = technician
            ticket.status = 'open'
            ticket.save(update_fields=['assigned_to', 'status', 'updated_at'])
            clear_ticket_backlog(ticket)
            _log_ticket_event(
                ticket=ticket,
                user=originator,
                event_type='auto_assigned',
                description=f'Auto-assigned to {technician.get_full_name() or technician.username}',
                metadata={'technician_id': technician.id, 'strategy': strategy},
            )
            if technician.email:
                send_mail(
                    subject=f'Ticket Assigned to You - #{ticket.ticket_number or ticket.ticket_id}',
                    message=f'Hello {technician.get_full_name()},\n\n'
                            f'A support ticket has been auto-assigned to you.\n\n'
                            f'Ticket ID: {ticket.ticket_number or ticket.ticket_id}\n'
                            f'Company: {ticket.company_name}\n'
                            f'Service Type: {ticket.service_type.name if ticket.service_type else "N/A"}\n'
                            f'Priority: {ticket.get_priority_display()}\n\n'
                            f'Best regards,\nFSSHELPDESK Team',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[technician.email],
                    fail_silently=True,
                )
            return technician

        ticket.status = 'unassigned'
        ticket.save(update_fields=['status', 'updated_at'])
        enqueue_ticket(ticket, reason='threshold_full')
        _log_ticket_event(
            ticket=ticket,
            user=originator,
            event_type='updated',
            description='Ticket left unassigned because all technicians are at threshold.',
            metadata={'strategy': strategy},
        )
        send_overload_notification(
            get_overloaded_technicians(),
            context='Ticket auto-assignment'
        )
        return None
    
    def get_queryset(self):
        user = self.request.user
        
        # Admins and managers see all tickets
        if user.role in ['admin', 'manager']:
            return SupportTicket.objects.all()
        
        # Technicians can view all tickets (read-only for non-assigned enforced on mutation endpoints).
        elif user.role == 'technician':
            return SupportTicket.objects.all()
        
        # Regular users see only their tickets
        return SupportTicket.objects.filter(user=user)
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SupportTicketListSerializer
        elif self.action == 'create':
            return AuthenticatedTicketCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return TicketUpdateSerializer
        return SupportTicketDetailSerializer
    
    def perform_create(self, serializer):
        if self.request.user.role == 'technician':
            raise PermissionDenied('Technicians are not allowed to create new tickets.')

        ticket = serializer.save()
        if ticket.assigned_to_id:
            clear_ticket_backlog(ticket)
        _update_sla_state(ticket)
        _log_ticket_event(
            ticket=ticket,
            user=self.request.user,
            event_type='created',
            description='Ticket created.',
            metadata={'public_submission': False},
        )
        assigned_technician = self._auto_assign_ticket(ticket, originator=self.request.user)
        # Ensure serializer.instance reflects post-create auto-assignment fields.
        ticket.refresh_from_db()
        
        # Send notification to customer
        send_mail(
            subject=f'Ticket Created - #{ticket.ticket_number or ticket.ticket_id}',
            message=f'Your support ticket has been created successfully.\n\n'
                    f'Ticket ID: {ticket.ticket_number or ticket.ticket_id}\n'
                    f'Status: {ticket.get_status_display()}\n'
                    f'Assigned To: {assigned_technician.get_full_name() if assigned_technician else "Pending assignment"}\n\n'
                    f'Best regards,\nFSSHELPDESK Team',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[ticket.email],
            fail_silently=True,
        )

        ticket_ref = ticket.ticket_number or str(ticket.ticket_id)
        creator_name = self.request.user.get_full_name() or self.request.user.username
        staff_recipients = User.objects.filter(
            role__in=['technician', 'manager', 'admin'],
            is_active=True,
        ).exclude(id=self.request.user.id)
        _create_in_app_notifications(
            recipients=staff_recipients,
            title=f'New Ticket - {ticket_ref}',
            message=f'{creator_name} created ticket {ticket_ref}: {ticket.subject or "No subject"}',
            link=f'/tickets/{ticket.id}',
        )

        if assigned_technician:
            _create_in_app_notifications(
                recipients=[assigned_technician],
                title=f'Ticket Assigned - {ticket_ref}',
                message=f'You have been assigned ticket {ticket_ref}.',
                link=f'/tickets/{ticket.id}',
            )

    def perform_update(self, serializer):
        user = self.request.user
        before = serializer.instance
        if user.role == 'manager':
            raise PermissionDenied('Managers have read-only access to tickets. Use reassignment when needed.')
        old_status = before.status
        old_assigned_to_id = before.assigned_to_id

        if user.role == 'technician':
            if serializer.instance.assigned_to_id != user.id:
                raise PermissionDenied('Technicians can only modify tickets assigned to them.')

            allowed_fields = {'status'}
            incoming_fields = set(serializer.validated_data.keys())
            forbidden_fields = incoming_fields - allowed_fields
            if forbidden_fields:
                raise PermissionDenied('Technicians can only update ticket status.')

            if serializer.validated_data.get('status') == 'unassigned':
                raise PermissionDenied('Technicians are not allowed to unassign tickets.')
        else:
            # Status updates are reserved for the assigned technician only.
            if 'status' in serializer.validated_data:
                raise PermissionDenied('Only the assigned technician can update ticket status.')

            # Ticket creators can edit content fields, but not assignment/priority controls.
            if user.role == 'user':
                if before.user_id != user.id:
                    raise PermissionDenied('You can only edit tickets you created.')
                forbidden_fields = {'priority', 'assigned_to'}
                incoming_fields = set(serializer.validated_data.keys())
                if incoming_fields & forbidden_fields:
                    raise PermissionDenied('You are not allowed to change priority or assignment.')

        ticket = serializer.save()
        _update_sla_state(ticket)

        changed_fields = list(serializer.validated_data.keys())
        if changed_fields:
            _log_ticket_event(
                ticket=ticket,
                user=user,
                event_type='updated',
                description='Ticket updated.',
                metadata={'fields': changed_fields},
            )

        if old_status != ticket.status:
            _log_ticket_event(
                ticket=ticket,
                user=user,
                event_type='status_changed',
                description=f'Status changed from {old_status} to {ticket.status}.',
                metadata={'from': old_status, 'to': ticket.status},
            )
        if old_assigned_to_id != ticket.assigned_to_id:
            if ticket.assigned_to_id:
                clear_ticket_backlog(ticket)
            _log_ticket_event(
                ticket=ticket,
                user=user,
                event_type='updated',
                description='Ticket assignment changed.',
                metadata={'from_user_id': old_assigned_to_id, 'to_user_id': ticket.assigned_to_id},
            )

        # When an assigned technician completes/closes work, immediately drain one waiting backlog ticket.
        if (
            old_assigned_to_id
            and old_status in ACTIVE_TICKET_STATUSES
            and ticket.status not in ACTIVE_TICKET_STATUSES
        ):
            assign_waiting_ticket_to_technician(
                technician=ticket.assigned_to,
                actor=user,
                trigger='ticket_status_transition',
            )
    
    @action(detail=False, methods=['get'])
    def client_history(self, request):
        """
        External client ticket history including technician assistance trail and related jobs.
        """
        user = request.user
        if user.role != 'user':
            raise PermissionDenied('This endpoint is only available to client users.')

        queryset = SupportTicket.objects.filter(
            Q(user=user) | Q(email__iexact=user.email)
        ).distinct().order_by('-created_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = SupportTicketDetailSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = SupportTicketDetailSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_tickets(self, request):
        """Get tickets assigned to current user (technician)"""
        tickets = SupportTicket.objects.filter(assigned_to=request.user)
        
        page = self.paginate_queryset(tickets)
        if page is not None:
            serializer = SupportTicketListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = SupportTicketListSerializer(tickets, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_status(self, request):
        """Get tickets filtered by status"""
        status_param = request.query_params.get('status', 'pending')
        
        queryset = self.get_queryset()
        
        if status_param == 'unassigned':
            tickets = queryset.filter(assigned_to__isnull=True)
        else:
            tickets = queryset.filter(status=status_param)
        
        page = self.paginate_queryset(tickets)
        if page is not None:
            serializer = SupportTicketListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = SupportTicketListSerializer(tickets, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """
        Manual assignment override for managers/admins.
        Useful for urgent re-routing when the originally assigned technician is unavailable.
        """
        if request.user.role not in ['admin', 'manager']:
            raise PermissionDenied('Only managers or admins can manually assign tickets.')

        ticket = self.get_object()
        if request.user.role == 'manager' and ticket.status == 'solved':
            raise PermissionDenied('Managers cannot reassign solved tickets.')
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
            if not technician_is_available_for_ticket(chosen_technician):
                return Response(
                    {'error': 'Selected technician is currently at ticket workload threshold.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            strategy = getattr(settings, 'AUTO_ASSIGN_TICKET_STRATEGY', 'round_robin')
            chosen_technician = select_available_technician_for_ticket(strategy=strategy)
            if not chosen_technician:
                return Response(
                    {'error': 'No available technician found within workload threshold.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        old_assigned = ticket.assigned_to
        ticket.assigned_to = chosen_technician
        ticket.status = 'open' if ticket.status in ['pending', 'unassigned'] else ticket.status
        ticket.save(update_fields=['assigned_to', 'status', 'updated_at'])
        clear_ticket_backlog(ticket)
        _update_sla_state(ticket)

        _log_ticket_event(
            ticket=ticket,
            user=request.user,
            event_type='updated',
            description=(
                f'Ticket reassigned from '
                f'{old_assigned.get_full_name() if old_assigned else "Unassigned"} to '
                f'{chosen_technician.get_full_name() or chosen_technician.username}.'
            ),
            metadata={
                'from_user_id': old_assigned.id if old_assigned else None,
                'to_user_id': chosen_technician.id,
                'manual_override': True,
                'reason': reassignment_reason,
            },
        )

        if chosen_technician.email:
            send_mail(
                subject=f'Ticket Assigned to You - #{ticket.ticket_number or ticket.ticket_id}',
                message=f'Hello {chosen_technician.get_full_name() or chosen_technician.username},\n\n'
                        f'A ticket has been manually assigned to you by {request.user.get_full_name() or request.user.username}.\n\n'
                        f'Ticket ID: {ticket.ticket_number or ticket.ticket_id}\n'
                        f'Company: {ticket.company_name}\n'
                        f'Priority: {ticket.get_priority_display()}\n'
                        f'Subject: {ticket.subject or "N/A"}\n\n'
                        f'Reassignment Reason: {reassignment_reason or "Not provided"}\n\n'
                        f'Best regards,\nFSSHELPDESK Team',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[chosen_technician.email],
                fail_silently=True,
            )

        ticket_ref = ticket.ticket_number or str(ticket.ticket_id)
        _create_in_app_notifications(
            recipients=[chosen_technician],
            title=f'Ticket Assigned - {ticket_ref}',
            message=(
                f'You were assigned ticket {ticket_ref} by '
                f'{request.user.get_full_name() or request.user.username}.'
            ),
            link=f'/tickets/{ticket.id}',
        )

        serializer = SupportTicketDetailSerializer(ticket, context={'request': request})
        return Response(
            {
                'message': f'Ticket assigned to {chosen_technician.get_full_name() or chosen_technician.username}.',
                'ticket': serializer.data,
            },
            status=status.HTTP_200_OK,
        )
    
    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        """Reopen a solved ticket"""
        ticket = self.get_object()

        if request.user.role != 'technician' or ticket.assigned_to_id != request.user.id:
            raise PermissionDenied('Only the assigned technician can reopen this ticket.')
        
        if ticket.status != 'solved':
            return Response(
                {'error': 'Only solved tickets can be reopened.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        ticket.reopen()
        _update_sla_state(ticket)
        _log_ticket_event(
            ticket=ticket,
            user=request.user,
            event_type='reopened',
            description='Ticket reopened.',
        )

        if ticket.user_id:
            _create_in_app_notifications(
                recipients=User.objects.filter(id=ticket.user_id, is_active=True),
                title=f'Ticket Reopened - {ticket.ticket_number or ticket.ticket_id}',
                message='Your ticket was reopened by the assigned technician.',
                link=f'/tickets/{ticket.id}',
            )
        
        serializer = SupportTicketDetailSerializer(ticket, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def mark_solved(self, request, pk=None):
        """Mark ticket as solved"""
        ticket = self.get_object()
        if request.user.role != 'technician' or ticket.assigned_to_id != request.user.id:
            raise PermissionDenied('Only the assigned technician can mark this ticket as solved.')
        ticket.status = 'solved'
        ticket.solved_at = timezone.now()
        ticket.save()
        clear_ticket_backlog(ticket)
        _update_sla_state(ticket)
        _log_ticket_event(
            ticket=ticket,
            user=request.user,
            event_type='solved',
            description='Ticket marked as solved.',
        )
        assign_waiting_ticket_to_technician(
            technician=ticket.assigned_to,
            actor=request.user,
            trigger='ticket_mark_solved',
        )
        
        # Notify customer
        send_mail(
            subject=f'Ticket Solved - #{ticket.ticket_number or ticket.ticket_id}',
            message=f'Hello {ticket.company_name},\n\n'
                    f'Your support ticket has been marked as solved.\n\n'
                    f'Ticket ID: {ticket.ticket_number or ticket.ticket_id}\n\n'
                    f'If you need further assistance, please reopen the ticket.\n\n'
                    f'Best regards,\nFSSHELPDESK Team',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[ticket.email],
            fail_silently=True,
        )

        if ticket.user_id:
            _create_in_app_notifications(
                recipients=User.objects.filter(id=ticket.user_id, is_active=True),
                title=f'Ticket Solved - {ticket.ticket_number or ticket.ticket_id}',
                message='Your ticket has been marked as solved.',
                link=f'/tickets/{ticket.id}',
            )
        
        serializer = SupportTicketDetailSerializer(ticket, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def submit_csat(self, request, pk=None):
        """
        Customer satisfaction capture for solved tickets.
        """
        ticket = self.get_object()
        user = request.user

        if user.role != 'user':
            raise PermissionDenied('Only client users can submit CSAT feedback.')
        if ticket.user_id and ticket.user_id != user.id:
            raise PermissionDenied('You can only submit feedback for your own tickets.')
        if ticket.status != 'solved':
            return Response(
                {'error': 'CSAT can only be submitted after a ticket is solved.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        score = request.data.get('score')
        feedback = request.data.get('feedback', '') or ''
        try:
            score = int(score)
        except (TypeError, ValueError):
            return Response({'error': 'Score must be an integer between 1 and 5.'}, status=status.HTTP_400_BAD_REQUEST)
        if score < 1 or score > 5:
            return Response({'error': 'Score must be between 1 and 5.'}, status=status.HTTP_400_BAD_REQUEST)

        ticket.csat_score = score
        ticket.csat_feedback = feedback.strip()
        ticket.csat_submitted_at = timezone.now()
        ticket.save(update_fields=['csat_score', 'csat_feedback', 'csat_submitted_at', 'updated_at'])

        _log_ticket_event(
            ticket=ticket,
            user=request.user,
            event_type='updated',
            description='Customer satisfaction feedback submitted.',
            metadata={'score': score},
        )

        serializer = SupportTicketDetailSerializer(ticket, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def merge(self, request, pk=None):
        """
        Merge current ticket into a target ticket.
        Body: {"target_ticket_id": <id>}
        """
        source = self.get_object()
        if request.user.role not in ['admin', 'manager']:
            raise PermissionDenied('Only admin or manager can merge tickets.')

        target_id = request.data.get('target_ticket_id')
        if not target_id:
            return Response(
                {'error': 'target_ticket_id is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            target = SupportTicket.objects.get(id=target_id)
        except SupportTicket.DoesNotExist:
            return Response(
                {'error': 'Target ticket not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if source.id == target.id:
            return Response(
                {'error': 'A ticket cannot be merged into itself.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if source.merged_into_id:
            return Response(
                {'error': 'This ticket has already been merged.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        source.comments.update(ticket=target)
        source.attachments.update(ticket=target)

        source.merged_into = target
        source.status = 'solved'
        source.solved_at = timezone.now()
        source.save(update_fields=['merged_into', 'status', 'solved_at', 'updated_at'])

        _log_ticket_event(
            ticket=source,
            user=request.user,
            event_type='merged',
            description=f'Merged into ticket #{target.ticket_number or target.ticket_id}.',
            metadata={'target_ticket_id': target.id},
        )
        _log_ticket_event(
            ticket=target,
            user=request.user,
            event_type='merged',
            description=f'Absorbed merged ticket #{source.ticket_number or source.ticket_id}.',
            metadata={'source_ticket_id': source.id},
        )

        serializer = SupportTicketDetailSerializer(target, context={'request': request})
        return Response(
            {'message': 'Tickets merged successfully.', 'target_ticket': serializer.data},
            status=status.HTTP_200_OK
        )


class TicketCommentViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for ticket comments
    """
    serializer_class = TicketCommentSerializer
    permission_classes = (IsAuthenticated,)

    def _get_accessible_tickets(self):
        user = self.request.user
        if user.role in ['admin', 'manager']:
            return SupportTicket.objects.all()
        if user.role == 'technician':
            return SupportTicket.objects.all()
        return SupportTicket.objects.filter(user=user)
    
    def get_queryset(self):
        ticket_id = self.kwargs.get('ticket_pk')
        queryset = TicketComment.objects.filter(
            ticket_id=ticket_id,
            ticket__in=self._get_accessible_tickets()
        )
        if self.request.user.role == 'user':
            queryset = queryset.filter(is_internal=False)
        return queryset
    
    def perform_create(self, serializer):
        ticket_id = self.kwargs.get('ticket_pk')
        ticket = self._get_accessible_tickets().filter(id=ticket_id).first()
        if not ticket:
            raise PermissionDenied('You are not allowed to comment on this ticket.')
        if self.request.user.role == 'manager':
            raise PermissionDenied('Managers have read-only access on tickets.')

        if self.request.user.role == 'technician' and ticket.assigned_to_id != self.request.user.id:
            raise PermissionDenied('Technicians can only comment on tickets assigned to them.')
        
        is_internal = serializer.validated_data.get('is_internal', True)
        if self.request.user.role == 'user':
            is_internal = False

        comment = serializer.save(
            ticket=ticket,
            author=self.request.user,
            is_internal=is_internal
        )
        _log_ticket_event(
            ticket=ticket,
            user=self.request.user,
            event_type='comment_added',
            description='Comment added.',
            metadata={'is_internal': comment.is_internal},
        )
        
        # Notify customer if comment is not internal
        if not comment.is_internal:
            send_mail(
                subject=f'New Comment on Ticket #{ticket.ticket_number or ticket.ticket_id}',
                message=f'A new comment has been added to your ticket.\n\n'
                        f'Comment: {comment.content}\n\n'
                        f'Best regards,\nFSSHELPDESK Team',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[ticket.email],
                fail_silently=True,
            )

            # In-app bell notification to ticket owner when staff posts public reply.
            if self.request.user.role in ['technician', 'admin', 'manager', 'accounts'] and ticket.user_id:
                _create_in_app_notifications(
                    recipients=User.objects.filter(id=ticket.user_id, is_active=True),
                    title=f'New Support Reply - {ticket.ticket_number or ticket.ticket_id}',
                    message=(
                        f'{self.request.user.get_full_name() or self.request.user.username} '
                        f'replied on your ticket.'
                    ),
                    link=f'/tickets/{ticket.id}',
                )

        # In-app bell notifications for internal team when client posts feedback/message.
        if self.request.user.role == 'user':
            recipients = User.objects.filter(
                role__in=['technician', 'manager', 'admin'],
                is_active=True,
            ).exclude(id=self.request.user.id)
            ticket_ref = ticket.ticket_number or str(ticket.ticket_id)
            message_preview = (comment.content or '').strip()
            if len(message_preview) > 140:
                message_preview = f'{message_preview[:137]}...'

            _create_in_app_notifications(
                recipients=recipients,
                title=f'Client Feedback - {ticket_ref}',
                message=(
                    f'Client {self.request.user.get_full_name() or self.request.user.username} '
                    f'sent a message on ticket {ticket_ref}: "{message_preview}"'
                ),
                category='ticket_feedback',
                link=f'/tickets/{ticket.id}',
            )


class TicketAttachmentViewSet(viewsets.ModelViewSet):
    """
    Upload and manage ticket attachments
    """
    serializer_class = TicketAttachmentSerializer
    permission_classes = (IsAuthenticated,)

    def _get_accessible_tickets(self):
        user = self.request.user
        if user.role in ['admin', 'manager']:
            return SupportTicket.objects.all()
        if user.role == 'technician':
            return SupportTicket.objects.all()
        return SupportTicket.objects.filter(user=user)
    
    def get_queryset(self):
        ticket_id = self.kwargs.get('ticket_pk')
        return TicketAttachment.objects.filter(
            ticket_id=ticket_id,
            ticket__in=self._get_accessible_tickets()
        )
    
    def perform_create(self, serializer):
        ticket_id = self.kwargs.get('ticket_pk')
        ticket = self._get_accessible_tickets().filter(id=ticket_id).first()
        if not ticket:
            raise PermissionDenied('You are not allowed to upload files to this ticket.')
        if self.request.user.role == 'manager':
            raise PermissionDenied('Managers have read-only access on tickets.')

        if self.request.user.role == 'technician' and ticket.assigned_to_id != self.request.user.id:
            raise PermissionDenied('Technicians can only upload files to tickets assigned to them.')
        
        file = self.request.FILES['file']
        
        attachment = serializer.save(
            ticket=ticket,
            filename=file.name,
            file_size=file.size,
            file_type=file.name.split('.')[-1].lower()
        )
        _log_ticket_event(
            ticket=ticket,
            user=self.request.user,
            event_type='attachment_added',
            description=f'Attachment uploaded: {attachment.filename}',
            metadata={'attachment_id': attachment.id, 'file_type': attachment.file_type},
        )

