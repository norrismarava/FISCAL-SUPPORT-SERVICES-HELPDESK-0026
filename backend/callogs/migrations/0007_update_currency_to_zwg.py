from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('callogs', '0006_update_fault_type_choices'),
    ]

    operations = [
        migrations.AlterField(
            model_name='calllog',
            name='currency',
            field=models.CharField(
                choices=[('USD', 'US Dollar'), ('ZWG', 'ZWG'), ('ZAR', 'South African Rand')],
                default='USD',
                max_length=3,
            ),
        ),
    ]

