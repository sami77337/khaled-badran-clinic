import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import PublicReview, SystemSetting
from apps.core.showcase import GOOGLE_REVIEW_AVERAGE_KEY, GOOGLE_REVIEW_COUNT_KEY


class Command(BaseCommand):
    help = "Import approved public-review source data from a local JSON file without committing review data to Git."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to a UTF-8 JSON file kept outside Git.")
        parser.add_argument(
            "--approve",
            action="store_true",
            help="Mark imported reviews approved for public display. Omit for a safe draft import.",
        )

    def handle(self, *args, **options):
        path = Path(options["path"]).expanduser()
        if not path.is_file():
            raise CommandError("Review import file does not exist.")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CommandError("Review import file is not valid UTF-8 JSON.") from exc

        if isinstance(payload, list):
            reviews = payload
            summary = None
        elif isinstance(payload, dict):
            reviews = payload.get("reviews")
            summary = payload.get("source_summary")
        else:
            reviews = None
            summary = None
        if not isinstance(reviews, list):
            raise CommandError("JSON must be a list or an object containing a reviews list.")

        created = 0
        updated = 0
        with transaction.atomic():
            for index, row in enumerate(reviews, start=1):
                if not isinstance(row, dict):
                    raise CommandError(f"Review row {index} must be an object.")
                reviewer_name = str(row.get("reviewer_name", "")).strip()
                body = str(row.get("body", "")).strip()
                language = str(row.get("language", "")).strip().lower()
                source = str(row.get("source", PublicReview.Source.GOOGLE)).strip().lower()
                source_reference = str(row.get("source_reference", "")).strip()
                try:
                    rating = int(row.get("rating"))
                except (TypeError, ValueError) as exc:
                    raise CommandError(f"Review row {index} has an invalid rating.") from exc
                if not reviewer_name or not body:
                    raise CommandError(f"Review row {index} requires reviewer_name and body.")
                if language not in {PublicReview.Language.ARABIC, PublicReview.Language.ENGLISH}:
                    raise CommandError(f"Review row {index} has an unsupported language.")
                if source not in {PublicReview.Source.GOOGLE, PublicReview.Source.OTHER}:
                    raise CommandError(f"Review row {index} has an unsupported source.")

                reviewed_at = row.get("reviewed_at") or None
                if reviewed_at:
                    try:
                        reviewed_at = date.fromisoformat(str(reviewed_at))
                    except ValueError as exc:
                        raise CommandError(f"Review row {index} has an invalid reviewed_at date.") from exc

                lookup = {
                    "source": source,
                    "reviewer_name": reviewer_name,
                    "body": body,
                }
                defaults = {
                    "rating": rating,
                    "language": language,
                    "source_reference": source_reference,
                    "is_active": bool(row.get("is_active", True)),
                    "is_featured": bool(row.get("is_featured", False)),
                    "display_order": max(0, int(row.get("display_order", 0))),
                    "reviewed_at": reviewed_at,
                }
                if options["approve"]:
                    defaults["is_approved_for_publication"] = True

                review, was_created = PublicReview.objects.update_or_create(
                    **lookup,
                    defaults=defaults,
                )
                review.full_clean()
                review.save()
                if was_created:
                    created += 1
                else:
                    updated += 1

            if isinstance(summary, dict):
                average = summary.get("average_rating")
                count = summary.get("review_count")
                if average not in (None, "") and count not in (None, ""):
                    try:
                        average_value = float(average)
                        count_value = int(count)
                    except (TypeError, ValueError) as exc:
                        raise CommandError("source_summary contains invalid values.") from exc
                    if not 0 <= average_value <= 5 or count_value < 0:
                        raise CommandError("source_summary values are outside the allowed range.")
                    SystemSetting.objects.update_or_create(
                        key=GOOGLE_REVIEW_AVERAGE_KEY,
                        defaults={
                            "value": f"{average_value:.1f}",
                            "value_type": SystemSetting.ValueType.STRING,
                            "description": "Current Google review average; owner-verified source summary.",
                        },
                    )
                    SystemSetting.objects.update_or_create(
                        key=GOOGLE_REVIEW_COUNT_KEY,
                        defaults={
                            "value": str(count_value),
                            "value_type": SystemSetting.ValueType.INTEGER,
                            "description": "Current Google review count; owner-verified source summary.",
                        },
                    )

        self.stdout.write(self.style.SUCCESS(f"Imported reviews: {created} created, {updated} updated."))
        if not options["approve"]:
            self.stdout.write("Imported rows remain drafts unless they were already approved.")
