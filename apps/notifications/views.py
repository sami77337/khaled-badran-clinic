import json
from functools import wraps

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import FileResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_GET, require_POST

from .models import StaffPushSubscription
from .services import vapid_credentials, vapid_public_key
from .validation import validate_endpoint, validate_subscription


def staff_api(view):
    @wraps(view)
    @never_cache
    @sensitive_post_parameters()
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "authentication_required"}, status=401)
        if not request.user.is_active or not request.user.is_staff:
            return JsonResponse({"error": "staff_required"}, status=403)
        return view(request, *args, **kwargs)
    return wrapped


def json_body(request):
    if request.content_type != "application/json" or int(request.META.get("CONTENT_LENGTH") or 0) > 4096:
        raise ValueError("Invalid request.")
    if len(request.body) > 4096:
        raise ValueError("Invalid request.")
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValueError("Invalid request.")
    return data


@staff_api
@require_GET
def configuration(request):
    public_key = vapid_public_key()
    return JsonResponse({"available": bool(public_key), "publicKey": public_key})


@staff_api
@require_POST
@csrf_protect
@sensitive_variables()
def subscribe(request):
    try:
        values = validate_subscription(json_body(request))
    except (ValueError, TypeError, OverflowError, RecursionError):
        return JsonResponse({"error": "invalid_subscription"}, status=400)
    if vapid_credentials() is None:
        return JsonResponse({"error": "unavailable"}, status=503)
    try:
        with transaction.atomic():
            # Serialize per-user inserts so the device limit cannot race.
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            existing = StaffPushSubscription.objects.filter(endpoint=values["endpoint"]).first()
            if existing is not None and existing.user_id != request.user.pk:
                return JsonResponse({"error": "subscription_in_use"}, status=409)
            if existing is None and StaffPushSubscription.objects.filter(user=request.user).count() >= 10:
                return JsonResponse({"error": "device_limit"}, status=409)
            subscription, _ = StaffPushSubscription.objects.get_or_create(
                endpoint=values.pop("endpoint"), defaults={"user": request.user, **values},
            )
            # A concurrent insert by another user must never transfer ownership.
            if subscription.user_id != request.user.pk:
                return JsonResponse({"error": "subscription_in_use"}, status=409)
            for field, value in values.items():
                setattr(subscription, field, value)
            subscription.save(update_fields=[*values, "updated_at"])
    except Exception:
        return JsonResponse({"error": "unavailable"}, status=503)
    return JsonResponse({"subscribed": True})


@staff_api
@require_POST
@csrf_protect
@sensitive_variables()
def subscription_state(request, remove=False):
    try:
        data = json_body(request)
        if set(data) != {"endpoint"}:
            raise ValueError("Invalid request.")
        endpoint = validate_endpoint(data["endpoint"])
    except (ValueError, TypeError, OverflowError, RecursionError):
        return JsonResponse({"error": "invalid_subscription"}, status=400)
    try:
        subscription = StaffPushSubscription.objects.filter(user=request.user, endpoint=endpoint)
        if remove:
            subscription.delete()
            return JsonResponse({"subscribed": False})
        return JsonResponse({"subscribed": subscription.exists()})
    except Exception:
        return JsonResponse({"error": "unavailable"}, status=503)


@require_GET
def service_worker(request):
    # Root scope is needed for both /dashboard/ and /staff/. No private caching.
    response = FileResponse((settings.BASE_DIR / "static" / "sw.js").open("rb"), content_type="text/javascript")
    response["Cache-Control"] = "no-cache"
    response["Service-Worker-Allowed"] = "/"
    return response
