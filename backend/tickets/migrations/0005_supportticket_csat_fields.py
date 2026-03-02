from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0004_ticket_automation_features'),
    ]

    operations = [
        migrations.AddField(
            model_name='supportticket',
            name='csat_feedback',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='supportticket',
            name='csat_score',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='supportticket',
            name='csat_submitted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

