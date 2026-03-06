from .models import Client, ClientWorkItem


def get_or_create_client_for_email(*, email, full_name='', phone='', address='', company_name='', user=None):
    normalized = (email or '').strip().lower()
    if not normalized:
        return None

    defaults = {
        'full_name': full_name or '',
        'phone': phone or '',
        'address': address or '',
        'company_name': company_name or '',
        'is_active': True,
    }
    client, created = Client.objects.get_or_create(email=normalized, defaults=defaults)

    changed = []
    if user and not client.user_id:
        client.user = user
        changed.append('user')
    if full_name and not client.full_name:
        client.full_name = full_name
        changed.append('full_name')
    if phone and not client.phone:
        client.phone = phone
        changed.append('phone')
    if address and not client.address:
        client.address = address
        changed.append('address')
    if company_name and not client.company_name:
        client.company_name = company_name
        changed.append('company_name')
    if changed and not created:
        changed.append('updated_at')
        client.save(update_fields=changed)
    return client


def sync_ticket_work_item(ticket):
    if not ticket.client_id:
        return
    ref = ticket.ticket_number or str(ticket.ticket_id)
    ClientWorkItem.objects.update_or_create(
        ticket=ticket,
        defaults={
            'client_id': ticket.client_id,
            'item_type': 'ticket',
            'job_card': None,
            'reference_number': ref,
            'title': ticket.subject or ticket.message[:255],
            'status': ticket.status or '',
            'priority': ticket.priority or '',
            'assigned_technician': ticket.assigned_to,
            'resolved_by': ticket.resolved_by,
            'created_by': ticket.user,
            'resolved_at': ticket.solved_at,
            'source_created_at': ticket.created_at,
            'source_updated_at': ticket.updated_at,
        },
    )


def sync_job_work_item(job):
    if not job.client_id:
        return
    ClientWorkItem.objects.update_or_create(
        job_card=job,
        defaults={
            'client_id': job.client_id,
            'item_type': 'job',
            'ticket': None,
            'reference_number': job.job_number or str(job.job_id),
            'title': job.fault_description[:255] if job.fault_description else job.get_fault_type_display(),
            'status': job.status or '',
            'priority': '',
            'assigned_technician': job.assigned_technician,
            'resolved_by': job.resolved_by,
            'created_by': job.created_by,
            'resolved_at': job.completed_at,
            'source_created_at': job.created_at,
            'source_updated_at': job.updated_at,
        },
    )
