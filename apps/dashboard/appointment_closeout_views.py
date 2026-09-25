from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.booking import appointment_messages, operations
from apps.booking.forms import MarkNoShowForm
from apps.booking.message_template_validation import (
    validate_appointment_message_template,
)
from apps.booking.models import Appointment, AppointmentMessageTemplate
from apps.core.views import APPROVED_CLINIC_PHONE

from .views import (
    _dashboard_home_context,
    _dashboard_language,
    _staff_required,
    _validated_e164,
)


AR_STATUS_LABELS = {
    Appointment.Status.CONFIRMED: "مؤكد",
    Appointment.Status.ARRIVED: "وصل",
    Appointment.Status.COMPLETED: "مكتمل",
    Appointment.Status.NO_SHOW: "لم يحضر",
    Appointment.Status.CANCELLED: "ملغي",
    Appointment.Status.RESCHEDULED: "أعيدت جدولته",
}
MESSAGE_EVENT_STATUS = {
    AppointmentMessageTemplate.Event.ARRIVED: Appointment.Status.ARRIVED,
    AppointmentMessageTemplate.Event.NO_SHOW: Appointment.Status.NO_SHOW,
}


def _with_language(url, language):
    return f"{url}?lang=en" if language == "en" else url


def _queue_url(language, *, page=None):
    params = {}
    if language == "en":
        params["lang"] = "en"
    if page:
        params["page"] = page
    query = urlencode(params)
    route = reverse("dashboard_appointment_follow_up")
    return f"{route}?{query}" if query else route


def _settings_url(language):
    return _with_language(reverse("dashboard_appointment_message_settings"), language)


def _compose_url(appointment_id, event, language):
    route = reverse(
        "dashboard_appointment_message_compose",
        kwargs={"appointment_id": appointment_id},
    )
    params = {"event": event}
    if language == "en":
        params["lang"] = "en"
    return f"{route}?{urlencode(params)}"


def _appointment_detail_url(appointment_id, language):
    return _with_language(
        reverse("staff_appointment_detail", kwargs={"appointment_id": appointment_id}),
        language,
    )


def _patient_record_url(patient_id, language):
    return _with_language(
        reverse("dashboard_patient_record_detail", kwargs={"patient_id": patient_id}),
        language,
    )


def _operation_url(route_name, appointment_id, language):
    return _with_language(
        reverse(route_name, kwargs={"appointment_id": appointment_id}),
        language,
    )


def _whatsapp_compose_url(phone_number, text):
    normalized_phone = _validated_e164(phone_number)
    text = (text or "").strip()
    if not normalized_phone or not text:
        return ""
    return f"https://wa.me/{normalized_phone[1:]}?{urlencode({'text': text})}"


def _preview_template(text, *, language):
    text = (text or "").strip()
    if not text:
        return ""
    values = {
        "patient_name": "مريض" if language == "ar" else "Patient",
        "appointment_date": "2026-01-01",
        "appointment_time": "10:00",
        "clinic_phone": APPROVED_CLINIC_PHONE["display"],
    }
    try:
        validate_appointment_message_template(text)
        return text.format(**values)
    except (ValidationError, KeyError, ValueError, IndexError):
        return ""


def _decorate_appointment(appointment, language):
    appointment.follow_up_status_label = (
        AR_STATUS_LABELS.get(appointment.status, appointment.get_status_display())
        if language == "ar"
        else appointment.get_status_display()
    )
    appointment.follow_up_visit_type_label = (
        appointment.visit_type.name_ar
        if language == "ar" and appointment.visit_type_id
        else appointment.visit_type.name_en
        if appointment.visit_type_id
        else ("غير محدد" if language == "ar" else "Not specified")
    )
    appointment.follow_up_detail_url = _appointment_detail_url(appointment.id, language)
    appointment.follow_up_patient_url = _patient_record_url(
        appointment.patient_id, language
    )
    appointment.follow_up_arrived_url = _operation_url(
        "dashboard_appointment_follow_up_arrived",
        appointment.id,
        language,
    )
    appointment.follow_up_no_show_url = _operation_url(
        "dashboard_appointment_follow_up_no_show",
        appointment.id,
        language,
    )
    appointment.follow_up_complete_url = _operation_url(
        "dashboard_appointment_follow_up_complete",
        appointment.id,
        language,
    )
    appointment.follow_up_message_url = _compose_url(
        appointment.id,
        AppointmentMessageTemplate.Event.ARRIVED,
        language,
    )
    return appointment


@_staff_required
@require_GET
def appointment_follow_up(request):
    language = _dashboard_language(request)
    paginator = Paginator(
        operations.needs_classification_queryset().order_by("starts_at", "id"),
        25,
    )
    page_obj = paginator.get_page(request.GET.get("page"))
    appointments = [
        _decorate_appointment(appointment, language)
        for appointment in page_obj.object_list
    ]
    arrived_appointments = [
        _decorate_appointment(appointment, language)
        for appointment in operations.staff_appointment_queryset()
        .filter(status=Appointment.Status.ARRIVED)
        .order_by("starts_at", "id")[:25]
    ]

    context = _dashboard_home_context(
        request,
        language=language,
        metrics={},
        schedule_items=[],
    )
    alternate_language = "en" if language == "ar" else "ar"
    queue_url = _queue_url(language)
    context.update(
        {
            "page_key": "appointment_follow_up",
            "page_title": (
                "المواعيد التي تحتاج متابعة"
                if language == "ar"
                else "Appointments Needing Follow-up"
            ),
            "meta_description": (
                "قائمة تشغيلية للمواعيد التي مر وقتها وتحتاج تصنيفًا يدويًا."
                if language == "ar"
                else "Operational queue for past appointments that still need manual classification."
            ),
            "canonical_url": request.build_absolute_uri(queue_url),
            "dashboard_language_switch_url": _queue_url(alternate_language),
            "active_dashboard_nav": "appointments",
            "staff_appointments_url": _with_language(
                reverse("staff_appointment_list"),
                language,
            ),
            "message_settings_url": _settings_url(language),
            "appointments": appointments,
            "arrived_appointments": arrived_appointments,
            "page_obj": page_obj,
            "previous_page_url": (
                _queue_url(language, page=page_obj.previous_page_number())
                if page_obj.has_previous()
                else ""
            ),
            "next_page_url": (
                _queue_url(language, page=page_obj.next_page_number())
                if page_obj.has_next()
                else ""
            ),
        }
    )
    return render(request, "dashboard/appointment_follow_up.html", context)


def _message_setting_rows(language, *, override=None):
    stored = {
        row.event: row
        for row in AppointmentMessageTemplate.objects.filter(
            event__in=AppointmentMessageTemplate.Event.values
        )
    }
    rows = []
    for event in AppointmentMessageTemplate.Event.values:
        row = stored.get(event)
        is_active = row.is_active if row else False
        text_ar = row.text_ar if row else ""
        text_en = row.text_en if row else ""
        if override and override.get("event") == event:
            is_active = override["is_active"]
            text_ar = override["text_ar"]
            text_en = override["text_en"]
        label = (
            (
                "بعد تسجيل الوصول"
                if event == AppointmentMessageTemplate.Event.ARRIVED
                else "بعد عدم الحضور"
            )
            if language == "ar"
            else (
                "After Arrived"
                if event == AppointmentMessageTemplate.Event.ARRIVED
                else "After No-show"
            )
        )
        rows.append(
            {
                "event": event,
                "label": label,
                "is_active": is_active,
                "text_ar": text_ar,
                "text_en": text_en,
                "preview_ar": _preview_template(text_ar, language="ar"),
                "preview_en": _preview_template(text_en, language="en"),
            }
        )
    return rows


@_staff_required
@require_http_methods(["GET", "POST"])
def appointment_message_settings(request):
    language = _dashboard_language(request)
    override = None
    if request.method == "POST":
        event = (request.POST.get("event") or "").strip()
        if event not in AppointmentMessageTemplate.Event.values:
            raise Http404
        override = {
            "event": event,
            "is_active": request.POST.get("is_active") == "on",
            "text_ar": request.POST.get("text_ar") or "",
            "text_en": request.POST.get("text_en") or "",
        }
        try:
            appointment_messages.save_appointment_message_template(
                event=event,
                is_active=override["is_active"],
                text_ar=override["text_ar"],
                text_en=override["text_en"],
                actor=request.user,
            )
        except ValidationError:
            messages.error(
                request,
                "تعذر حفظ الإعدادات. تحقق من النصوص والمتغيرات المسموحة."
                if language == "ar"
                else "Settings could not be saved. Check the texts and allowed placeholders.",
            )
        else:
            messages.success(
                request,
                "تم حفظ إعدادات الرسالة."
                if language == "ar"
                else "Appointment message settings saved.",
            )
            return redirect(_settings_url(language))

    context = _dashboard_home_context(
        request,
        language=language,
        metrics={},
        schedule_items=[],
    )
    alternate_language = "en" if language == "ar" else "ar"
    settings_url = _settings_url(language)
    context.update(
        {
            "page_key": "appointment_message_settings",
            "page_title": "رسائل المواعيد"
            if language == "ar"
            else "Appointment Messages",
            "canonical_url": request.build_absolute_uri(settings_url),
            "dashboard_language_switch_url": _settings_url(alternate_language),
            "active_dashboard_nav": "appointments",
            "follow_up_url": _queue_url(language),
            "settings_url": settings_url,
            "message_settings": _message_setting_rows(language, override=override),
        }
    )
    return render(request, "dashboard/appointment_message_settings.html", context)


def _operation_failed(request, language):
    messages.error(
        request,
        "تعذر تنفيذ الإجراء. حدّث الصفحة وراجع حالة الموعد."
        if language == "ar"
        else "The action could not be completed. Refresh the page and review the appointment status.",
    )
    return redirect(_queue_url(language))


@_staff_required
@require_POST
def appointment_follow_up_arrived(request, appointment_id):
    language = _dashboard_language(request)
    get_object_or_404(operations.staff_appointment_queryset(), id=appointment_id)
    try:
        operations.mark_arrived(appointment_id, actor=request.user)
    except (ValidationError, Appointment.DoesNotExist):
        return _operation_failed(request, language)
    messages.success(
        request,
        "تم تسجيل وصول المريض." if language == "ar" else "Appointment marked arrived.",
    )
    return redirect(
        _compose_url(
            appointment_id,
            AppointmentMessageTemplate.Event.ARRIVED,
            language,
        )
    )


@_staff_required
@require_POST
def appointment_follow_up_no_show(request, appointment_id):
    language = _dashboard_language(request)
    appointment = get_object_or_404(
        operations.staff_appointment_queryset(),
        id=appointment_id,
    )
    form = MarkNoShowForm(request.POST, language=language)
    if not form.is_valid():
        messages.error(
            request,
            "يرجى إدخال سبب عدم الحضور."
            if language == "ar"
            else "A no-show reason is required.",
        )
        return redirect(_queue_url(language))
    try:
        operations.mark_no_show(
            appointment.id,
            actor=request.user,
            note=form.cleaned_data["note"],
        )
    except ValidationError:
        return _operation_failed(request, language)
    messages.success(
        request,
        "تم تسجيل عدم حضور المريض."
        if language == "ar"
        else "Appointment marked no-show.",
    )
    return redirect(
        _compose_url(
            appointment.id,
            AppointmentMessageTemplate.Event.NO_SHOW,
            language,
        )
    )


@_staff_required
@require_http_methods(["GET", "POST"])
def appointment_message_compose(request, appointment_id):
    language = _dashboard_language(request)
    event = (request.POST.get("event") or request.GET.get("event") or "").strip()
    expected_status = MESSAGE_EVENT_STATUS.get(event)
    if expected_status is None:
        raise Http404

    appointment = get_object_or_404(
        operations.staff_appointment_queryset(),
        id=appointment_id,
    )
    if appointment.status != expected_status:
        raise Http404

    phone = _validated_e164(appointment.effective_whatsapp_phone)
    compose_url = _compose_url(appointment.id, event, language)

    try:
        default_message = appointment_messages.render_ready_message(
            appointment,
            event=event,
            language=language,
            clinic_phone=APPROVED_CLINIC_PHONE["display"],
        )
    except ValidationError:
        # Stored rows are validated on the supported settings path. Fail closed
        # instead of returning a 500 if legacy/manual database edits bypassed it.
        default_message = ""

    message_text = (
        request.POST.get("message_text", "")
        if request.method == "POST"
        else default_message
    )

    if request.method == "POST":
        message_text = message_text.strip()
        if not message_text:
            messages.error(
                request,
                "أدخل نص الرسالة أو اختر بدون رسالة."
                if language == "ar"
                else "Enter a message or choose No Message.",
            )
        elif len(message_text) > 2000:
            messages.error(
                request,
                "الرسالة طويلة جدًا."
                if language == "ar"
                else "The message is too long.",
            )
        elif not phone:
            messages.error(
                request,
                "لا يوجد رقم واتساب صالح لهذا الموعد."
                if language == "ar"
                else "This appointment has no valid WhatsApp number.",
            )
        else:
            return redirect(_whatsapp_compose_url(phone, message_text))

    event_label = (
        (
            "تم تسجيل الوصول"
            if event == AppointmentMessageTemplate.Event.ARRIVED
            else "لم يحضر"
        )
        if language == "ar"
        else (
            "Arrived"
            if event == AppointmentMessageTemplate.Event.ARRIVED
            else "No-show"
        )
    )

    context = _dashboard_home_context(
        request,
        language=language,
        metrics={},
        schedule_items=[],
    )
    alternate_language = "en" if language == "ar" else "ar"
    context.update(
        {
            "page_key": "appointment_message_compose",
            "page_title": "رسالة بعد التصنيف"
            if language == "ar"
            else "Post-classification Message",
            "canonical_url": request.build_absolute_uri(compose_url),
            "dashboard_language_switch_url": _compose_url(
                appointment.id,
                event,
                alternate_language,
            ),
            "active_dashboard_nav": "appointments",
            "appointment": appointment,
            "event": event,
            "event_label": event_label,
            "compose_url": compose_url,
            "follow_up_url": _queue_url(language),
            "settings_url": _settings_url(language),
            "message_text": message_text,
            "has_default_message": bool(default_message),
            "whatsapp_available": bool(phone),
        }
    )
    return render(request, "dashboard/appointment_message_compose.html", context)


@_staff_required
@require_POST
def appointment_follow_up_complete(request, appointment_id):
    language = _dashboard_language(request)
    get_object_or_404(operations.staff_appointment_queryset(), id=appointment_id)
    try:
        operations.mark_completed(appointment_id, actor=request.user)
    except (ValidationError, Appointment.DoesNotExist):
        return _operation_failed(request, language)
    messages.success(
        request,
        "تم تسجيل إكمال الزيارة." if language == "ar" else "Visit marked complete.",
    )
    return redirect(_queue_url(language))
