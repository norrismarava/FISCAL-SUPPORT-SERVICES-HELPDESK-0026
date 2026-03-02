from django.db import migrations, models
import django.db.models.deletion


def backfill_client_profiles(apps, schema_editor):
    User = apps.get_model('users', 'User')
    ClientProfile = apps.get_model('users', 'ClientProfile')

    for user in User.objects.filter(role='user').iterator():
        ClientProfile.objects.update_or_create(
            user=user,
            defaults={
                'registration_email': user.email or '',
                'registration_phone': user.phone or '',
                'registration_address': user.address or '',
                'registration_username': user.username or '',
                'registration_full_name': f'{(user.first_name or "").strip()} {(user.last_name or "").strip()}'.strip(),
                'registration_role': user.role or 'user',
                'source_ip': None,
                'user_agent': '',
            }
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_auto_activate_client_users'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('registration_email', models.EmailField(max_length=254)),
                ('registration_phone', models.CharField(blank=True, max_length=20)),
                ('registration_address', models.TextField(blank=True)),
                ('registration_username', models.CharField(max_length=150)),
                ('registration_full_name', models.CharField(blank=True, max_length=255)),
                ('registration_role', models.CharField(default='user', max_length=20)),
                ('source_ip', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='client_profile', to='users.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='clientprofile',
            index=models.Index(fields=['registration_email'], name='users_clien_registr_767ff7_idx'),
        ),
        migrations.AddIndex(
            model_name='clientprofile',
            index=models.Index(fields=['created_at'], name='users_clien_created_d5dc4d_idx'),
        ),
        migrations.RunPython(backfill_client_profiles, noop_reverse),
    ]
