from django.db import migrations, models


def populate_ticket_numbers(apps, schema_editor):
    SupportTicket = apps.get_model('tickets', 'SupportTicket')
    for ticket in SupportTicket.objects.order_by('id'):
        if not ticket.ticket_number:
            ticket.ticket_number = f'FSS{ticket.id}'
            ticket.save(update_fields=['ticket_number'])


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='supportticket',
            name='ticket_number',
            field=models.CharField(blank=True, max_length=20, null=True, unique=True),
        ),
        migrations.RunPython(populate_ticket_numbers, migrations.RunPython.noop),
    ]
