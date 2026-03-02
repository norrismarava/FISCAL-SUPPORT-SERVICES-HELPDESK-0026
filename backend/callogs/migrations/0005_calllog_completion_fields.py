from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('callogs', '0004_calllog_full_amount_and_deposit'),
    ]

    operations = [
        migrations.AddField(
            model_name='calllog',
            name='billed_hours',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='calllog',
            name='time_finish',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='calllog',
            name='time_start',
            field=models.TimeField(blank=True, null=True),
        ),
    ]
