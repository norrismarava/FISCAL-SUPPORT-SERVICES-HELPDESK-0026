from django.conf import settings
from django.db.models import Count, F, IntegerField, Q, Value, Max
from django.db.models.functions import Coalesce
from django.core.mail import send_mail

from users.models import User


ACTIVE_TICKET_STATUSES = ('pending', 'open', 'reopened')
ACTIVE_JOB_STATUSES = ('pending', 'assigned', 'in_progress')


def get_ticket_threshold():
    return int(getattr(settings, 'AUTO_ASSIGN_MAX_OPEN_TICKETS', 7))


def get_job_threshold():
    return int(getattr(settings, 'AUTO_ASSIGN_MAX_OPEN_JOBS', 4))


def get_active_load_threshold():
    return int(getattr(settings, 'AUTO_ASSIGN_MAX_ACTIVE_LOAD', 4))


def technician_workloads():
    return (
        User.objects.filter(role='technician', is_active=True)
        .annotate(
            open_ticket_count=Count(
                'assigned_tickets',
                filter=Q(assigned_tickets__status__in=ACTIVE_TICKET_STATUSES),
                distinct=True,
            ),
            open_job_count=Count(
                'assigned_jobs',
                filter=Q(assigned_jobs__status__in=ACTIVE_JOB_STATUSES),
                distinct=True,
            ),
            last_ticket_assigned_at=Max('assigned_tickets__created_at'),
        )
        .annotate(
            active_load=Coalesce(F('open_ticket_count'), Value(0), output_field=IntegerField())
            + Coalesce(F('open_job_count'), Value(0), output_field=IntegerField())
        )
    )


def technician_is_available(technician, threshold=None):
    threshold = threshold if threshold is not None else get_active_load_threshold()
    tech = technician_workloads().filter(id=technician.id).first()
    if not tech:
        return False
    return tech.active_load < threshold


def technician_is_available_for_ticket(technician, threshold=None):
    threshold = threshold if threshold is not None else get_ticket_threshold()
    active_threshold = get_active_load_threshold()
    tech = technician_workloads().filter(id=technician.id).first()
    if not tech:
        return False
    return tech.open_ticket_count < threshold and tech.active_load < active_threshold


def technician_is_available_for_job(technician, threshold=None):
    threshold = threshold if threshold is not None else get_job_threshold()
    active_threshold = get_active_load_threshold()
    tech = technician_workloads().filter(id=technician.id).first()
    if not tech:
        return False
    return tech.open_job_count < threshold and tech.active_load < active_threshold


def get_overloaded_technicians(ticket_threshold=None, job_threshold=None, active_threshold=None):
    ticket_threshold = ticket_threshold if ticket_threshold is not None else get_ticket_threshold()
    job_threshold = job_threshold if job_threshold is not None else get_job_threshold()
    active_threshold = active_threshold if active_threshold is not None else get_active_load_threshold()
    return technician_workloads().filter(
        Q(open_ticket_count__gte=ticket_threshold)
        | Q(open_job_count__gte=job_threshold)
        | Q(active_load__gte=active_threshold)
    )


def get_overload_notification_recipients():
    recipients = set(
        User.objects.filter(role__in=['admin', 'accounts'], is_active=True)
        .exclude(email='')
        .values_list('email', flat=True)
    )
    extras = getattr(settings, 'OVERLOAD_NOTIFICATION_RECIPIENTS', []) or []
    recipients.update([email for email in extras if email])
    return sorted(recipients)


def send_overload_notification(technicians, context='Assignment'):
    tech_list = list(technicians)
    if not tech_list:
        return
    recipients = get_overload_notification_recipients()
    if not recipients:
        return

    lines = [
        f'{context} alert: technician workload threshold exceeded.',
        '',
        f'Configured limits: jobs={get_job_threshold()}, tickets={get_ticket_threshold()}, combined={get_active_load_threshold()}',
        '',
        'Technician load:',
    ]
    for tech in tech_list:
        lines.append(
            f"- {tech.get_full_name() or tech.username}: jobs={tech.open_job_count}, tickets={tech.open_ticket_count}"
        )

    send_mail(
        subject='FSS Helpdesk Overload Alert',
        message='\n'.join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
        fail_silently=True,
    )


def select_available_technician_for_ticket(preferred_user_ids=None, threshold=None, strategy='least_load'):
    threshold = threshold if threshold is not None else get_ticket_threshold()
    active_threshold = get_active_load_threshold()

    base_qs = technician_workloads().filter(
        open_ticket_count__lt=threshold,
        active_load__lt=active_threshold,
    )
    order_fields = (
        ('last_ticket_assigned_at', 'open_ticket_count', 'open_job_count', 'active_load', 'id')
        if strategy == 'round_robin'
        else ('open_ticket_count', 'open_job_count', 'active_load', 'id')
    )

    if preferred_user_ids:
        preferred_qs = base_qs.filter(id__in=preferred_user_ids).order_by(*order_fields)
        preferred = preferred_qs.first()
        if preferred:
            return preferred

    return base_qs.order_by(*order_fields).first()


def select_available_technician_for_job(preferred_user_ids=None, threshold=None):
    threshold = threshold if threshold is not None else get_job_threshold()
    active_threshold = get_active_load_threshold()

    base_qs = technician_workloads().filter(
        open_job_count__lt=threshold,
        active_load__lt=active_threshold,
    )

    if preferred_user_ids:
        preferred_qs = base_qs.filter(id__in=preferred_user_ids).order_by(
            'open_job_count', 'open_ticket_count', 'active_load', 'id'
        )
        preferred = preferred_qs.first()
        if preferred:
            return preferred

    return base_qs.order_by('open_job_count', 'open_ticket_count', 'active_load', 'id').first()
