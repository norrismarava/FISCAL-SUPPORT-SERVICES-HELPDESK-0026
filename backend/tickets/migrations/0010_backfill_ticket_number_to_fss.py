from django.db import migrations


def backfill_ticket_numbers_to_fss(apps, schema_editor):
    SupportTicket = apps.get_model('tickets', 'SupportTicket')
    for ticket in SupportTicket.objects.all().only('id', 'ticket_number'):
        expected = f'FSS-{ticket.id:06d}'
        if ticket.ticket_number != expected:
            ticket.ticket_number = expected
            ticket.save(update_fields=['ticket_number'])


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0009_backfill_ticket_number_format'),
    ]

    operations = [
        migrations.RunPython(backfill_ticket_numbers_to_fss, migrations.RunPython.noop),
    ]
