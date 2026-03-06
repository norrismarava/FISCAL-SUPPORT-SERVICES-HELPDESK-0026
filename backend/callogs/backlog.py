from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from helpdesk_backend.assignment import (
    select_available_technician_for_job,
    technician_is_available_for_job,
)

from .models import CallLog, CallLogActivity, JobBacklogEntry


ACTIVE_JOB_STATUSES = ('pending', 'assigned', 'in_progress')


def enqueue_job(call_log, reason='threshold_full'):
    now = timezone.now()
    entry, created = JobBacklogEntry.objects.get_or_create(
        call_log=call_log,
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


def clear_job_backlog(call_log):
    entry = JobBacklogEntry.objects.filter(call_log=call_log, is_waiting=True).first()
    if not entry:
        return None
    entry.is_waiting = False
    entry.dequeued_at = timezone.now()
    entry.save(update_fields=['is_waiting', 'dequeued_at'])
    return entry


def assign_waiting_job_to_technician(technician=None, actor=None, trigger='capacity_available'):
    """
    Assign the oldest waiting backlog job to an available technician.
    If technician is provided, try that technician first (used when they free capacity).
    """
    with transaction.atomic():
        backlog_entry = (
            JobBacklogEntry.objects.select_related('call_log')
            .filter(is_waiting=True)
            .order_by('enqueued_at', 'id')
            .first()
        )
        if not backlog_entry:
            return None

        chosen = technician
        if chosen:
            if not technician_is_available_for_job(chosen):
                return None
        else:
            chosen = select_available_technician_for_job()
            if not chosen:
                return None

        call_log = CallLog.objects.select_for_update().filter(id=backlog_entry.call_log_id).first()
        if not call_log:
            backlog_entry.is_waiting = False
            backlog_entry.dequeued_at = timezone.now()
            backlog_entry.save(update_fields=['is_waiting', 'dequeued_at'])
            return None

        # Skip jobs no longer eligible for active assignment.
        if call_log.status == 'complete':
            backlog_entry.is_waiting = False
            backlog_entry.dequeued_at = timezone.now()
            backlog_entry.save(update_fields=['is_waiting', 'dequeued_at'])
            return None

        if call_log.assigned_technician_id:
            backlog_entry.is_waiting = False
            backlog_entry.dequeued_at = timezone.now()
            backlog_entry.dequeued_to_id = call_log.assigned_technician_id
            backlog_entry.save(update_fields=['is_waiting', 'dequeued_at', 'dequeued_to'])
            return None

        call_log.assigned_technician = chosen
        if call_log.status in ('pending',):
            call_log.status = 'assigned'
        elif call_log.status not in ACTIVE_JOB_STATUSES:
            call_log.status = 'assigned'
        call_log.save(update_fields=['assigned_technician', 'status', 'updated_at'])

        backlog_entry.is_waiting = False
        backlog_entry.dequeued_at = timezone.now()
        backlog_entry.dequeued_to = chosen
        backlog_entry.save(update_fields=['is_waiting', 'dequeued_at', 'dequeued_to'])

        CallLogActivity.objects.create(
            call_log=call_log,
            user=actor if getattr(actor, 'is_authenticated', False) else call_log.created_by,
            activity_type='assigned',
            description=f'Auto-assigned from backlog to {chosen.get_full_name() or chosen.username}.',
            metadata={'technician_id': chosen.id, 'trigger': trigger},
        )

        if chosen.email:
            send_mail(
                subject=f'Job Assigned to You - {call_log.job_number}',
                message=f'Hello {chosen.get_full_name() or chosen.username},\n\n'
                        f'A waiting job has been assigned to you from backlog.\n\n'
                        f'Job Number: {call_log.job_number}\n'
                        f'Customer: {call_log.customer_name}\n'
                        f'Fault Type: {call_log.get_fault_type_display()}\n\n'
                        f'Best regards,\nFSSHELPDESK Team',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[chosen.email],
                fail_silently=True,
            )
        return call_log

