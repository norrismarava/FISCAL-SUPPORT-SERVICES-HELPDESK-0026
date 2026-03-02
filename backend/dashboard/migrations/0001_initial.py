import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ReportSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, unique=True)),
                (
                    'interval',
                    models.CharField(
                        choices=[
                            ('hourly', 'Hourly'),
                            ('daily', 'Daily'),
                            ('monthly', 'Monthly'),
                            ('quarterly', 'Quarterly'),
                            ('yearly', 'Yearly'),
                        ],
                        default='daily',
                        max_length=20,
                    ),
                ),
                ('recipients', models.JSONField(blank=True, default=list)),
                ('include_fields', models.JSONField(blank=True, default=list)),
                ('is_active', models.BooleanField(default=True)),
                ('last_sent_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'created_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='created_report_schedules',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'ordering': ['name'],
            },
        ),
    ]
