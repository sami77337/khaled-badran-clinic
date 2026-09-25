import hmac

from django.conf import settings
from django.db import connection
from django.http import HttpResponseNotFound, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .booking import dispatch_due_reminders
from .configuration import configuration_issues, is_available


REMINDER_DISPATCH_LIMIT = 20


@csrf_exempt
@require_POST
def reminder_dispatch(request):
    expected = (getattr(settings, "REMINDER_CRON_TOKEN", "") or "").strip()
    provided = (request.headers.get("X-KBC-Cron-Token") or "").strip()

    if not expected or not provided or not hmac.compare_digest(provided, expected):
        return HttpResponseNotFound()

    if not is_available() or configuration_issues(templates=True):
        return JsonResponse(
            {"ok": False, "error": "configuration_unavailable"},
            status=503,
        )

    if not connection.features.has_select_for_update:
        return JsonResponse(
            {"ok": False, "error": "row_locking_unavailable"},
            status=503,
        )

    counts = dispatch_due_reminders(limit=REMINDER_DISPATCH_LIMIT)
    failed = counts["failed"]
    payload = {
        "ok": failed == 0,
        "sent": counts["sent"],
        "skipped": counts["skipped"],
        "failed": failed,
    }
    return JsonResponse(payload, status=503 if failed else 200)
