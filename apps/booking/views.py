from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.booking.forms import (
    CancelAppointmentForm,
    MarkNoShowForm,
    PublicBookingForm,
    RescheduleAppointmentForm,
    StatusNoteForm,
)
from apps.booking.countries import INTERNATIONAL_PHONE_COUNTRIES
from apps.booking.models import Appointment
from apps.booking import operations, rate_limits, services
from apps.booking.selectors import get_active_doctor, get_active_visit_type
from apps.clinic.models import Doctor, VisitType
from apps.core.models import AuditLog
from apps.core.views import _base_context
from apps.patients.profile_resolution import PatientProfileConflictError


def _language(language):
    return "en" if language == "en" else "ar"


def _booking_url(name, language, **kwargs):
    suffix = "_en" if _language(language) == "en" else ""
    return reverse(f"{name}{suffix}", kwargs=kwargs or None)


def _booking_language_switch(name, language, **query):
    language = _language(language)
    alternate_language = "en" if language == "ar" else "ar"
    url = _booking_url(name, alternate_language)
    preserved_query = {key: value for key, value in query.items() if value not in (None, "")}
    if preserved_query:
        url = f"{url}?{urlencode(preserved_query)}"
    return {
        "label": "English" if language == "ar" else "العربية",
        "url": url,
    }


def _context(request, language, **extra):
    language = _language(language)
    context = _base_context(request, "booking", language, use_public_shell=True)
    context.update(
        {
            "page_title": "احجز موعدك" if language == "ar" else "Book Your Appointment",
            "booking_home_url": _booking_url("book", language),
            "visit_type_url": _booking_url("booking_visit_type", language),
            "slots_url": _booking_url("booking_slots", language),
            "confirm_url": _booking_url("booking_confirm", language),
            "footer_primary_url": context["contact_url"],
            "footer_primary_label": context["labels"]["contact"],
            "booking_steps": [
                ("visit_type", "الخدمة" if language == "ar" else "Service"),
                ("slot", "التاريخ والوقت" if language == "ar" else "Date & Time"),
                ("confirm", "التفاصيل" if language == "ar" else "Details"),
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

    selected_visit_type = get_active_visit_type(request.GET.get("visit_type"), doctor=doctor)
    primary_visit_types = visit_types[:4]
    remaining_visit_types = visit_types[4:]
    remaining_visit_type_ids = {visit_type.id for visit_type in remaining_visit_types}

    return render(
        request,
        "booking/select_visit_type.html",
        _context(
            request,
            language,
            active_step="visit_type",
            visit_types=visit_types,
            primary_visit_types=primary_visit_types,
            remaining_visit_types=remaining_visit_types,
            visit_types_expanded=(
                selected_visit_type is not None and selected_visit_type.id in remaining_visit_type_ids
            ),
            selected_visit_type=selected_visit_type,
            language_switch=_booking_language_switch(
                "booking_visit_type",
                language,
                visit_type=selected_visit_type.id if selected_visit_type else None,
            ),
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

    requested_date = request.GET.get("date") or ""
    slots = services.generate_available_slots(
        visit_type=visit_type,
        target_date=None,
        doctor=doctor,
    )

    requested_starts_at = request.GET.get("starts_at") or ""
    selected_slot = next((slot for slot in slots if slot.value == requested_starts_at), None)
    grouped_slots = services.group_slots_by_date(slots)
    selected_date_group = None
    if selected_slot is not None:
        selected_date_group = next(
            (group for group in grouped_slots if group["date"] == selected_slot.local_date),
            None,
        )
    if selected_date_group is None and requested_date:
        selected_date_group = next(
            (group for group in grouped_slots if group["date"].isoformat() == requested_date),
            None,
        )
    if selected_date_group is None and grouped_slots:
        selected_date_group = grouped_slots[0]

    selected_date = selected_date_group["date"] if selected_date_group else None
    selected_date_slots = selected_date_group["slots"] if selected_date_group else []
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
            selected_date_group=selected_date_group,
            selected_date_slots=selected_date_slots,
            selected_slot=selected_slot,
            language_switch=_booking_language_switch(
                "booking_slots",
                language,
                visit_type=visit_type.id,
                date=selected_date.isoformat() if selected_date else None,
                starts_at=selected_slot.value if selected_slot else None,
            ),
        ),
    )


@never_cache
def confirm_booking(request, language="ar"):
    language = _language(language)
    doctor = get_active_doctor()
    authenticated_user = (
        request.user
        if request.user.is_authenticated and not request.user.is_staff
        else None
    )
    authenticated_name = ""
    if authenticated_user is not None:
        authenticated_name = authenticated_user.get_full_name().strip() or authenticated_user.username

    if request.method == "POST":
        form = PublicBookingForm(
            request.POST,
            initial={"full_name": authenticated_name},
            language=language,
            authenticated_user=authenticated_user,
        )
        ip_limit = rate_limits.check_public_booking_ip_rate_limit(request)
        if not ip_limit.allowed:
            form.is_valid()
            form.add_error(None, form.localized_error(ip_limit.message))
        elif form.is_valid():
            phone_limit = rate_limits.check_public_booking_phone_rate_limit(form.normalized_phone)
            if not phone_limit.allowed:
                form.add_error(None, form.localized_error(phone_limit.message))
            else:
                try:
                    appointment = form.save()
                except PatientProfileConflictError:
                    form.add_error(
                        None,
                        (
                            "يوجد سجل مريض يحتاج إلى الربط الآمن. استخدم ربط موعد أو تواصل مع العيادة لاستعادة الحساب."
                            if language == "ar"
                            else "An existing patient record requires secure linking. Use Link Appointment or contact the clinic for account recovery."
                        ),
                    )
                except ValidationError as exc:
                    form.add_error(None, form.localized_error(exc))
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
            "full_name": authenticated_name,
            "phone": authenticated_user.username if authenticated_user is not None else "",
        }
        form = PublicBookingForm(
            initial=initial,
            language=language,
            authenticated_user=authenticated_user,
        )
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
            starts_at=starts_at,
            phone_countries=INTERNATIONAL_PHONE_COUNTRIES,
            authenticated_booking=authenticated_user is not None,
            language_switch=_booking_language_switch(
                "booking_confirm",
                language,
                visit_type=visit_type.id if visit_type else None,
                starts_at=starts_at,
            ),
        ),
    )


@never_cache
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


STAFF_APPOINTMENT_FILTER_KEYS = (
    "status",
    "scope",
    "doctor",
    "visit_type",
    "date_from",
    "date_to",
    "q",
)

STAFF_APPOINTMENT_STATUS_LABELS = {
    "ar": {
        Appointment.Status.CONFIRMED: "مؤكد",
        Appointment.Status.ARRIVED: "وصل",
        Appointment.Status.COMPLETED: "مكتمل",
        Appointment.Status.NO_SHOW: "لم يحضر",
        Appointment.Status.CANCELLED: "ملغي",
        Appointment.Status.RESCHEDULED: "أعيدت جدولته",
    },
    "en": dict(Appointment.Status.choices),
}

STAFF_AUDIT_ACTION_LABELS_AR = {
    AuditLog.Action.CREATE: "إنشاء",
    AuditLog.Action.UPDATE: "تحديث",
    AuditLog.Action.DELETE: "حذف",
    AuditLog.Action.STATUS_CHANGE: "تغيير الحالة",
    AuditLog.Action.SETTINGS_CHANGE: "تغيير الإعدادات",
    AuditLog.Action.LOGIN: "تسجيل الدخول",
    AuditLog.Action.LOGOUT: "تسجيل الخروج",
}

STAFF_AUDIT_MESSAGE_LABELS_AR = {
    "Appointment created through public booking.": "تم إنشاء الموعد عبر الحجز العام.",
    "Appointment cancelled by staff.": "ألغى الموظف الموعد.",
    "Appointment marked arrived by staff.": "سجّل الموظف وصول المريض.",
    "Appointment marked completed by staff.": "سجّل الموظف إكمال الموعد.",
    "Appointment marked no-show by staff.": "سجّل الموظف عدم حضور المريض.",
    "Appointment rescheduled by staff.": "أعاد الموظف جدولة الموعد.",
}


def _staff_language(request):
    return _language(request.GET.get("lang"))


def _localized_status_label(status, language, *, empty_label=""):
    if not status:
        return empty_label
    return STAFF_APPOINTMENT_STATUS_LABELS[language].get(status, status)


def _url_with_staff_language(route_name, language, *, kwargs=None):
    route = reverse(route_name, kwargs=kwargs)
    return f"{route}?lang=en" if language == "en" else route


def _staff_appointment_list_url(language, *, filters=None, page=None):
    params = {}
    filters = filters or {}
    for key in STAFF_APPOINTMENT_FILTER_KEYS:
        value = filters.get(key)
        if value not in (None, ""):
            params[key] = value
    if language == "en":
        params["lang"] = "en"
    if page is not None:
        params["page"] = page
    route = reverse("staff_appointment_list")
    query = urlencode(params)
    return f"{route}?{query}" if query else route


def _staff_appointment_detail_url(appointment_id, language):
    return _url_with_staff_language(
        "staff_appointment_detail",
        language,
        kwargs={"appointment_id": appointment_id},
    )


def _staff_required(view_func):
    @wraps(view_func)
    @never_cache
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            language = _staff_language(request)
            login_route = "login_en" if language == "en" else "login"
            return redirect_to_login(
                request.get_full_path(),
                login_url=f"{reverse(login_route)}?role=doctor",
            )
        if not request.user.is_staff:
            return HttpResponseForbidden("Staff access required.")
        return view_func(request, *args, **kwargs)

    return wrapped


def _staff_context(request, *, language=None, **extra):
    language = language or _staff_language(request)
    context = _base_context(request, "booking", language)
    alternate_language = "en" if language == "ar" else "ar"
    doctor_name = (context["doctor"].get("full_name_en") or "Khaled Badran").split()
    doctor_initials = (
        f"{doctor_name[0][0]}{doctor_name[-1][0]}".upper()
        if doctor_name
        else "KB"
    )
    dashboard_home_url = _url_with_staff_language("dashboard_home", language)
    staff_appointments_url = _staff_appointment_list_url(language)
    labels = {
        "ar": {
            "overview": "نظرة عامة",
            "appointments": "المواعيد",
            "consultations": "الاستشارات",
            "patients": "المرضى",
            "public_cases": "الحالات العامة",
            "scheduling": "الجدولة",
        },
        "en": {
            "overview": "Overview",
            "appointments": "Appointments",
            "consultations": "Consultations",
            "patients": "Patients",
            "public_cases": "Public Cases",
            "scheduling": "Scheduling",
        },
    }[language]
    context.update(
        {
            "page_key": "staff_appointments",
            "page_title": (
                f"المواعيد | {context['clinic']['name_ar']}"
                if language == "ar"
                else f"Appointments | {context['clinic']['name_en']}"
            ),
            "meta_description": (
                "إدارة مواعيد العيادة وحالاتها التشغيلية."
                if language == "ar"
                else "Manage clinic appointments and their operational status."
            ),
            "canonical_url": request.build_absolute_uri(staff_appointments_url),
            "dashboard_home_url": dashboard_home_url,
            "dashboard_language_switch_url": _staff_appointment_list_url(alternate_language),
            "dashboard_language_switch_label": "English" if language == "ar" else "العربية",
            "dashboard_doctor_initials": doctor_initials,
            "dashboard_logout_url": reverse(
                "patient_portal_logout_en" if language == "en" else "patient_portal_logout"
            ),
            "dashboard_nav_items": [
                {
                    "key": "overview",
                    "label": labels["overview"],
                    "url": dashboard_home_url,
                },
                {
                    "key": "appointments",
                    "label": labels["appointments"],
                    "url": staff_appointments_url,
                },
                {
                    "key": "consultations",
                    "label": labels["consultations"],
                    "url": _url_with_staff_language("dashboard_consultation_list", language),
                },
                {
                    "key": "patients",
                    "label": labels["patients"],
                    "url": _url_with_staff_language("dashboard_patient_list", language),
                },
                {
                    "key": "public_cases",
                    "label": labels["public_cases"],
                    "url": _url_with_staff_language("dashboard_public_case_list", language),
                },
                {
                    "key": "scheduling",
                    "label": labels["scheduling"],
                    "url": _url_with_staff_language("dashboard_scheduling", language),
                },
            ],
            "active_dashboard_nav": "appointments",
            "staff_appointments_url": staff_appointments_url,
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
            | Q(contact_phone_raw__icontains=search)
            | Q(contact_phone_e164__icontains=search)
            | Q(whatsapp_phone_raw__icontains=search)
            | Q(whatsapp_phone_e164__icontains=search)
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
    language = _staff_language(request)
    queryset, filters = _filtered_staff_appointments(request)
    paginator = Paginator(queryset, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    appointments = list(page_obj.object_list)
    for appointment in appointments:
        appointment.staff_status_label = _localized_status_label(appointment.status, language)
        appointment.staff_doctor_label = (
            appointment.doctor.display_name_ar
            if language == "ar"
            else appointment.doctor.display_name_en
        )
        appointment.staff_visit_type_label = (
            (
                appointment.visit_type.name_ar
                if language == "ar"
                else appointment.visit_type.name_en
            )
            if appointment.visit_type_id
            else ("غير محدد" if language == "ar" else "Not specified")
        )
        appointment.staff_detail_url = _staff_appointment_detail_url(appointment.id, language)
        appointment.staff_patient_record_url = _url_with_staff_language(
            "dashboard_patient_record_detail",
            language,
            kwargs={"patient_id": appointment.patient_id},
        )
    alternate_language = "en" if language == "ar" else "ar"
    return render(
        request,
        "booking/staff/appointment_list.html",
        _staff_context(
            request,
            language=language,
            appointments=appointments,
            page_obj=page_obj,
            filters=filters,
            status_choices=[
                (value, _localized_status_label(value, language, empty_label=label))
                for value, label in Appointment.Status.choices
            ],
            doctors=Doctor.objects.filter(is_active=True).order_by("display_order", "full_name_en"),
            visit_types=VisitType.objects.filter(is_active=True).order_by("display_order", "name_en"),
            dashboard_language_switch_url=_staff_appointment_list_url(
                alternate_language,
                filters=filters,
                page=page_obj.number,
            ),
            staff_filter_action_url=reverse("staff_appointment_list"),
            previous_page_url=(
                _staff_appointment_list_url(
                    language,
                    filters=filters,
                    page=page_obj.previous_page_number(),
                )
                if page_obj.has_previous()
                else ""
            ),
            next_page_url=(
                _staff_appointment_list_url(
                    language,
                    filters=filters,
                    page=page_obj.next_page_number(),
                )
                if page_obj.has_next()
                else ""
            ),
        ),
    )


def _staff_detail_context(request, appointment, **extra):
    language = _staff_language(request)
    status_history = list(appointment.status_history.select_related("changed_by"))
    for item in status_history:
        item.staff_old_status_label = _localized_status_label(
            item.old_status,
            language,
            empty_label="تم الإنشاء" if language == "ar" else "Created",
        )
        item.staff_new_status_label = _localized_status_label(item.new_status, language)
        item.staff_actor_label = (
            str(item.changed_by)
            if item.changed_by_id
            else ("النظام / الحجز العام" if language == "ar" else "System / public booking")
        )
    audit_logs = list(
        AuditLog.objects.filter(
            app_label="booking",
            model_name="Appointment",
            object_id=str(appointment.id),
        ).select_related("user")
    )
    for event in audit_logs:
        event.staff_action_label = (
            STAFF_AUDIT_ACTION_LABELS_AR.get(event.action, event.get_action_display())
            if language == "ar"
            else event.get_action_display()
        )
        if event.message in STAFF_AUDIT_MESSAGE_LABELS_AR:
            event.staff_message = (
                STAFF_AUDIT_MESSAGE_LABELS_AR[event.message]
                if language == "ar"
                else event.message
            )
        else:
            event.staff_message = (
                "تم تسجيل حدث للموعد."
                if language == "ar"
                else "Appointment event recorded."
            )
        event.staff_actor_label = (
            str(event.user)
            if event.user_id
            else ("النظام / الحجز العام" if language == "ar" else "System / public booking")
        )
    appointment.staff_status_label = _localized_status_label(appointment.status, language)
    appointment.staff_doctor_label = (
        appointment.doctor.display_name_ar
        if language == "ar"
        else appointment.doctor.display_name_en
    )
    appointment.staff_visit_type_label = (
        (
            appointment.visit_type.name_ar
            if language == "ar"
            else appointment.visit_type.name_en
        )
        if appointment.visit_type_id
        else ("غير محدد" if language == "ar" else "Not specified")
    )
    alternate_language = "en" if language == "ar" else "ar"
    context = _staff_context(
        request,
        language=language,
        appointment=appointment,
        status_history=status_history,
        audit_logs=audit_logs,
        cancel_form=CancelAppointmentForm(language=language, auto_id="id_cancel_%s"),
        reschedule_form=RescheduleAppointmentForm(
            appointment=appointment,
            language=language,
            auto_id="id_reschedule_%s",
        ),
        no_show_form=MarkNoShowForm(language=language, auto_id="id_no_show_%s"),
        arrived_form=StatusNoteForm(language=language, auto_id="id_arrived_%s"),
        complete_form=StatusNoteForm(language=language, auto_id="id_complete_%s"),
        page_title=(
            f"الموعد {appointment.confirmation_reference}"
            if language == "ar"
            else f"Appointment {appointment.confirmation_reference}"
        ),
        canonical_url=request.build_absolute_uri(
            _staff_appointment_detail_url(appointment.id, language)
        ),
        dashboard_language_switch_url=_staff_appointment_detail_url(
            appointment.id,
            alternate_language,
        ),
        patient_record_url=_url_with_staff_language(
            "dashboard_patient_record_detail",
            language,
            kwargs={"patient_id": appointment.patient_id},
        ),
        operation_urls={
            "arrived": _url_with_staff_language(
                "staff_appointment_arrived",
                language,
                kwargs={"appointment_id": appointment.id},
            ),
            "complete": _url_with_staff_language(
                "staff_appointment_complete",
                language,
                kwargs={"appointment_id": appointment.id},
            ),
            "reschedule": _url_with_staff_language(
                "staff_appointment_reschedule",
                language,
                kwargs={"appointment_id": appointment.id},
            ),
            "cancel": _url_with_staff_language(
                "staff_appointment_cancel",
                language,
                kwargs={"appointment_id": appointment.id},
            ),
            "no_show": _url_with_staff_language(
                "staff_appointment_no_show",
                language,
                kwargs={"appointment_id": appointment.id},
            ),
        },
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


def _redirect_detail(appointment_id, language):
    return redirect(_staff_appointment_detail_url(appointment_id, language))


def _add_staff_operation_error(form, error, language):
    if language == "ar":
        form.add_error(None, "تعذر تنفيذ الإجراء على حالة الموعد الحالية.")
    else:
        form.add_error(None, error)


@_staff_required
def staff_appointment_cancel(request, appointment_id):
    not_allowed = _require_post(request)
    if not_allowed:
        return not_allowed
    language = _staff_language(request)
    appointment = get_object_or_404(operations.staff_appointment_queryset(), id=appointment_id)
    form = CancelAppointmentForm(
        request.POST,
        language=language,
        auto_id="id_cancel_%s",
    )
    if form.is_valid():
        try:
            appointment = operations.cancel_appointment(
                appointment_id,
                actor=request.user,
                note=form.cleaned_data["note"],
            )
        except ValidationError as exc:
            _add_staff_operation_error(form, exc, language)
        else:
            messages.success(
                request,
                "تم إلغاء الموعد." if language == "ar" else "Appointment cancelled.",
            )
            return _redirect_detail(appointment.id, language)
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
    language = _staff_language(request)
    appointment = get_object_or_404(operations.staff_appointment_queryset(), id=appointment_id)
    form = RescheduleAppointmentForm(
        request.POST,
        appointment=appointment,
        language=language,
        auto_id="id_reschedule_%s",
    )
    if form.is_valid():
        try:
            appointment = operations.reschedule_appointment(
                appointment_id,
                starts_at=form.cleaned_data["starts_at"],
                actor=request.user,
                note=form.cleaned_data.get("note", ""),
            )
        except ValidationError as exc:
            _add_staff_operation_error(form, exc, language)
        else:
            messages.success(
                request,
                "تمت إعادة جدولة الموعد."
                if language == "ar"
                else "Appointment rescheduled.",
            )
            return _redirect_detail(appointment.id, language)
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
    language = _staff_language(request)
    appointment = get_object_or_404(operations.staff_appointment_queryset(), id=appointment_id)
    form = StatusNoteForm(
        request.POST,
        language=language,
        auto_id="id_arrived_%s",
    )
    if form.is_valid():
        try:
            appointment = operations.mark_arrived(
                appointment_id,
                actor=request.user,
                note=form.cleaned_data.get("note", ""),
            )
        except ValidationError as exc:
            _add_staff_operation_error(form, exc, language)
        else:
            messages.success(
                request,
                "تم تسجيل وصول المريض."
                if language == "ar"
                else "Appointment marked arrived.",
            )
            return _redirect_detail(appointment.id, language)
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
    language = _staff_language(request)
    appointment = get_object_or_404(operations.staff_appointment_queryset(), id=appointment_id)
    form = StatusNoteForm(
        request.POST,
        language=language,
        auto_id="id_complete_%s",
    )
    if form.is_valid():
        try:
            appointment = operations.mark_completed(
                appointment_id,
                actor=request.user,
                note=form.cleaned_data.get("note", ""),
            )
        except ValidationError as exc:
            _add_staff_operation_error(form, exc, language)
        else:
            messages.success(
                request,
                "تم تسجيل إكمال الموعد."
                if language == "ar"
                else "Appointment completed.",
            )
            return _redirect_detail(appointment.id, language)
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
    language = _staff_language(request)
    appointment = get_object_or_404(operations.staff_appointment_queryset(), id=appointment_id)
    form = MarkNoShowForm(
        request.POST,
        language=language,
        auto_id="id_no_show_%s",
    )
    if form.is_valid():
        try:
            appointment = operations.mark_no_show(
                appointment_id,
                actor=request.user,
                note=form.cleaned_data["note"],
            )
        except ValidationError as exc:
            _add_staff_operation_error(form, exc, language)
        else:
            messages.success(
                request,
                "تم تسجيل عدم حضور المريض."
                if language == "ar"
                else "Appointment marked no-show.",
            )
            return _redirect_detail(appointment.id, language)
    return render(
        request,
        "booking/staff/appointment_detail.html",
        _staff_detail_context(request, appointment, no_show_form=form),
        status=400,
    )
