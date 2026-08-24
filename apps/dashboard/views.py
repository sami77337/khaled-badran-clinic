import calendar
import re
from datetime import date, datetime, time, timedelta
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.booking import services as booking_services
from apps.booking.models import Appointment
from apps.booking.selectors import get_active_doctor, get_active_visit_types
from apps.clinic.models import ClosedDay, DoctorSchedule
from apps.core.views import _base_context
from apps.patients.models import Patient
from apps.records.models import ClinicalNote, RecordMedia, VisitRecord

from .forms import (
    StaffClinicalNoteForm,
    StaffRecordMediaCreateForm,
    StaffRecordMediaUpdateForm,
    StaffVisitRecordForm,
)


VISIBILITY_LABELS = {
    RecordMedia.Visibility.PRIVATE_ONLY: "خاص فقط",
    RecordMedia.Visibility.VISIBLE_TO_PATIENT: "ظاهر للمريض",
    RecordMedia.Visibility.APPROVED_PUBLIC_CASE: "حالة عامة بموافقة",
}

DASHBOARD_EXCLUDED_TODAY_STATUSES = (
    Appointment.Status.CANCELLED,
    Appointment.Status.RESCHEDULED,
)
DASHBOARD_UPCOMING_STATUSES = (
    Appointment.Status.CONFIRMED,
    Appointment.Status.ARRIVED,
)
DASHBOARD_STATUS_LABELS = {
    "ar": {
        Appointment.Status.CONFIRMED: "مؤكد",
        Appointment.Status.ARRIVED: "وصل",
        Appointment.Status.COMPLETED: "مكتمل",
        Appointment.Status.NO_SHOW: "لم يحضر",
        Appointment.Status.CANCELLED: "ملغي",
        Appointment.Status.RESCHEDULED: "أعيدت جدولته",
    },
    "en": {
        Appointment.Status.CONFIRMED: "Confirmed",
        Appointment.Status.ARRIVED: "Arrived",
        Appointment.Status.COMPLETED: "Completed",
        Appointment.Status.NO_SHOW: "No-show",
        Appointment.Status.CANCELLED: "Cancelled",
        Appointment.Status.RESCHEDULED: "Rescheduled",
    },
}

SCHEDULING_VIEW_NAMES = ("day", "week", "month")
SCHEDULING_WEEKDAY_LABELS = {
    "ar": (
        ("الاثنين", "اث"),
        ("الثلاثاء", "ثل"),
        ("الأربعاء", "أر"),
        ("الخميس", "خم"),
        ("الجمعة", "جم"),
        ("السبت", "سب"),
        ("الأحد", "أح"),
    ),
    "en": (
        ("Monday", "Mon"),
        ("Tuesday", "Tue"),
        ("Wednesday", "Wed"),
        ("Thursday", "Thu"),
        ("Friday", "Fri"),
        ("Saturday", "Sat"),
        ("Sunday", "Sun"),
    ),
}
SCHEDULING_MONTH_LABELS = {
    "ar": (
        "يناير",
        "فبراير",
        "مارس",
        "أبريل",
        "مايو",
        "يونيو",
        "يوليو",
        "أغسطس",
        "سبتمبر",
        "أكتوبر",
        "نوفمبر",
        "ديسمبر",
    ),
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
}


def _dashboard_language(request):
    return "en" if request.GET.get("lang") == "en" else "ar"


def _dashboard_home_url(language):
    url = reverse("dashboard_home")
    return f"{url}?lang=en" if language == "en" else url


def _scheduling_url(language, *, view=None, selected_date=None, visit_type=None):
    params = {}
    if language == "en":
        params["lang"] = "en"
    if view:
        params["view"] = view
    if selected_date:
        params["date"] = selected_date.isoformat()
    if visit_type:
        params["visit_type"] = visit_type.pk
    query = urlencode(params)
    route = reverse("dashboard_scheduling")
    return f"{route}?{query}" if query else route


def _staff_required(view_func):
    @wraps(view_func)
    @never_cache
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            language = _dashboard_language(request)
            login_route = "login_en" if language == "en" else "login"
            return redirect_to_login(
                request.get_full_path(),
                login_url=f"{reverse(login_route)}?role=doctor",
            )
        if not request.user.is_staff:
            return HttpResponseForbidden("Staff access required.")
        return view_func(request, *args, **kwargs)

    return wrapped


def _dashboard_home_context(request, *, language, metrics, schedule_items):
    context = _base_context(request, "booking", language)
    alternate_language = "en" if language == "ar" else "ar"
    doctor_name = (context["doctor"].get(f"full_name_{language}") or "").strip()
    doctor_first_name = (
        doctor_name.split()[0]
        if doctor_name
        else ("خالد" if language == "ar" else "Khaled")
    )
    english_name_parts = (context["doctor"].get("full_name_en") or "Khaled Badran").split()
    doctor_initials = (
        f"{english_name_parts[0][0]}{english_name_parts[-1][0]}".upper()
        if english_name_parts
        else "KB"
    )
    dashboard_url = _dashboard_home_url(language)
    labels = {
        "ar": {
            "overview": "نظرة عامة",
            "appointments": "المواعيد",
            "patients": "المرضى",
            "scheduling": "الجدولة",
        },
        "en": {
            "overview": "Overview",
            "appointments": "Appointments",
            "patients": "Patients",
            "scheduling": "Scheduling",
        },
    }[language]
    context.update(
        {
            "page_key": "dashboard_home",
            "page_title": (
                f"نظرة عامة | {context['clinic']['name_ar']}"
                if language == "ar"
                else f"Dashboard Overview | {context['clinic']['name_en']}"
            ),
            "meta_description": (
                "نظرة تشغيلية آمنة ومختصرة لفريق العيادة."
                if language == "ar"
                else "A secure operational overview for clinic staff."
            ),
            "canonical_url": request.build_absolute_uri(dashboard_url),
            "dashboard_home_url": dashboard_url,
            "dashboard_language_switch_url": _dashboard_home_url(alternate_language),
            "dashboard_language_switch_label": "English" if language == "ar" else "العربية",
            "dashboard_doctor_first_name": doctor_first_name,
            "dashboard_doctor_initials": doctor_initials,
            "dashboard_logout_url": reverse(
                "patient_portal_logout_en" if language == "en" else "patient_portal_logout"
            ),
            "dashboard_nav_items": [
                {
                    "key": "overview",
                    "label": labels["overview"],
                    "url": dashboard_url,
                },
                {
                    "key": "appointments",
                    "label": labels["appointments"],
                    "url": reverse("staff_appointment_list"),
                },
                {
                    "key": "patients",
                    "label": labels["patients"],
                    "url": reverse("dashboard_patient_list"),
                },
                {
                    "key": "scheduling",
                    "label": labels["scheduling"],
                    "url": _scheduling_url(language),
                },
            ],
            "active_dashboard_nav": "overview",
            "staff_appointments_url": reverse("staff_appointment_list"),
            "dashboard_patients_url": reverse("dashboard_patient_list"),
            "dashboard_metrics": metrics,
            "schedule_items": schedule_items,
        }
    )
    return context


@_staff_required
@require_GET
def dashboard_home(request):
    language = _dashboard_language(request)
    now = timezone.now()
    today = timezone.localdate(now)
    today_appointments = Appointment.objects.filter(starts_at__date=today)
    today_metrics = today_appointments.aggregate(
        appointments=Count(
            "pk",
            filter=~Q(status__in=DASHBOARD_EXCLUDED_TODAY_STATUSES),
        ),
        completed=Count("pk", filter=Q(status=Appointment.Status.COMPLETED)),
        no_show=Count("pk", filter=Q(status=Appointment.Status.NO_SHOW)),
    )
    upcoming = Appointment.objects.filter(
        starts_at__gt=now,
        starts_at__lte=now + timedelta(days=7),
        status__in=DASHBOARD_UPCOMING_STATUSES,
    ).count()
    total_patients = Patient.objects.count()

    schedule = (
        today_appointments.exclude(status__in=DASHBOARD_EXCLUDED_TODAY_STATUSES)
        .select_related("patient", "visit_type", "doctor")
        .order_by("starts_at", "id")[:6]
    )
    schedule_items = [
        {
            "appointment": appointment,
            "visit_type_label": (
                appointment.visit_type.name_ar
                if language == "ar" and appointment.visit_type
                else appointment.visit_type.name_en
                if appointment.visit_type
                else "—"
            ),
            "status_label": DASHBOARD_STATUS_LABELS[language].get(
                appointment.status,
                appointment.get_status_display(),
            ),
            "status_class": appointment.status,
        }
        for appointment in schedule
    ]

    metrics = {
        "today": today_metrics["appointments"],
        "upcoming": upcoming,
        "patients": total_patients,
        "completed": today_metrics["completed"],
        "no_show": today_metrics["no_show"],
    }
    metric_cards = [
        {
            "key": "today",
            "label": "مواعيد اليوم" if language == "ar" else "Today's appointments",
            "value": metrics["today"],
            "sublabel": "",
        },
        {
            "key": "upcoming",
            "label": "المواعيد القادمة" if language == "ar" else "Upcoming appointments",
            "value": metrics["upcoming"],
            "sublabel": "الأيام السبعة القادمة" if language == "ar" else "Next 7 days",
        },
        {
            "key": "patients",
            "label": "إجمالي المرضى" if language == "ar" else "Total patients",
            "value": metrics["patients"],
            "sublabel": "",
        },
        {
            "key": "completed",
            "label": "المكتملة اليوم" if language == "ar" else "Completed today",
            "value": metrics["completed"],
            "sublabel": "",
        },
        {
            "key": "no_show",
            "label": "حالات عدم الحضور اليوم" if language == "ar" else "No-shows today",
            "value": metrics["no_show"],
            "sublabel": "",
        },
    ]

    context = _dashboard_home_context(
        request,
        language=language,
        metrics=metrics,
        schedule_items=schedule_items,
    )
    context["metric_cards"] = metric_cards
    return render(request, "dashboard/home.html", context)


def _parse_scheduling_view(raw_view):
    return raw_view if raw_view in SCHEDULING_VIEW_NAMES else "week"


def _parse_scheduling_date(raw_date, today):
    if not raw_date or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
        return today
    try:
        parsed_date = date.fromisoformat(raw_date)
    except ValueError:
        return today
    if parsed_date.year in {date.min.year, date.max.year}:
        return today
    return parsed_date


def _shift_month(selected_date, offset):
    month_index = selected_date.year * 12 + selected_date.month - 1 + offset
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(selected_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _scheduling_dates(selected_date, view):
    if view == "day":
        return [selected_date]
    if view == "week":
        week_start = selected_date - timedelta(days=selected_date.weekday())
        return [week_start + timedelta(days=offset) for offset in range(7)]
    month_weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(
        selected_date.year,
        selected_date.month,
    )
    return [day for week in month_weeks for day in week]


def _local_day_bounds(day):
    current_timezone = timezone.get_current_timezone()
    starts_at = timezone.make_aware(datetime.combine(day, time.min), current_timezone)
    ends_at = timezone.make_aware(
        datetime.combine(day + timedelta(days=1), time.min),
        current_timezone,
    )
    return starts_at, ends_at


def _localized_visit_type_name(visit_type, language):
    if visit_type is None:
        return "—"
    primary = visit_type.name_ar if language == "ar" else visit_type.name_en
    fallback = visit_type.name_en if language == "ar" else visit_type.name_ar
    return primary or fallback or "—"


def _scheduling_appointment_item(appointment, language):
    local_start = timezone.localtime(appointment.starts_at)
    local_end = timezone.localtime(appointment.ends_at)
    duration_minutes = max(
        1,
        int((appointment.ends_at - appointment.starts_at).total_seconds() // 60),
    )
    return {
        "start_time": local_start.strftime("%H:%M"),
        "end_time": local_end.strftime("%H:%M"),
        "duration_minutes": duration_minutes,
        "patient_name": appointment.patient.full_name,
        "visit_type_name": _localized_visit_type_name(appointment.visit_type, language),
        "status_label": DASHBOARD_STATUS_LABELS[language].get(
            appointment.status,
            appointment.get_status_display(),
        ),
        "status_class": appointment.status,
        "detail_url": reverse(
            "staff_appointment_detail",
            kwargs={"appointment_id": appointment.pk},
        ),
    }


def _scheduling_day_item(
    day,
    *,
    language,
    selected_date,
    today,
    selected_month,
    schedules_by_weekday,
    closures_by_date,
    appointments_by_date,
):
    weekday_full, weekday_short = SCHEDULING_WEEKDAY_LABELS[language][day.weekday()]
    periods = [
        {
            "start": schedule.start_time.strftime("%H:%M"),
            "end": schedule.end_time.strftime("%H:%M"),
        }
        for schedule in schedules_by_weekday.get(day.weekday(), [])
    ]
    closures = closures_by_date.get(day, [])
    appointment_items = appointments_by_date.get(day, [])
    return {
        "date": day,
        "iso_date": day.isoformat(),
        "day_number": day.day,
        "weekday_full": weekday_full,
        "weekday_short": weekday_short,
        "month_name": SCHEDULING_MONTH_LABELS[language][day.month - 1],
        "is_today": day == today,
        "is_selected": day == selected_date,
        "is_current_month": (day.year, day.month) == selected_month,
        "working_periods": periods,
        "closures": closures,
        "is_closed": bool(closures),
        "appointments": appointment_items,
        "appointment_count": len(appointment_items),
        "available_slots": [],
    }


def _scheduling_navigation_date(selected_date, view, direction):
    if view == "day":
        return selected_date + timedelta(days=direction)
    if view == "week":
        return selected_date + timedelta(days=7 * direction)
    return _shift_month(selected_date, direction)


def _scheduling_period_label(language, view, selected_day, visible_dates):
    selected_date = selected_day["date"]
    if view == "day":
        if language == "ar":
            return (
                f"{selected_day['weekday_full']}، {selected_date.day} "
                f"{selected_day['month_name']} {selected_date.year}"
            )
        return (
            f"{selected_day['weekday_full']}, {selected_day['month_name']} "
            f"{selected_date.day}, {selected_date.year}"
        )
    if view == "month":
        return f"{selected_day['month_name']} {selected_date.year}"

    week_start = visible_dates[0]
    week_end = visible_dates[-1]
    start_month = SCHEDULING_MONTH_LABELS[language][week_start.month - 1]
    end_month = SCHEDULING_MONTH_LABELS[language][week_end.month - 1]
    if week_start.year == week_end.year and week_start.month == week_end.month:
        return f"{week_start.day}–{week_end.day} {end_month} {week_end.year}"
    if week_start.year == week_end.year:
        return (
            f"{week_start.day} {start_month} – "
            f"{week_end.day} {end_month} {week_end.year}"
        )
    return (
        f"{week_start.day} {start_month} {week_start.year} – "
        f"{week_end.day} {end_month} {week_end.year}"
    )


def _scheduling_context(
    request,
    *,
    language,
    view,
    selected_date,
    active_doctor,
    visit_types,
    selected_visit_type,
):
    today = timezone.localdate()
    if selected_visit_type and selected_visit_type not in visit_types:
        selected_visit_type = None

    visible_dates = _scheduling_dates(selected_date, view)
    visible_start, _ = _local_day_bounds(visible_dates[0])
    _, visible_end = _local_day_bounds(visible_dates[-1])

    schedules_by_weekday = {}
    closures_by_date = {}
    appointments_by_date = {}
    if active_doctor:
        schedules = DoctorSchedule.objects.filter(
            doctor=active_doctor,
            is_active=True,
        ).order_by("weekday", "start_time", "id")
        for schedule in schedules:
            schedules_by_weekday.setdefault(schedule.weekday, []).append(schedule)

        closures = (
            ClosedDay.objects.filter(
                is_active=True,
                date__range=(visible_dates[0], visible_dates[-1]),
            )
            .filter(Q(doctor=active_doctor) | Q(doctor__isnull=True))
            .order_by("date", "id")
        )
        for closure in closures:
            reason = closure.reason_ar if language == "ar" else closure.reason_en
            if not reason:
                reason = closure.reason_en if language == "ar" else closure.reason_ar
            closures_by_date.setdefault(closure.date, []).append(reason)

        appointments = (
            Appointment.objects.filter(
                doctor=active_doctor,
                starts_at__lt=visible_end,
                ends_at__gt=visible_start,
            )
            .select_related("patient", "visit_type", "doctor")
            .order_by("starts_at", "id")
        )
        for appointment in appointments:
            local_date = timezone.localtime(appointment.starts_at).date()
            appointments_by_date.setdefault(local_date, []).append(
                _scheduling_appointment_item(appointment, language)
            )

    day_items = [
        _scheduling_day_item(
            day,
            language=language,
            selected_date=selected_date,
            today=today,
            selected_month=(selected_date.year, selected_date.month),
            schedules_by_weekday=schedules_by_weekday,
            closures_by_date=closures_by_date,
            appointments_by_date=appointments_by_date,
        )
        for day in visible_dates
    ]
    day_items_by_date = {item["date"]: item for item in day_items}
    selected_day = day_items_by_date.get(selected_date)
    if selected_day is None:
        selected_day = _scheduling_day_item(
            selected_date,
            language=language,
            selected_date=selected_date,
            today=today,
            selected_month=(selected_date.year, selected_date.month),
            schedules_by_weekday=schedules_by_weekday,
            closures_by_date=closures_by_date,
            appointments_by_date=appointments_by_date,
        )

    if active_doctor and selected_visit_type:
        settings = booking_services.get_booking_settings()
        now = timezone.localtime(timezone.now())
        availability_days = day_items if view == "week" else [selected_day]
        for day_item in availability_days:
            slots = booking_services.generate_available_slots(
                visit_type=selected_visit_type,
                target_date=day_item["date"],
                now=now,
                settings=settings,
                doctor=active_doctor,
            )
            day_item["available_slots"] = [
                {
                    "start": timezone.localtime(slot.starts_at).strftime("%H:%M"),
                    "end": timezone.localtime(slot.ends_at).strftime("%H:%M"),
                }
                for slot in slots
            ]

    alternate_language = "en" if language == "ar" else "ar"
    shell_context = _dashboard_home_context(
        request,
        language=language,
        metrics={},
        schedule_items=[],
    )
    previous_date = _scheduling_navigation_date(selected_date, view, -1)
    next_date = _scheduling_navigation_date(selected_date, view, 1)
    view_labels = {
        "ar": {"day": "اليوم", "week": "الأسبوع", "month": "الشهر"},
        "en": {"day": "Day", "week": "Week", "month": "Month"},
    }[language]
    for day_item in day_items:
        day_item["day_view_url"] = _scheduling_url(
            language,
            view="day",
            selected_date=day_item["date"],
            visit_type=selected_visit_type,
        )

    appointments_query = urlencode(
        {
            "scope": "all",
            "date_from": selected_date.isoformat(),
            "date_to": selected_date.isoformat(),
            **({"visit_type": selected_visit_type.pk} if selected_visit_type else {}),
        }
    )
    shell_context.update(
        {
            "page_key": "dashboard_scheduling",
            "page_title": (
                f"مركز الجدولة | {shell_context['clinic']['name_ar']}"
                if language == "ar"
                else f"Scheduling Center | {shell_context['clinic']['name_en']}"
            ),
            "meta_description": (
                "عرض تشغيلي للجدول والمواعيد والتوافر الفعلي للعيادة."
                if language == "ar"
                else "An operational view of clinic hours, appointments, and real availability."
            ),
            "canonical_url": request.build_absolute_uri(
                _scheduling_url(
                    language,
                    view=view,
                    selected_date=selected_date,
                    visit_type=selected_visit_type,
                )
            ),
            "active_dashboard_nav": "scheduling",
            "dashboard_language_switch_url": _scheduling_url(
                alternate_language,
                view=view,
                selected_date=selected_date,
                visit_type=selected_visit_type,
            ),
            "scheduling_view": view,
            "scheduling_selected_date": selected_date,
            "scheduling_today": today,
            "scheduling_timezone": timezone.get_current_timezone_name(),
            "scheduling_doctor": active_doctor,
            "scheduling_visit_types": visit_types,
            "scheduling_selected_visit_type": selected_visit_type,
            "scheduling_days": day_items,
            "scheduling_month_weeks": [
                day_items[index : index + 7]
                for index in range(0, len(day_items), 7)
            ],
            "scheduling_selected_day": selected_day,
            "scheduling_previous_url": _scheduling_url(
                language,
                view=view,
                selected_date=previous_date,
                visit_type=selected_visit_type,
            ),
            "scheduling_today_url": _scheduling_url(
                language,
                view=view,
                selected_date=today,
                visit_type=selected_visit_type,
            ),
            "scheduling_next_url": _scheduling_url(
                language,
                view=view,
                selected_date=next_date,
                visit_type=selected_visit_type,
            ),
            "scheduling_view_tabs": [
                {
                    "key": view_name,
                    "label": view_labels[view_name],
                    "url": _scheduling_url(
                        language,
                        view=view_name,
                        selected_date=selected_date,
                        visit_type=selected_visit_type,
                    ),
                }
                for view_name in SCHEDULING_VIEW_NAMES
            ],
            "scheduling_period_label": _scheduling_period_label(
                language,
                view,
                selected_day,
                visible_dates,
            ),
            "scheduling_appointments_url": (
                f"{reverse('staff_appointment_list')}?{appointments_query}"
            ),
        }
    )
    return shell_context


@_staff_required
@require_GET
def dashboard_scheduling(request):
    language = _dashboard_language(request)
    view = _parse_scheduling_view(request.GET.get("view"))
    selected_date = _parse_scheduling_date(
        request.GET.get("date"),
        timezone.localdate(),
    )
    active_doctor = get_active_doctor()
    visit_types = list(get_active_visit_types(doctor=active_doctor)) if active_doctor else []
    selected_visit_type = None
    raw_visit_type = request.GET.get("visit_type")
    if active_doctor and raw_visit_type:
        try:
            visit_type_id = int(raw_visit_type)
        except (TypeError, ValueError):
            visit_type_id = None
        if visit_type_id is not None:
            selected_visit_type = next(
                (visit_type for visit_type in visit_types if visit_type.pk == visit_type_id),
                None,
            )

    context = _scheduling_context(
        request,
        language=language,
        view=view,
        selected_date=selected_date,
        active_doctor=active_doctor,
        visit_types=visit_types,
        selected_visit_type=selected_visit_type,
    )
    return render(request, "dashboard/scheduling.html", context)


def _method_allowed(request, methods):
    if request.method not in methods:
        return HttpResponseNotAllowed(methods)
    return None


def _dashboard_context(request, **extra):
    context = _base_context(request, "booking", "ar")
    context.update(
        {
            "page_key": "dashboard_records",
            "page_title": f"لوحة سجلات المرضى | {context['clinic']['name_ar']}",
            "meta_description": "صفحات داخلية مخصصة لفريق العيادة لإدارة سجلات المرضى والوسائط الخاصة.",
            "canonical_url": request.build_absolute_uri(request.path),
            "dashboard_patients_url": reverse("dashboard_patient_list"),
            "staff_appointments_url": reverse("staff_appointment_list"),
            "dashboard_nav_items": [
                {
                    "label": "المرضى والسجلات",
                    "url": reverse("dashboard_patient_list"),
                },
                {
                    "label": "المواعيد",
                    "url": reverse("staff_appointment_list"),
                },
            ],
        }
    )
    context.update(extra)
    return context


def _patient_record_detail_url(patient):
    return reverse("dashboard_patient_record_detail", kwargs={"patient_id": patient.id})


def _record_visibility_label(is_visible_to_patient):
    return "ظاهر للمريض" if is_visible_to_patient else "خاص فقط"


def _media_status_labels(media):
    labels = [
        {
            "label": VISIBILITY_LABELS.get(media.visibility, media.get_visibility_display()),
            "class": f"status-{media.visibility}",
        }
    ]
    if media.consent_confirmed:
        labels.append({"label": "موافقة مؤكدة", "class": "status-consent-confirmed"})
    if not media.is_active:
        labels.append({"label": "غير نشط", "class": "status-inactive"})
    return labels


def _media_items(media_queryset):
    items = []
    for media in media_queryset:
        staff_download_url = ""
        if media.is_active and media.file:
            staff_download_url = reverse(
                "record_private_media_download",
                kwargs={"public_id": media.public_id},
            )
        public_case_url = ""
        if media.is_public_case_approved:
            public_case_url = reverse("public_case_media", kwargs={"public_id": media.public_id})
        items.append(
            {
                "media": media,
                "status_labels": _media_status_labels(media),
                "staff_download_url": staff_download_url,
                "public_case_url": public_case_url,
                "edit_url": reverse(
                    "dashboard_media_update",
                    kwargs={
                        "patient_id": media.patient_id,
                        "public_id": media.public_id,
                    },
                ),
            }
        )
    return items


@_staff_required
@require_GET
def dashboard_patient_list(request):
    patients = (
        Patient.objects.annotate(
            visit_count=Count("visit_records", distinct=True),
            note_count=Count("clinical_notes", distinct=True),
            media_count=Count("record_media", distinct=True),
        )
        .order_by("full_name", "id")
    )
    return render(
        request,
        "dashboard/patient_list.html",
        _dashboard_context(request, patients=patients),
    )


@_staff_required
@require_GET
def dashboard_patient_record_detail(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    visits = (
        VisitRecord.objects.filter(patient=patient)
        .select_related("appointment", "appointment__doctor", "appointment__visit_type")
        .order_by("-visit_date", "-created_at")
    )
    notes = (
        ClinicalNote.objects.filter(patient=patient)
        .select_related("visit", "created_by")
        .order_by("-created_at", "-id")
    )
    media = (
        RecordMedia.objects.filter(patient=patient)
        .select_related("visit", "uploaded_by")
        .order_by("-uploaded_at", "-id")
    )
    return render(
        request,
        "dashboard/patient_record_detail.html",
        _dashboard_context(
            request,
            patient=patient,
            visit_items=[
                {
                    "visit": visit,
                    "visibility_label": _record_visibility_label(visit.is_visible_to_patient),
                }
                for visit in visits
            ],
            note_items=[
                {
                    "note": note,
                    "visibility_label": _record_visibility_label(note.is_visible_to_patient),
                }
                for note in notes
            ],
            media_items=_media_items(media),
            visit_create_url=reverse("dashboard_visit_create", kwargs={"patient_id": patient.id}),
            note_create_url=reverse("dashboard_note_create", kwargs={"patient_id": patient.id}),
            media_create_url=reverse("dashboard_media_create", kwargs={"patient_id": patient.id}),
        ),
    )


@_staff_required
def dashboard_visit_create(request, patient_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    patient = get_object_or_404(Patient, id=patient_id)
    if request.method == "POST":
        form = StaffVisitRecordForm(request.POST, patient=patient)
        if form.is_valid():
            visit = form.save(commit=False)
            visit.patient = patient
            visit.save()
            messages.success(request, "تم إنشاء الزيارة.")
            return redirect(_patient_record_detail_url(patient))
        status = 400
    else:
        form = StaffVisitRecordForm(patient=patient)
        status = 200

    return render(
        request,
        "dashboard/visit_form.html",
        _dashboard_context(
            request,
            patient=patient,
            form=form,
            form_title="إضافة زيارة",
            cancel_url=_patient_record_detail_url(patient),
        ),
        status=status,
    )


@_staff_required
def dashboard_note_create(request, patient_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    patient = get_object_or_404(Patient, id=patient_id)
    if request.method == "POST":
        form = StaffClinicalNoteForm(request.POST, patient=patient, created_by=request.user)
        if form.is_valid():
            note = form.save(commit=False)
            note.patient = patient
            note.created_by = request.user
            note.save()
            messages.success(request, "تم إنشاء الملاحظة.")
            return redirect(_patient_record_detail_url(patient))
        status = 400
    else:
        form = StaffClinicalNoteForm(patient=patient, created_by=request.user)
        status = 200

    return render(
        request,
        "dashboard/note_form.html",
        _dashboard_context(
            request,
            patient=patient,
            form=form,
            form_title="إضافة ملاحظة سريرية",
            cancel_url=_patient_record_detail_url(patient),
        ),
        status=status,
    )


@_staff_required
def dashboard_media_create(request, patient_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    patient = get_object_or_404(Patient, id=patient_id)
    if request.method == "POST":
        form = StaffRecordMediaCreateForm(
            request.POST,
            request.FILES,
            patient=patient,
            uploaded_by=request.user,
        )
        if form.is_valid():
            media = form.save(commit=False)
            media.patient = patient
            media.uploaded_by = request.user
            media.save()
            messages.success(request, "تم رفع الملف الخاص.")
            return redirect(_patient_record_detail_url(patient))
        status = 400
    else:
        form = StaffRecordMediaCreateForm(patient=patient, uploaded_by=request.user)
        status = 200

    return render(
        request,
        "dashboard/media_form.html",
        _dashboard_context(
            request,
            patient=patient,
            form=form,
            form_title="رفع صورة أو فيديو خاص",
            cancel_url=_patient_record_detail_url(patient),
            is_multipart=True,
        ),
        status=status,
    )


@_staff_required
def dashboard_media_update(request, patient_id, public_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    patient = get_object_or_404(Patient, id=patient_id)
    media = get_object_or_404(
        RecordMedia.objects.select_related("patient", "visit", "uploaded_by"),
        patient=patient,
        public_id=public_id,
    )
    if request.method == "POST":
        form = StaffRecordMediaUpdateForm(request.POST, instance=media)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث حالة الملف.")
            return redirect(_patient_record_detail_url(patient))
        status = 400
    else:
        form = StaffRecordMediaUpdateForm(instance=media)
        status = 200

    return render(
        request,
        "dashboard/media_form.html",
        _dashboard_context(
            request,
            patient=patient,
            media=media,
            form=form,
            form_title="تعديل حالة ملف",
            cancel_url=_patient_record_detail_url(patient),
            is_multipart=False,
        ),
        status=status,
    )
