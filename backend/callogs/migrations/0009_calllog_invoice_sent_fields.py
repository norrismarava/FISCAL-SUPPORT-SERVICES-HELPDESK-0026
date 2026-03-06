from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('callogs', '0008_calllog_client_calllog_resolved_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='calllog',
            name='invoice_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='calllog',
            name='invoice_sent_by',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={'role__in': ['accounts', 'admin']},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='invoice_notifications_sent',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='calllog',
            name='invoice_sent_note',
            field=models.TextField(blank=True),
        ),
    ]
