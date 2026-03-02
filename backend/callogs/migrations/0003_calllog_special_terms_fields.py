from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('callogs', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='calllog',
            name='discount_amount',
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=10),
        ),
        migrations.AddField(
            model_name='calllog',
            name='payment_terms_type',
            field=models.CharField(
                choices=[
                    ('none', 'None'),
                    ('partial', 'Partial Payment'),
                    ('periodic', 'Periodic Payment'),
                    ('lay_by', 'Lay-By Arrangement'),
                    ('discount', 'Discount Applied'),
                ],
                default='none',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='calllog',
            name='special_terms_notes',
            field=models.TextField(blank=True),
        ),
    ]
