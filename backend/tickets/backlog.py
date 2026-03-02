from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from helpdesk_backend.assignment import (
    select_available_technician_for_ticket,
    technician_is_available_for_ticket,
)

from .models import SupportTicket, TicketAuditLog, TicketBacklogEntry


ACTIVE_TICKET_STATUSES = ('pending', 'open', 'reopened')


def _log_event(ticket, event_type, description, user=None, metadata=None):
    TicketAuditLog.objects.create(
        ticket=ticket,
        user=user if getattr(user, 'is_authenticated', False) else None,
        event_type=event_type,
        description=description,
        metadata=metadata or {},
    )


def enqueue_ticket(ticket, reason='threshold_full'):
    now = timezone.now()
    entry, created = TicketBacklogEntry.objects.get_or_create(
        ticket=ticket,
        defaults={
            'is_waiting': True,
            'reason': reason,
            'enqueued_at': now,
            'dequeued_at': None,
            'dequeued_to': None,
        },
    )
    if not created and not entry.is_waiting:
        entry.is_waiting = True
        entry.reason = reason
        entry.enqueued_at = now
        entry.dequeued_at = None
        entry.dequeued_to = None
        entry.save(update_fields=['is_waiting', 'reason', 'enqueued_at', 'dequeued_at', 'dequeued_to'])
    return entry


def clear_ticket_backlog(ticket):
    entry = TicketBacklogEntry.objects.filter(ticket=ticket, is_waiting=True).first()
    if not entry:
        return None
    entry.is_waiting = False
    entry.dequeued_at = timezone.now()
    entry.save(update_fields=['is_waiting', 'dequeued_at'])
    return entry


def assign_waiting_ticket_to_technician(technician=None, actor=None, trigger='capacity_available'):
    """
    Assign the oldest waiting backlog ticket to an available technician.
    If technician is provided, try that technician first (used when they free capacity).
    """
    with transaction.atomic():
        backlog_entry = (
            TicketBacklogEntry.objects.select_related('ticket')
            .filter(is_waiting=True)
            .order_by('enqueued_at', 'id')
            .first()
        )
        if not backlog_entry:
            return None

        chosen = technician
        if chosen:
            if not technician_is_available_for_ticket(chosen):
                return None
        else:
            strategy = getattr(settings, 'AUTO_ASSIGN_TICKET_STRATEGY', 'round_robin')
            chosen = select_available_technician_for_ticket(strategy=strategy)
            if not chosen:
                return None

        ticket = SupportTicket.objects.select_for_update().filter(id=backlog_entry.ticket_id).first()
        if not ticket:
            backlog_entry.is_waiting = False
            backlog_entry.dequeued_at = timezone.now()
            backlog_entry.save(update_fields=['is_waiting', 'dequeued_at'])
            return None

        # Skip tickets no longer eligible for active assignment.
        if ticket.status == 'solved' or ticket.merged_into_id:
            backlog_entry.is_waiting = False
            backlog_entry.dequeued_at = timezone.now()
            backlog_entry.save(update_fields=['is_waiting', 'dequeued_at'])
            return None

        if ticket.assigned_to_id:
            backlog_entry.is_waiting = False
            backlog_entry.dequeued_at = timezone.now()
            backlog_entry.dequeued_to_id = ticket.assigned_to_id
            backlog_entry.save(update_fields=['is_waiting', 'dequeued_at', 'dequeued_to'])
            return None

        ticket.assigned_to = chosen
        if ticket.status in ('pending', 'unassigned'):
            ticket.status = 'open'
        elif ticket.status not in ACTIVE_TICKET_STATUSES:
            ticket.status = 'open'
        ticket.save(update_fields=['assigned_to', 'status', 'updated_at'])

        backlog_entry.is_waiting = False
        backlog_entry.dequeued_at = timezone.now()
        backlog_entry.dequeued_to = chosen
        backlog_entry.save(update_fields=['is_waiting', 'dequeued_at', 'dequeued_to'])

        _log_event(
            ticket=ticket,
            event_type='auto_assigned',
            user=actor,
            description=f'Auto-assigned from backlog to {chosen.get_full_name() or chosen.username}.',
            metadata={'technician_id': chosen.id, 'trigger': trigger},
        )

        if chosen.email:
            send_mail(
                subject=f'Ticket Assigned to You - #{ticket.ticket_number or ticket.ticket_id}',
                message=f'Hello {chosen.get_full_name() or chosen.username},\n\n'
                        f'A waiting support ticket has been assigned to you from backlog.\n\n'
                        f'Ticket ID: {ticket.ticket_number or ticket.ticket_id}\n'
                        f'Company: {ticket.company_name}\n'
                        f'Priority: {ticket.get_priority_display()}\n\n'
                        f'Best regards,\nFSSHELPDESK Team',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[chosen.email],
                fail_silently=True,
            )
        return ticket
