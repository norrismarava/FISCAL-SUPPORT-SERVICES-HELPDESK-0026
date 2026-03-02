from django.db import migrations


def activate_existing_client_users(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(role='user', is_active=False).update(is_active=True, is_activated=True)


def noop_reverse(apps, schema_editor):
    # Intentionally no-op to avoid disabling accounts on rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_department_alter_department_manager'),
    ]

    operations = [
        migrations.RunPython(activate_existing_client_users, noop_reverse),
    ]

