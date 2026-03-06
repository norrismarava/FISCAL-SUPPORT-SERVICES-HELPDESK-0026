from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0008_leaverequest'),
    ]

    operations = [
        migrations.AlterField(
            model_name='leaverequest',
            name='leave_type',
            field=models.CharField(
                choices=[
                    ('annual', 'Annual Leave'),
                    ('sick', 'Sick Leave'),
                    ('compassionate', 'Compassionate Leave'),
                    ('unpaid', 'Unpaid Leave'),
                    ('day_off', 'Just a day off'),
                    ('other', 'Other'),
                ],
                default='annual',
                max_length=20,
            ),
        ),
    ]
