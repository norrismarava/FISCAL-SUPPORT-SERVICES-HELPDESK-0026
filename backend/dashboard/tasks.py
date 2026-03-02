from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import ReportSchedule
from .reporting import send_report


def _is_due(schedule, now):
    if not schedule.last_sent_at:
        return True

    delta = now - schedule.last_sent_at
    if schedule.interval == 'hourly':
        return delta >= timedelta(hours=1)
    if schedule.interval == 'daily':
        return delta >= timedelta(days=1)
    if schedule.interval == 'monthly':
        return delta >= timedelta(days=30)
    if schedule.interval == 'quarterly':
        return delta >= timedelta(days=90)
    if schedule.interval == 'yearly':
        return delta >= timedelta(days=365)
    return False


@shared_task
def process_report_schedules():
    now = timezone.now()
    schedules = ReportSchedule.objects.filter(is_active=True)
    sent_count = 0

    for schedule in schedules:
        if not _is_due(schedule, now):
            continue

        send_report(
            interval=schedule.interval,
            recipients=schedule.recipients or None,
            include_fields=schedule.include_fields or None,
            filters=schedule.filters or None,
        )
        schedule.last_sent_at = now
        schedule.save(update_fields=['last_sent_at', 'updated_at'])
        sent_count += 1

    return {'sent_count': sent_count}


@shared_task
def send_report_now(schedule_id):
    schedule = ReportSchedule.objects.filter(id=schedule_id, is_active=True).first()
    if not schedule:
        return {'sent': False}

    send_report(
        interval=schedule.interval,
        recipients=schedule.recipients or None,
        include_fields=schedule.include_fields or None,
        filters=schedule.filters or None,
    )
    schedule.last_sent_at = timezone.now()
    schedule.save(update_fields=['last_sent_at', 'updated_at'])
    return {'sent': True, 'schedule_id': schedule_id}
