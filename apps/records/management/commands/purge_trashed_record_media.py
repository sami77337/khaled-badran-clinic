from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditLog
from apps.records.models import RecordMedia


RETENTION_DAYS = 30


class Command(BaseCommand):
    help = "Permanently purge RecordMedia retained in Trash for at least 30 days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many retained media rows are eligible without changing files or data.",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
        eligible_ids = list(
            RecordMedia.objects.filter(
                trashed_at__isnull=False,
                trashed_at__lte=cutoff,
            )
            .order_by("trashed_at", "pk")
            .values_list("pk", flat=True)
        )

        if options["dry_run"]:
            self.stdout.write(
                f"Dry run: {len(eligible_ids)} RecordMedia row(s) are eligible for purge."
            )
            return

        purged_count = 0
        failure_count = 0
        for media_id in eligible_ids:
            with transaction.atomic():
                media = (
                    RecordMedia.objects.select_for_update()
                    .filter(
                        pk=media_id,
                        trashed_at__isnull=False,
                        trashed_at__lte=cutoff,
                    )
                    .first()
                )
                if media is None:
                    continue

                try:
                    if media.file and media.file.name:
                        media.file.storage.delete(media.file.name)
                except Exception:  # Storage backends expose provider-specific exceptions.
                    failure_count += 1
                    self.stderr.write(
                        self.style.ERROR(
                            f"Failed to purge media {media.public_id}: storage deletion failed."
                        )
                    )
                    continue

                AuditLog.objects.create(
                    user=None,
                    action=AuditLog.Action.DELETE,
                    app_label="records",
                    model_name="RecordMedia",
                    object_id=str(media.pk),
                    object_repr=f"RecordMedia {media.pk}",
                    message="record_media_purged_after_retention",
                    metadata={
                        "action": "record_media_purged_after_retention",
                        "patient_id": media.patient_id,
                        "media_public_id": str(media.public_id),
                        "media_type": media.media_type,
                    },
                )
                media.delete()
                purged_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Purged {purged_count} RecordMedia row(s); {failure_count} failure(s)."
            )
        )
