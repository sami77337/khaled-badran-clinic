from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.booking import operations
from apps.booking.forms import MarkNoShowForm
from apps.booking.models import Appointment

from .views import _dashboard_home_context, _dashboard_language, _staff_required


AR_STATUS_LABELS = {
    Appointment.Status.CONFIRMED: "مؤكد",
    Appointment.Status.ARRIVED: "وصل",
    Appointment.Status.COMPLETED: "مكتمل",
    Appointment.Status.NO_SHOW: "لم يحضر",
    Appointment.Status.CANCELLED: "ملغي",
    Appointment.Status.RESCHEDULED: "أعيدت جدولته",
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
    appointment.follow_up_patient_url = _patient_record_url(appointment.patient_id, language)
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
        "تم تسجيل وصول المريض."
        if language == "ar"
        else "Appointment marked arrived.",
    )
    return redirect(_queue_url(language))


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
    return redirect(_queue_url(language))


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
        "تم تسجيل إكمال الزيارة."
        if language == "ar"
        else "Visit marked complete.",
    )
    return redirect(_queue_url(language))
