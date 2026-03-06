import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify
from django.core.exceptions import ValidationError

from callogs.models import CallLog
from tickets.models import ServiceType, SupportTicket
from users.models import User
from users.workitems import (
    get_or_create_client_for_email,
    sync_job_work_item,
    sync_ticket_work_item,
)


TARGET_TABLES = {"users", "tickets", "call_logs", "customer_contacts"}


def parse_iso_datetime(value):
    if not value:
        return None
    value = str(value).strip()
    if not value or value.upper() == "NULL":
        return None
    try:
        dt = datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def parse_iso_date(value):
    dt = parse_iso_datetime(f"{value} 00:00:00")
    return dt.date() if dt else None


def parse_time(value):
    if not value:
        return None
    text = str(value).strip()
    if not text or text.upper() == "NULL":
        return None
    try:
        return datetime.strptime(text, "%H:%M:%S").time()
    except ValueError:
        try:
            return datetime.strptime(text, "%H:%M").time()
        except ValueError:
            return None


def parse_decimal(value, default="0.00"):
    if value in (None, "", "NULL"):
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal(default)


def parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_email(value):
    email = (value or "").strip().lower()
    if not email:
        return ""
    try:
        validate_email(email)
        return email
    except ValidationError:
        return ""


def split_name(full_name):
    text = (full_name or "").strip()
    if not text:
        return "", ""
    parts = text.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def unique_username(seed):
    base = slugify(seed or "user").replace("-", "_")[:120] or "user"
    candidate = base
    suffix = 1
    while User.objects.filter(username=candidate).exists():
        suffix += 1
        candidate = f"{base[:110]}_{suffix}"
    return candidate


def split_rows(values_blob):
    in_string = False
    escaped = False
    depth = 0
    start = None

    for idx, ch in enumerate(values_blob):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_string = False
            continue

        if ch == "'":
            in_string = True
            continue
        if ch == "(":
            if depth == 0:
                start = idx + 1
            depth += 1
            continue
        if ch == ")":
            depth -= 1
            if depth == 0 and start is not None:
                yield values_blob[start:idx]
                start = None


def parse_row(row_text):
    reader = csv.reader(
        io.StringIO(row_text),
        delimiter=",",
        quotechar="'",
        escapechar="\\",
        doublequote=False,
        skipinitialspace=True,
    )
    values = next(reader)
    output = []
    for raw in values:
        value = raw.strip()
        if value.upper() == "NULL":
            output.append(None)
        else:
            output.append(value)
    return output


class Command(BaseCommand):
    help = "Import legacy MySQL SQL dump (users, tickets, call_logs) into current Django schema."

    def add_arguments(self, parser):
        parser.add_argument("--path", required=True, help="Absolute path to legacy .sql file.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and simulate import, then rollback.",
        )
        parser.add_argument(
            "--skip-users",
            action="store_true",
            help="Skip importing users records.",
        )
        parser.add_argument(
            "--skip-tickets",
            action="store_true",
            help="Skip importing tickets records.",
        )
        parser.add_argument(
            "--skip-jobs",
            action="store_true",
            help="Skip importing call_logs records.",
        )
        parser.add_argument("--max-users", type=int, default=0, help="Max users rows to process (0 = all).")
        parser.add_argument("--max-tickets", type=int, default=0, help="Max tickets rows to process (0 = all).")
        parser.add_argument("--max-jobs", type=int, default=0, help="Max call_logs rows to process (0 = all).")
        parser.add_argument("--user-offset", type=int, default=0, help="Skip this many legacy user rows first.")
        parser.add_argument("--ticket-offset", type=int, default=0, help="Skip this many legacy ticket rows first.")
        parser.add_argument("--job-offset", type=int, default=0, help="Skip this many legacy call_log rows first.")

    def handle(self, *args, **options):
        path = options["path"]
        dry_run = options["dry_run"]

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                sql_text = f.read()
        except OSError as exc:
            raise CommandError(f"Cannot read SQL file: {exc}") from exc

        blocks = self._extract_blocks(sql_text)
        self.stdout.write(self.style.NOTICE(f"Found target INSERT blocks for: {', '.join(sorted(blocks.keys()))}"))

        counters = {
            "users_created": 0,
            "users_updated": 0,
            "users_skipped": 0,
            "clients_created_or_linked": 0,
            "tickets_created": 0,
            "tickets_updated": 0,
            "tickets_skipped": 0,
            "jobs_created": 0,
            "jobs_updated": 0,
            "jobs_skipped": 0,
        }
        legacy_user_id_map = {}

        with transaction.atomic():
            if not options["skip_users"]:
                self._import_users(
                    blocks.get("users", []),
                    counters,
                    legacy_user_id_map,
                    max_rows=parse_int(options.get("max_users")),
                    offset=parse_int(options.get("user_offset")),
                )
            if not options["skip_tickets"]:
                self._import_tickets(
                    blocks.get("tickets", []),
                    counters,
                    legacy_user_id_map,
                    max_rows=parse_int(options.get("max_tickets")),
                    offset=parse_int(options.get("ticket_offset")),
                )
            if not options["skip_jobs"]:
                self._import_jobs(
                    blocks.get("call_logs", []),
                    counters,
                    legacy_user_id_map,
                    max_rows=parse_int(options.get("max_jobs")),
                    offset=parse_int(options.get("job_offset")),
                )

            self._print_summary(counters, dry_run)
            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry-run complete: all changes rolled back."))

    def _extract_blocks(self, sql_text):
        extracted = {name: [] for name in TARGET_TABLES}
        lines = sql_text.splitlines()
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            if not line.startswith("INSERT INTO `"):
                i += 1
                continue

            try:
                table = line.split("`", 2)[1]
            except IndexError:
                i += 1
                continue

            if table not in TARGET_TABLES:
                i += 1
                continue

            buffer = [lines[i]]
            i += 1
            while i < len(lines):
                buffer.append(lines[i])
                if lines[i].rstrip().endswith(";"):
                    i += 1
                    break
                i += 1

            statement = "\n".join(buffer)
            values_marker = ") VALUES"
            marker_pos = statement.find(values_marker)
            if marker_pos == -1:
                continue

            columns_start = statement.find("(")
            columns_end = marker_pos + 1
            values_start = marker_pos + len(values_marker)
            values_end = statement.rfind(";")
            if columns_start == -1 or columns_end <= columns_start or values_end == -1:
                continue

            columns_blob = statement[columns_start + 1 : columns_end - 1]
            values_blob = statement[values_start:values_end]
            columns = [c.strip().strip("`") for c in columns_blob.split(",")]
            extracted[table].append((columns, values_blob))

        return extracted

    def _import_users(self, blocks, counters, legacy_user_id_map, max_rows=0, offset=0):
        valid_roles = {choice[0] for choice in User.USER_ROLES}
        processed = 0
        seen = 0

        for columns, values_blob in blocks:
            for row_text in split_rows(values_blob):
                if seen < offset:
                    seen += 1
                    continue
                if max_rows and processed >= max_rows:
                    return
                values = parse_row(row_text)
                record = dict(zip(columns, values))
                legacy_id = parse_int(record.get("id"), default=0)
                role = (record.get("role") or "").strip().lower()
                email = normalize_email(record.get("email"))
                full_name = (record.get("name") or "").strip()

                if not email or role not in valid_roles:
                    counters["users_skipped"] += 1
                    processed += 1
                    seen += 1
                    continue

                first_name, last_name = split_name(full_name)
                is_active = bool(parse_int(record.get("is_active"), default=0))

                user = User.objects.filter(email__iexact=email).first()
                created = False
                if not user:
                    user = User(
                        username=unique_username(email.split("@")[0]),
                        email=email,
                    )
                    created = True

                user.first_name = first_name
                user.last_name = last_name
                user.role = role
                user.is_active = is_active
                user.is_activated = is_active
                avatar = (record.get("avatar") or "").strip()
                user.avatar = avatar or None

                # Legacy bcrypt hash ($2y$...) is not Django-native. Force password reset path.
                user.set_unusable_password()
                if created:
                    # Defend against rare username collisions across legacy variants.
                    saved = False
                    while not saved:
                        try:
                            user.save()
                            saved = True
                        except IntegrityError as exc:
                            if "users_user_username_key" in str(exc):
                                user.username = unique_username(email.split("@")[0])
                                continue
                            raise
                else:
                    user.save()

                created_at = parse_iso_datetime(record.get("created_at"))
                updated_at = parse_iso_datetime(record.get("updated_at"))
                update_fields = {}
                if created_at:
                    update_fields["created_at"] = created_at
                if updated_at:
                    update_fields["updated_at"] = updated_at
                if update_fields:
                    User.objects.filter(pk=user.pk).update(**update_fields)

                if legacy_id:
                    legacy_user_id_map[legacy_id] = user

                if created:
                    counters["users_created"] += 1
                else:
                    counters["users_updated"] += 1

                if role == "user":
                    client = get_or_create_client_for_email(
                        email=email,
                        full_name=full_name,
                        user=user,
                    )
                    if client:
                        counters["clients_created_or_linked"] += 1
                processed += 1
                seen += 1

    def _import_tickets(self, blocks, counters, legacy_user_id_map, max_rows=0, offset=0):
        valid_statuses = {choice[0] for choice in SupportTicket.STATUS_CHOICES}
        valid_priorities = {choice[0] for choice in SupportTicket.PRIORITY_CHOICES}
        processed = 0
        seen = 0

        for columns, values_blob in blocks:
            for row_text in split_rows(values_blob):
                if seen < offset:
                    seen += 1
                    continue
                if max_rows and processed >= max_rows:
                    return
                values = parse_row(row_text)
                record = dict(zip(columns, values))
                legacy_id = parse_int(record.get("id"), default=0)
                email = normalize_email(record.get("email"))
                company_name = (record.get("company_name") or "").strip() or "Unknown Company"
                message = (record.get("message") or "").strip()

                if not email or not message:
                    counters["tickets_skipped"] += 1
                    processed += 1
                    seen += 1
                    continue

                service_name = (record.get("service") or "").strip()
                service_type = None
                if service_name:
                    service_type, _ = ServiceType.objects.get_or_create(
                        name=service_name[:100],
                        defaults={"is_active": True},
                    )

                assigned_legacy = parse_int(record.get("assigned_to"), default=0)
                assigned_to = legacy_user_id_map.get(assigned_legacy)
                user = User.objects.filter(email=email).first()
                client = get_or_create_client_for_email(
                    email=email,
                    full_name=(record.get("contact_details") or "").strip(),
                    company_name=company_name,
                    user=user if user and user.role == "user" else None,
                )
                if client:
                    counters["clients_created_or_linked"] += 1

                legacy_ref = f"LEGACY-TKT-{legacy_id}" if legacy_id else None
                status = (record.get("status") or "pending").strip().lower()
                priority = (record.get("priority") or "medium").strip().lower()
                status = status if status in valid_statuses else "pending"
                priority = priority if priority in valid_priorities else "medium"

                defaults = {
                    "company_name": company_name,
                    "email": email,
                    "phone": "",
                    "contact_person": (record.get("contact_details") or "").strip()[:255],
                    "user": user,
                    "client": client,
                    "service_type": service_type,
                    "region": "",
                    "subject": (record.get("subject") or "").strip()[:255],
                    "message": message,
                    "assigned_to": assigned_to,
                    "status": status,
                    "priority": priority,
                    "is_public_submission": user is None,
                    "solved_at": parse_iso_datetime(record.get("updated_at")) if status == "solved" else None,
                }

                if legacy_ref:
                    ticket, created = SupportTicket.objects.update_or_create(
                        ticket_number=legacy_ref,
                        defaults=defaults,
                    )
                else:
                    ticket = SupportTicket.objects.create(**defaults)
                    created = True

                created_at = parse_iso_datetime(record.get("created_at"))
                updated_at = parse_iso_datetime(record.get("updated_at"))
                fields_to_update = {}
                if created_at:
                    fields_to_update["created_at"] = created_at
                if updated_at:
                    fields_to_update["updated_at"] = updated_at
                if fields_to_update:
                    SupportTicket.objects.filter(pk=ticket.pk).update(**fields_to_update)

                sync_ticket_work_item(ticket)
                if created:
                    counters["tickets_created"] += 1
                else:
                    counters["tickets_updated"] += 1
                processed += 1
                seen += 1

    def _import_jobs(self, blocks, counters, legacy_user_id_map, max_rows=0, offset=0):
        valid_statuses = {choice[0] for choice in CallLog.STATUS_CHOICES}
        valid_job_types = {choice[0] for choice in CallLog.JOB_TYPE_CHOICES}
        valid_currencies = {choice[0] for choice in CallLog.CURRENCY_CHOICES}
        processed = 0
        seen = 0

        status_map = {
            "done": "complete",
            "completed": "complete",
            "in progress": "in_progress",
        }

        for columns, values_blob in blocks:
            for row_text in split_rows(values_blob):
                if seen < offset:
                    seen += 1
                    continue
                if max_rows and processed >= max_rows:
                    return
                values = parse_row(row_text)
                record = dict(zip(columns, values))

                legacy_id = parse_int(record.get("id"), default=0)
                customer_email = normalize_email(record.get("customer_email"))
                customer_name = (record.get("customer_name") or "").strip() or "Unknown Customer"
                fault_description = (record.get("fault_description") or "").strip() or "Legacy imported job"

                if not customer_email:
                    counters["jobs_skipped"] += 1
                    processed += 1
                    seen += 1
                    continue

                booked_by = legacy_user_id_map.get(parse_int(record.get("booked_by"), default=0))
                assigned_to = legacy_user_id_map.get(parse_int(record.get("assigned_to"), default=0))
                client = get_or_create_client_for_email(
                    email=customer_email,
                    full_name=customer_name,
                    phone=(record.get("customer_phone") or "").strip(),
                    address=(record.get("customer_address") or "").strip(),
                    user=None,
                )
                if client:
                    counters["clients_created_or_linked"] += 1

                job_number = (record.get("job_card") or "").strip()
                if not job_number:
                    job_number = f"LEGACY-JOB-{legacy_id}" if legacy_id else ""

                raw_status = (record.get("status") or "pending").strip().lower()
                raw_status = status_map.get(raw_status, raw_status)
                status = raw_status if raw_status in valid_statuses else "pending"

                raw_job_type = (record.get("type") or "normal").strip().lower()
                job_type = raw_job_type if raw_job_type in valid_job_types else "normal"

                raw_currency = (record.get("currency") or "USD").strip().upper()
                currency = raw_currency if raw_currency in valid_currencies else "USD"

                defaults = {
                    "customer_name": customer_name,
                    "customer_email": customer_email,
                    "customer_phone": (record.get("customer_phone") or "").strip(),
                    "customer_address": (record.get("customer_address") or "").strip(),
                    "client": client,
                    "related_ticket": None,
                    "job_type": job_type,
                    "fault_type": "support",
                    "fault_description": fault_description,
                    "resolution_notes": (record.get("engineer_comments") or "").strip(),
                    "amount_charged": parse_decimal(record.get("amount_charged")),
                    "currency": currency,
                    "zimra_reference": (record.get("zimra_ref") or "").strip()[:100],
                    "status": status,
                    "booking_date": parse_iso_date(record.get("date_booked")),
                    "resolution_date": parse_iso_date(record.get("date_resolved")),
                    "time_start": parse_time(record.get("time_start")),
                    "time_finish": parse_time(record.get("time_finish")),
                    "billed_hours": (record.get("billed_hours") or "").strip()[:20],
                    "assigned_technician": assigned_to,
                    "resolved_by": assigned_to if status == "complete" else None,
                    "created_by": booked_by,
                    "completed_at": parse_iso_datetime(record.get("updated_at")) if status == "complete" else None,
                }

                if job_number:
                    job, created = CallLog.objects.update_or_create(
                        job_number=job_number,
                        defaults=defaults,
                    )
                else:
                    job = CallLog.objects.create(**defaults)
                    created = True

                created_at = parse_iso_datetime(record.get("created_at"))
                updated_at = parse_iso_datetime(record.get("updated_at"))
                fields_to_update = {}
                if created_at:
                    fields_to_update["created_at"] = created_at
                if updated_at:
                    fields_to_update["updated_at"] = updated_at
                if fields_to_update:
                    CallLog.objects.filter(pk=job.pk).update(**fields_to_update)

                sync_job_work_item(job)
                if created:
                    counters["jobs_created"] += 1
                else:
                    counters["jobs_updated"] += 1
                processed += 1
                seen += 1

    def _print_summary(self, counters, dry_run):
        title = "DRY RUN SUMMARY" if dry_run else "IMPORT SUMMARY"
        self.stdout.write(self.style.SUCCESS(f"\n{title}"))
        self.stdout.write(f"users_created: {counters['users_created']}")
        self.stdout.write(f"users_updated: {counters['users_updated']}")
        self.stdout.write(f"users_skipped: {counters['users_skipped']}")
        self.stdout.write(f"clients_created_or_linked: {counters['clients_created_or_linked']}")
        self.stdout.write(f"tickets_created: {counters['tickets_created']}")
        self.stdout.write(f"tickets_updated: {counters['tickets_updated']}")
        self.stdout.write(f"tickets_skipped: {counters['tickets_skipped']}")
        self.stdout.write(f"jobs_created: {counters['jobs_created']}")
        self.stdout.write(f"jobs_updated: {counters['jobs_updated']}")
        self.stdout.write(f"jobs_skipped: {counters['jobs_skipped']}")
