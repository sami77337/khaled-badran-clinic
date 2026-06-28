from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.booking.forms import (
    CancelAppointmentForm,
    MarkNoShowForm,
    PublicBookingForm,
    RescheduleAppointmentForm,
    StatusNoteForm,
)
from apps.booking.models import Appointment
from apps.booking import operations, rate_limits, services
from apps.booking.selectors import get_active_doctor, get_active_visit_type
from apps.clinic.models import Doctor, VisitType
from apps.core.models import AuditLog
from apps.core.views import _base_context


def _language(language):
    return "en" if language == "en" else "ar"


def _booking_url(name, language, **kwargs):
    suffix = "_en" if _language(language) == "en" else ""
    return reverse(f"{name}{suffix}", kwargs=kwargs or None)


def _context(request, language, **extra):
    language = _language(language)
    context = _base_context(request, "booking", language)
    context.update(
        {
            "booking_home_url": _booking_url("book", language),
            "visit_type_url": _booking_url("booking_visit_type", language),
            "slots_url": _booking_url("booking_slots", language),
            "confirm_url": _booking_url("booking_confirm", language),
            "booking_steps": [
                ("visit_type", "نوع الزيارة" if language == "ar" else "Visit type"),
                ("slot", "الوقت" if language == "ar" else "Time"),
                ("confirm", "التأكيد" if language == "ar" else "Confirm"),
            ],
        }
    )
    context.update(extra)
    return context


def _render_unavailable(request, language, reason):
    return render(
        request,
        "booking/unavailable.html",
        _context(
            request,
            language,
            active_step="visit_type",
            reason=reason,
        ),
    )


def book_start(request, language="ar"):
    return select_visit_type(request, language=language)


def select_visit_type(request, language="ar"):
    language = _language(language)
    settings = services.get_booking_settings()
    if not settings.enabled:
        reason = "الحجز الإلكتروني غير متاح حالياً." if language == "ar" else "Online booking is currently unavailable."
        return _render_unavailable(request, language, reason)

    doctor = get_active_doctor()
    visit_types = list(services.public_visit_types())
    if doctor is None or not visit_types:
        reason = (
            "لا توجد أنواع زيارات متاحة للحجز حالياً."
            if language == "ar"
            else "No visit types are currently available for booking."
        )
        return _render_unavailable(request, language, reason)

    return render(
        request,
        "booking/select_visit_type.html",
        _context(
            request,
            language,
            active_step="visit_type",
            visit_types=visit_types,
            doctor=doctor,
        ),
    )


def select_slot(request, language="ar"):
    language = _language(language)
    settings = services.get_booking_settings()
    if not settings.enabled:
        reason = "الحجز الإلكتروني غير متاح حالياً." if language == "ar" else "Online booking is currently unavailable."
        return _render_unavailable(request, language, reason)

    doctor = get_active_doctor()
    visit_type = get_active_visit_type(request.GET.get("visit_type"), doctor=doctor)
    if visit_type is None:
        return redirect(_booking_url("book", language))

    selected_date = request.GET.get("date") or None
    try:
        slots = services.generate_available_slots(
            visit_type=visit_type,
            target_date=selected_date,
            doctor=doctor,
        )
    except ValueError:
        slots = []

    grouped_slots = services.group_slots_by_date(slots)
    return render(
        request,
        "booking/select_slot.html",
        _context(
            request,
            language,
            active_step="slot",
            visit_type=visit_type,
            grouped_slots=grouped_slots,
            selected_date=selected_date,
        ),
    )


def confirm_booking(request, language="ar"):
    language = _language(language)
    doctor = get_active_doctor()

    if request.method == "POST":
        form = PublicBookingForm(request.POST, language=language)
        ip_limit = rate_limits.check_public_booking_ip_rate_limit(request)
        if not ip_limit.allowed:
            form.is_valid()
            form.add_error(None, ip_limit.message)
        elif form.is_valid():
            phone_limit = rate_limits.check_public_booking_phone_rate_limit(form.normalized_phone)
            if not phone_limit.allowed:
                form.add_error(None, phone_limit.message)
            else:
                try:
                    appointment = form.save()
                except ValidationError as exc:
                    form.add_error(None, exc)
                else:
                    return redirect(
                        _booking_url(
                            "booking_success",
                            language,
                            public_token=appointment.public_token,
                        )
                    )
    else:
        initial = {
            "visit_type": request.GET.get("visit_type"),
            "starts_at": request.GET.get("starts_at"),
            "same_as_phone": True,
        }
        form = PublicBookingForm(initial=initial, language=language)
        visit_type = get_active_visit_type(initial["visit_type"], doctor=doctor)
        try:
            if visit_type is None:
                raise ValidationError("Select an active visit type.")
            services.validate_public_booking_request(
                visit_type=visit_type,
                starts_at=initial["starts_at"],
                doctor=doctor,
            )
        except ValidationError:
            return redirect(_booking_url("book", language))

    visit_type = None
    starts_at = None
    if form.data:
        visit_type = get_active_visit_type(form.data.get("visit_type"), doctor=doctor)
        starts_at = form.data.get("starts_at")
    elif form.initial:
        visit_type = get_active_visit_type(form.initial.get("visit_type"), doctor=doctor)
        starts_at = form.initial.get("starts_at")

    slot_display = None
    if starts_at:
        try:
            slot_display = timezone.localtime(services.parse_slot_datetime(starts_at))
        except ValidationError:
            slot_display = None

    return render(
        request,
        "booking/confirm.html",
        _context(
            request,
            language,
            active_step="confirm",
            form=form,
            visit_type=visit_type,
            slot_display=slot_display,
        ),
    )


def booking_success(request, public_token, language="ar"):
    appointment = get_object_or_404(
        Appointment.objects.select_related("doctor", "patient", "visit_type"),
        public_token=public_token,
    )
    return render(
        request,
        "booking/success.html",
        _context(
            request,
            language,
            active_step="success",
            appointment=appointment,
        ),
    )


def _staff_required(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url=reverse("admin:login"))
        if not request.user.is_staff:
            return HttpResponseForbidden("Staff access required.")
        return view_func(request, *args, **kwargs)

    return wrapped


def _staff_context(request, **extra):
    context = _base_context(request, "booking", "en")
    context.update(
        {
            "page_key": "staff_appointments",
            "page_title": "Staff appointments | Dr. Khaled Badran Clinic",
            "staff_appointments_url": reverse("staff_appointment_list"),
        }
    )
    context.update(extra)
    return context


def _filtered_staff_appointments(request):
    queryset = operations.staff_appointment_queryset()
    status = request.GET.get("status") or ""
    doctor_id = request.GET.get("doctor") or ""
    visit_type_id = request.GET.get("visit_type") or ""
    scope = request.GET.get("scope") or "upcoming"
    date_from = request.GET.get("date_from") or ""
    date_to = request.GET.get("date_to") or ""
    search = (request.GET.get("q") or "").strip()

    if status:
        queryset = queryset.filter(status=status)
    if doctor_id:
        queryset = queryset.filter(doctor_id=doctor_id)
    if visit_type_id:
        queryset = queryset.filter(visit_type_id=visit_type_id)
    if search:
        queryset = queryset.filter(
            Q(patient__full_name__icontains=search)
            | Q(patient__phone_raw__icontains=search)
            | Q(patient__phone_e164__icontains=search)
        )

    today = timezone.localdate()
    if date_from:
        queryset = queryset.filter(starts_at__date__gte=date_from)
    elif scope == "upcoming":
        queryset = queryset.filter(starts_at__date__gte=today)
    if date_to:
        queryset = queryset.filter(starts_at__date__lte=date_to)
    elif scope == "past":
        queryset = queryset.filter(starts_at__date__lt=today)

    if scope == "past":
        queryset = queryset.order_by("-starts_at", "id")
    else:
        queryset = queryset.order_by("starts_at", "id")

    filters = {
        "status": status,
        "doctor": doctor_id,
        "visit_type": visit_type_id,
        "scope": scope,
        "date_from": date_from,
        "date_to": date_to,
        "q": search,
    }
    return queryset, filters


@_staff_required
def staff_appointment_list(request):
    queryset, filters = _filtered_staff_appointments(request)
    paginator = Paginator(queryset, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "booking/staff/appointment_list.html",
        _staff_context(
            request,
            appointments=page_obj.object_list,
            page_obj=page_obj,
            filters=filters,
            status_choices=Appointment.Status.choices,
            doctors=Doctor.objects.filter(is_active=True).order_by("display_order", "full_name_en"),
            visit_types=VisitType.objects.filter(is_active=True).order_by("display_order", "name_en"),
        ),
    )


def _staff_detail_context(request, appointment, **extra):
    audit_logs = AuditLog.objects.filter(
        app_label="booking",
        model_name="Appointment",
        object_id=str(appointment.id),
    ).select_related("user")
    context = _staff_context(
        request,
        appointment=appointment,
        status_history=appointment.status_history.select_related("changed_by"),
        audit_logs=audit_logs,
        cancel_form=CancelAppointmentForm(),
        reschedule_form=RescheduleAppointmentForm(appointment=appointment),
        no_show_form=MarkNoShowForm(),
        arrived_form=StatusNoteForm(),
        complete_form=StatusNoteForm(),
    )
    context.update(extra)
    return context


@_staff_required
def staff_appointment_detail(request, appointment_id):
    appointment = get_object_or_404(
        operations.staff_appointment_queryset().prefetch_related("status_history"),
        id=appointment_id,
    )
    return render(
        request,
        "booking/staff/appointment_detail.html",
        _staff_detail_context(request, appointment),
    )


def _require_post(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    return None


def _redirect_detail(appointment_id):
    return redirect("staff_appointment_detail", appointment_id=appointment_id)


@_staff_required
def staff_appointment_cancel(request, appointment_id):
    not_allowed = _require_post(request)
    if not_allowed:
        return not_allowed
    appointment = get_object_or_404(operations.staff_appointment_queryset(), id=appointment_id)
    form = CancelAppointmentForm(request.POST)
    if form.is_valid():
        try:
            appointment = operations.cancel_appointment(
                appointment_id,
                actor=request.user,
                note=form.cleaned_data["note"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Appointment cancelled.")
            return _redirect_detail(appointment.id)
    return render(
        request,
        "booking/staff/appointment_detail.html",
        _staff_detail_context(request, appointment, cancel_form=form),
        status=400,
    )


@_staff_required
def staff_appointment_reschedule(request, appointment_id):
    not_allowed = _require_post(request)
    if not_allowed:
        return not_allowed
    appointment = get_object_or_404(operations.staff_appointment_queryset(), id=appointment_id)
    form = RescheduleAppointmentForm(request.POST, appointment=appointment)
    if form.is_valid():
        try:
            appointment = operations.reschedule_appointment(
                appointment_id,
                starts_at=form.cleaned_data["starts_at"],
                actor=request.user,
                note=form.cleaned_data.get("note", ""),
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Appointment rescheduled.")
            return _redirect_detail(appointment.id)
    return render(
        request,
        "booking/staff/appointment_detail.html",
        _staff_detail_context(request, appointment, reschedule_form=form),
        status=400,
    )


@_staff_required
def staff_appointment_arrived(request, appointment_id):
    not_allowed = _require_post(request)
    if not_allowed:
        return not_allowed
    appointment = get_object_or_404(operations.staff_appointment_queryset(), id=appointment_id)
    form = StatusNoteForm(request.POST)
    if form.is_valid():
        try:
            appointment = operations.mark_arrived(
                appointment_id,
                actor=request.user,
                note=form.cleaned_data.get("note", ""),
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Appointment marked arrived.")
            return _redirect_detail(appointment.id)
    return render(
        request,
        "booking/staff/appointment_detail.html",
        _staff_detail_context(request, appointment, arrived_form=form),
        status=400,
    )


@_staff_required
def staff_appointment_complete(request, appointment_id):
    not_allowed = _require_post(request)
    if not_allowed:
        return not_allowed
    appointment = get_object_or_404(operations.staff_appointment_queryset(), id=appointment_id)
    form = StatusNoteForm(request.POST)
    if form.is_valid():
        try:
            appointment = operations.mark_completed(
                appointment_id,
                actor=request.user,
                note=form.cleaned_data.get("note", ""),
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Appointment completed.")
            return _redirect_detail(appointment.id)
    return render(
        request,
        "booking/staff/appointment_detail.html",
        _staff_detail_context(request, appointment, complete_form=form),
        status=400,
    )


@_staff_required
def staff_appointment_no_show(request, appointment_id):
    not_allowed = _require_post(request)
    if not_allowed:
        return not_allowed
    appointment = get_object_or_404(operations.staff_appointment_queryset(), id=appointment_id)
    form = MarkNoShowForm(request.POST)
    if form.is_valid():
        try:
            appointment = operations.mark_no_show(
                appointment_id,
                actor=request.user,
                note=form.cleaned_data["note"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Appointment marked no-show.")
            return _redirect_detail(appointment.id)
    return render(
        request,
        "booking/staff/appointment_detail.html",
        _staff_detail_context(request, appointment, no_show_form=form),
        status=400,
    )
