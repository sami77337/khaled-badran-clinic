from functools import wraps
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.db import OperationalError
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_http_methods

from apps.booking import operations, rate_limits, rescheduling, services
from apps.booking.views import _booking_url, _context, _language


def _private(view):
    @wraps(view)
    @never_cache
    def wrapped(*args, **kwargs):
        response = view(*args, **kwargs)
        response["Referrer-Policy"] = "no-referrer"
        response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response
    return wrapped


def _reschedule_context(request, language, token, route, **extra):
    language = _language(language)
    alternate = "en" if language == "ar" else "ar"
    switch_url = _booking_url(route, alternate, token=token)
    switch_query = {}
    if extra.get("selected_date"):
        switch_query["date"] = extra["selected_date"].isoformat()
    if extra.get("starts_at"):
        switch_query["starts_at"] = extra["starts_at"]
    if switch_query:
        switch_url += "?" + urlencode(switch_query)
    return _context(
        request, language,
        page_title="إعادة جدولة موعدك" if language == "ar" else "Reschedule Your Appointment",
        is_reschedule=True,
        suppress_whatsapp_quick_link=True,
        booking_steps=[
            ("slot", "التاريخ والوقت" if language == "ar" else "Date & Time"),
            ("confirm", "التأكيد" if language == "ar" else "Confirm"),
        ],
        slots_url=_booking_url("patient_reschedule", language, token=token),
        confirm_url=_booking_url("patient_reschedule_confirm", language, token=token),
        language_switch={"label": "English" if language == "ar" else "العربية", "url": switch_url},
        **extra,
    )


def _unavailable(request, language, *, retry_url=None, status=400):
    # Never render a failed capability/slot with patient or appointment context.
    return render(request, "booking/reschedule_unavailable.html", _context(
        request, language, retry_url=retry_url, suppress_whatsapp_quick_link=True,
    ), status=status)


@_private
@require_GET
def select_slot(request, token, language="ar"):
    try:
        appointment = rescheduling.resolve_reschedule_token(token)
        slots = services.generate_available_slots(
            appointment.visit_type, doctor=appointment.doctor,
            exclude_appointment_id=appointment.pk,
        )
    except (ValidationError, OperationalError):
        return _unavailable(request, language)
    slots = [slot for slot in slots if slot.starts_at != appointment.starts_at]
    return render(request, "booking/select_slot.html", _reschedule_context(
        request, language, token, "patient_reschedule",
        active_step="slot", appointment=appointment, visit_type=appointment.visit_type,
        **_slot_context(slots, request.GET),
    ))


def _slot_context(slots, query):
    selected = next((slot for slot in slots if slot.value == query.get("starts_at")), None)
    grouped = services.group_slots_by_date(slots)
    day = selected.local_date.isoformat() if selected else query.get("date")
    group = next((item for item in grouped if item["date"].isoformat() == day), None)
    group = group or (grouped[0] if grouped else None)
    return {
        "grouped_slots": grouped,
        "selected_date": group["date"] if group else None,
        "selected_slot": selected,
        "starts_at": selected.value if selected else "",
    }


@_private
@require_http_methods(["GET", "POST"])
@csrf_protect
def confirm(request, token, language="ar"):
    try:
        appointment = rescheduling.resolve_reschedule_token(token)
    except (ValidationError, OperationalError):
        return _unavailable(request, language)
    retry_url = _booking_url("patient_reschedule", language, token=token)
    starts_at = request.POST.get("starts_at") if request.method == "POST" else request.GET.get("starts_at")
    try:
        if request.method == "POST":
            if not rate_limits.check_public_booking_ip_rate_limit(request).allowed:
                return _unavailable(request, language, status=429)
            appointment = rescheduling.patient_reschedule_appointment(token=token, starts_at=starts_at)
            return redirect(_booking_url(
                "patient_reschedule_success", language,
                token=rescheduling.make_reschedule_receipt(appointment),
            ))
        starts_at, _ = operations.validate_reschedule_slot(appointment, starts_at)
        if starts_at == appointment.starts_at:
            raise ValidationError(rescheduling.UNAVAILABLE)
    except (ValidationError, ValueError, OverflowError, OperationalError):
        return _unavailable(request, language, retry_url=retry_url)
    return render(request, "booking/reschedule_confirm.html", _reschedule_context(
        request, language, token, "patient_reschedule_confirm",
        active_step="confirm", appointment=appointment,
        starts_at=starts_at.isoformat(), slot_display=timezone.localtime(starts_at),
    ))


@_private
@require_GET
def success(request, token, language="ar"):
    try:
        appointment = rescheduling.resolve_reschedule_token(token, receipt=True)
    except (ValidationError, OperationalError):
        return _unavailable(request, language)
    return render(request, "booking/reschedule_success.html", _reschedule_context(
        request, language, token, "patient_reschedule_success", appointment=appointment,
    ))
