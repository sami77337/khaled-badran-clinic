"""Trigger one production backup and wait for its sanitized completion status."""

import json
import os
import sys
import time
import urllib.error
import urllib.request


POLL_SECONDS = 15
MAX_WAIT_SECONDS = 55 * 60


def _env(name):
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError("backup cron configuration missing")
    return value


def _request(url, token, request_host, payload=None):
    body = None
    headers = {
        "X-KBC-Backup-Token": token,
        "Host": request_host,
        "X-Forwarded-Proto": "https",
    }
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body or b"", headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.loads(response.read(4096).decode("utf-8"))


def main():
    try:
        origin = _env("KBC_BACKUP_INTERNAL_ORIGIN").rstrip("/")
        if not origin.startswith(("http://", "https://")):
            raise RuntimeError("backup cron configuration invalid")
        token = _env("KBC_BACKUP_CRON_TOKEN")
        request_host = _env("KBC_BACKUP_REQUEST_HOST")

        status_code, response = _request(
            f"{origin}/integrations/backup/run/",
            token,
            request_host,
        )
        if status_code != 202 or response.get("status") != "accepted":
            raise RuntimeError("backup trigger failed")
        run_id = str(response.get("run_id") or "")
        if not run_id:
            raise RuntimeError("backup trigger failed")

        deadline = time.monotonic() + MAX_WAIT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(POLL_SECONDS)
            try:
                status_code, response = _request(
                    f"{origin}/integrations/backup/status/",
                    token,
                    request_host,
                    {"run_id": run_id},
                )
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    continue
                raise
            status = response.get("status")
            if status == "success":
                print("offsite_backup status=success")
                return 0
            if status == "failed":
                print("offsite_backup status=failed", file=sys.stderr)
                return 1
            if status not in {"queued", "running"}:
                raise RuntimeError("backup status invalid")

        print("offsite_backup status=timeout", file=sys.stderr)
        return 1
    except Exception:
        print("offsite_backup status=failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
