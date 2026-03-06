import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


User = get_user_model()


def generate_temp_password(length=12):
    if length < 8:
        length = 8
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Command(BaseCommand):
    help = "Set temporary passwords for users (default: active users with unusable passwords)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--usernames",
            default="",
            help="Comma-separated usernames to target. If omitted, targets unusable-password users.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Include inactive users in target set.",
        )
        parser.add_argument(
            "--length",
            type=int,
            default=12,
            help="Temporary password length (min 8). Default: 12",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview targets without writing passwords.",
        )
        parser.add_argument(
            "--output",
            default="",
            help="Optional output file path to save username,email,temp_password rows.",
        )

    def handle(self, *args, **options):
        usernames_raw = (options.get("usernames") or "").strip()
        include_inactive = bool(options.get("include_inactive"))
        length = int(options.get("length") or 12)
        dry_run = bool(options.get("dry_run"))
        output_path = (options.get("output") or "").strip()

        if length < 8:
            raise CommandError("Password length must be at least 8.")

        if usernames_raw:
            usernames = [u.strip() for u in usernames_raw.split(",") if u.strip()]
            queryset = User.objects.filter(username__in=usernames)
            if not include_inactive:
                queryset = queryset.filter(is_active=True)
        else:
            queryset = User.objects.all()
            if not include_inactive:
                queryset = queryset.filter(is_active=True)
            queryset = queryset.filter(password__startswith="!")

        targets = list(queryset.order_by("username"))
        if not targets:
            self.stdout.write(self.style.WARNING("No matching users found."))
            return

        self.stdout.write(self.style.NOTICE(f"Matched users: {len(targets)}"))

        rows = []
        if dry_run:
            for user in targets:
                self.stdout.write(f"{user.username} | {user.email} | role={user.role}")
            self.stdout.write(self.style.WARNING("Dry-run: no passwords changed."))
            return

        with transaction.atomic():
            for user in targets:
                temp_password = generate_temp_password(length=length)
                user.set_password(temp_password)
                prefs = dict(user.preferences or {})
                prefs["must_change_password"] = True
                user.preferences = prefs
                user.save(update_fields=["password", "preferences", "updated_at"])
                rows.append((user.username, user.email, temp_password))

        for username, email, temp_password in rows:
            self.stdout.write(f"{username} | {email} | TEMP={temp_password}")

        if output_path:
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("username,email,temp_password\n")
                    for username, email, temp_password in rows:
                        f.write(f"{username},{email},{temp_password}\n")
                self.stdout.write(self.style.SUCCESS(f"Saved credentials to: {output_path}"))
            except OSError as exc:
                raise CommandError(f"Failed to write output file: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"Temporary passwords set for {len(rows)} users."))
