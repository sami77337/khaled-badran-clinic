import logging

from django.core.management.base import BaseCommand, CommandError

from apps.core.offsite_backup import BackupError, run_offsite_backup, write_status

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create and verify one encrypted production offsite backup."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", required=True)

    def handle(self, *args, **options):
        run_id = options["run_id"]
        try:
            write_status(run_id, "running")
            logger.info("Offsite backup status=running.")
            run_offsite_backup(run_id)
            write_status(run_id, "success")
            logger.info("Offsite backup status=success.")
        except Exception as exc:
            try:
                write_status(run_id, "failed")
            except Exception:
                pass
            logger.warning("Offsite backup status=failed.")
            if isinstance(exc, BackupError):
                raise CommandError("Offsite backup failed.") from None
            raise CommandError("Offsite backup failed.") from None
