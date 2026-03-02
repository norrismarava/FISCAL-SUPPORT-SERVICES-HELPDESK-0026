from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('callogs', '0003_calllog_special_terms_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='calllog',
            name='amount_deposited',
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=10),
        ),
        migrations.AddField(
            model_name='calllog',
            name='full_amount',
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=10),
        ),
    ]
