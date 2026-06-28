from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.booking.forms import PublicBookingForm
from apps.booking.models import Appointment
from apps.booking import services
from apps.booking.selectors import get_active_doctor, get_active_visit_type
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
        if form.is_valid():
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
