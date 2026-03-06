from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0007_supportticket_client_supportticket_resolved_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='supportticket',
            name='address',
            field=models.TextField(blank=True),
        ),
    ]

