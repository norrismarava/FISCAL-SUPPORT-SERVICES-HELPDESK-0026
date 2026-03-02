from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0005_supportticket_csat_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TicketBacklogEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_waiting', models.BooleanField(db_index=True, default=True)),
                ('reason', models.CharField(blank=True, default='threshold_full', max_length=100)),
                ('enqueued_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('dequeued_at', models.DateTimeField(blank=True, null=True)),
                ('dequeued_to', models.ForeignKey(blank=True, limit_choices_to={'role__in': ['technician', 'manager', 'admin']}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dequeued_backlog_tickets', to=settings.AUTH_USER_MODEL)),
                ('ticket', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='backlog_entry', to='tickets.supportticket')),
            ],
            options={
                'ordering': ['enqueued_at', 'id'],
            },
        ),
    ]
