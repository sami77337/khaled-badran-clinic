from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from apps.whatsapp.booking import due_reminders, send_due_reminder
from apps.whatsapp.configuration import configuration_issues, is_available


class Command(BaseCommand):
    help = "Send due WhatsApp appointment reminders; suitable for a scheduled job."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum appointments per run (1–1000).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count eligible rows without sending or changing them.",
        )

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 1000:
            raise CommandError("limit must be between 1 and 1000.")
        if options["dry_run"]:
            self.stdout.write(
                f"Eligible reminders: {due_reminders(timezone.now()).count()} (dry run)."
            )
            return
        if not is_available() or configuration_issues(templates=True):
            raise CommandError(
                "Meta WhatsApp configuration unavailable; no reminders sent."
            )
        if not connection.features.has_select_for_update:
            # SQLite cannot provide cross-process row locks. Test the service
            # with mocked HTTP on SQLite; operate the dispatcher on PostgreSQL.
            raise CommandError(
                "Reminder delivery requires a database with row locking (PostgreSQL)."
            )
        ids = list(
            due_reminders(timezone.now()).values_list("pk", flat=True)[
                : options["limit"]
            ]
        )
        counts = Counter()
        for appointment_id in ids:
            try:
                counts[send_due_reminder(appointment_id)] += 1
            except Exception:
                # DB/provider exceptions may contain private values. Report counts only.
                counts["failed"] += 1
        self.stdout.write(
            f"Reminders: {counts['sent']} sent, {counts['skipped']} skipped, {counts['failed']} failed."
        )
        if counts["failed"]:
            raise CommandError(
                "Some reminders were not recorded as sent; check service health before retrying."
            )
