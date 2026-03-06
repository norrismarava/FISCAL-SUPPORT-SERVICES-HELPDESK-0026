from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('callogs', '0009_calllog_invoice_sent_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='JobBacklogEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(blank=True, default='threshold_full', max_length=100)),
                ('is_waiting', models.BooleanField(default=True)),
                ('enqueued_at', models.DateTimeField(auto_now_add=True)),
                ('dequeued_at', models.DateTimeField(blank=True, null=True)),
                ('call_log', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='backlog_entry', to='callogs.calllog')),
                ('dequeued_to', models.ForeignKey(blank=True, limit_choices_to={'role__in': ['technician', 'manager', 'admin']}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dequeued_backlog_jobs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['enqueued_at', 'id'],
            },
        ),
        migrations.AddIndex(
            model_name='jobbacklogentry',
            index=models.Index(fields=['is_waiting', 'enqueued_at'], name='callogs_job_is_waiti_8dfdb6_idx'),
        ),
    ]

