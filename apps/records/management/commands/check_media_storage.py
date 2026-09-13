"""Runtime deployment gate for protected media on an attached persistent disk."""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.records.durability import check_media_storage


class Command(BaseCommand):
    help = "Verify protected media directories are on the runtime persistent mount."
    # No DB or unrelated settings checks: this command must also diagnose a
    # storage failure when other deployment prerequisites are unavailable.
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--mount-root", default="/var/data",
            help="Actual provider-configured disk mount path (default: /var/data).",
        )
        parser.add_argument(
            "--write-probe", action="store_true",
            help="Also write/read/remove one exclusive synthetic file in each media root.",
        )
        parser.add_argument("--json", action="store_true", dest="json_output")

    def handle(self, *args, **options):
        report = check_media_storage(
            mount_root=options["mount_root"], write_probe=options["write_probe"]
        )
        if options["json_output"]:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Media storage check: {report['status']}")
            for check in report["checks"]:
                self.stdout.write(f"{check['name']}: {check['status']}")
        if report["status"] != "passed":
            raise CommandError(
                "Media storage check failed. See docs/PRODUCTION_MEDIA_DURABILITY.md."
            )
