from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('callogs', '0005_calllog_completion_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='calllog',
            name='fault_type',
            field=models.CharField(
                max_length=40,
                choices=[
                    ('license_tax_rate', 'License & Tax Rate'),
                    ('tax_rate', 'Tax Rate'),
                    ('inhouse_license', 'In-House License'),
                    ('inhouse_license_reinstall', 'In-House License & Re-Installation'),
                    ('makute_license_reinstall', 'Makute License & Re-Installation'),
                    ('reinstallation', 'Re-Installation'),
                    ('virtual_installation', 'Virtual Installation'),
                    ('support', 'Support'),
                    ('smartmini_new_install', 'Smart-Mini New Installation'),
                    ('smartmini_license_renew', 'Smart Mini License Renewal'),
                    ('makute_license_renewal', 'Makute License Renewal'),
                ],
            ),
        ),
    ]
