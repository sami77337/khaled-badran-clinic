import json

from django.core.management.base import BaseCommand

from apps.patients.temporary_otp import backfill_unverified_profiles


class Command(BaseCommand):
    help = "Preview eligible temporary patient profiles; use --apply to create them. Counts only."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Create safe missing profiles.")

    def handle(self, *args, **options):
        counts = backfill_unverified_profiles(apply=options["apply"])
        self.stdout.write(json.dumps(counts, sort_keys=True))
