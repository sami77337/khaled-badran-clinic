"""Authenticated internal trigger/status endpoints for offsite backups."""

import hmac
import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timezone

from django.conf import settings
from django.http import HttpResponseNotFound, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .offsite_backup import BackupError, read_status, write_status


def _authorized(request):
    expected = (os.getenv("KBC_BACKUP_CRON_TOKEN") or "").strip()
    provided = (request.headers.get("X-KBC-Backup-Token") or "").strip()
    return bool(expected and provided and hmac.compare_digest(expected, provided))


def _not_found():
    return HttpResponseNotFound()


def _run_id():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(6)}"


@csrf_exempt
@require_POST
def backup_trigger(request):
    if not settings.PRODUCTION or not _authorized(request):
        return _not_found()

    run_id = _run_id()
    try:
        write_status(run_id, "queued")
        env = os.environ.copy()
        env["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
        subprocess.Popen(
            [sys.executable, "manage.py", "offsite_backup", "--run-id", run_id],
            cwd=settings.BASE_DIR,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=None,
            stderr=None,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        try:
            write_status(run_id, "failed")
        except BackupError:
            pass
        return JsonResponse({"status": "failed"}, status=503)

    return JsonResponse({"status": "accepted", "run_id": run_id}, status=202)


@csrf_exempt
@require_POST
def backup_status(request):
    if not settings.PRODUCTION or not _authorized(request):
        return _not_found()

    try:
        payload = json.loads(request.body.decode("utf-8"))
        run_id = str(payload.get("run_id") or "")
        status = read_status(run_id)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, BackupError):
        status = None

    if status is None:
        return JsonResponse({"status": "unknown"}, status=404)
    return JsonResponse(status)
