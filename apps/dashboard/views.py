import calendar
import re
from datetime import date, datetime, time, timedelta
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.booking import operations as booking_operations
from apps.booking import services as booking_services
from apps.booking.models import Appointment
from apps.booking.selectors import get_active_doctor, get_active_visit_types
from apps.clinic.models import (
    ClosedDay,
    Doctor,
    DoctorSchedule,
    DoctorScheduleOverride,
    VisitType,
)
from apps.core.models import AuditLog, SystemSetting
from apps.core.views import _base_context
from apps.patients.models import Patient
from apps.records.models import ClinicalNote, RecordMedia, VisitRecord

from .forms import (
    BookingRulesForm,
    ClosureCreateForm,
    SpecialHoursDateForm,
    SpecialHoursForm,
    StaffClinicalNoteForm,
    StaffRecordMediaCreateForm,
    StaffRecordMediaUpdateForm,
    StaffVisitRecordForm,
    VisitTypeCreateForm,
    VisitTypeDurationForm,
    WeeklyPeriodCreateForm,
    WeeklyPeriodUpdateForm,
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
SCHEDULING_SECTION_NAMES = ("calendar", "weekly", "services", "rules", "closures")
SCHEDULING_WEEKDAY_DISPLAY_ORDER = (
    DoctorSchedule.Weekday.SUNDAY,
    DoctorSchedule.Weekday.MONDAY,
    DoctorSchedule.Weekday.TUESDAY,
    DoctorSchedule.Weekday.WEDNESDAY,
    DoctorSchedule.Weekday.THURSDAY,
    DoctorSchedule.Weekday.FRIDAY,
    DoctorSchedule.Weekday.SATURDAY,
)
SCHEDULING_WEEKDAY_ANCHORS = {
    DoctorSchedule.Weekday.MONDAY: "weekday-monday",
    DoctorSchedule.Weekday.TUESDAY: "weekday-tuesday",
    DoctorSchedule.Weekday.WEDNESDAY: "weekday-wednesday",
    DoctorSchedule.Weekday.THURSDAY: "weekday-thursday",
    DoctorSchedule.Weekday.FRIDAY: "weekday-friday",
    DoctorSchedule.Weekday.SATURDAY: "weekday-saturday",
    DoctorSchedule.Weekday.SUNDAY: "weekday-sunday",
}
SCHEDULING_SETTING_FIELDS = {
    "booking_enabled": {
        "key": SystemSetting.BOOKING_ENABLED,
        "value_type": SystemSetting.ValueType.BOOLEAN,
        "description": "Enable public booking.",
    },
    "booking_min_lead_minutes": {
        "key": SystemSetting.BOOKING_MIN_LEAD_MINUTES,
        "value_type": SystemSetting.ValueType.INTEGER,
        "description": "Minimum lead time before a public booking.",
    },
    "booking_max_days_ahead": {
        "key": SystemSetting.BOOKING_MAX_DAYS_AHEAD,
        "value_type": SystemSetting.ValueType.INTEGER,
        "description": "Maximum public booking window in days.",
    },
    "booking_slot_interval_minutes": {
        "key": SystemSetting.BOOKING_SLOT_INTERVAL_MINUTES,
        "value_type": SystemSetting.ValueType.INTEGER,
        "description": "Public booking slot interval.",
    },
    "appointment_reminder_offset_minutes": {
        "key": SystemSetting.APPOINTMENT_REMINDER_OFFSET_MINUTES,
        "value_type": SystemSetting.ValueType.DURATION_MINUTES,
        "description": "Default appointment reminder offset.",
    },
}
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


def _scheduling_url(
    language,
    *,
    section=None,
    view=None,
    selected_date=None,
    visit_type=None,
    fragment=None,
):
    params = {}
    if language == "en":
        params["lang"] = "en"
    if section:
        params["section"] = section
    if view:
        params["view"] = view
    if selected_date:
        params["date"] = selected_date.isoformat()
    if visit_type:
        params["visit_type"] = visit_type.pk
    query = urlencode(params)
    route = reverse("dashboard_scheduling")
    url = f"{route}?{query}" if query else route
    return f"{url}#{fragment}" if fragment else url


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


def _parse_scheduling_section(raw_section):
    return raw_section if raw_section in SCHEDULING_SECTION_NAMES else "calendar"


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
    active_doctor,
    schedules_by_weekday,
    overrides_by_date,
    closures_by_date,
    appointments_by_date,
):
    weekday_full, weekday_short = SCHEDULING_WEEKDAY_LABELS[language][day.weekday()]
    weekly_rows = schedules_by_weekday.get(day.weekday(), [])
    special_rows = overrides_by_date.get(day, [])
    closures = closures_by_date.get(day, [])
    effective = booking_services.get_effective_working_periods(
        active_doctor,
        day,
        closed=bool(closures),
        special_periods=special_rows,
        weekly_periods=weekly_rows,
    )

    def format_periods(rows):
        return [
            {
                "start": row.start_time.strftime("%H:%M"),
                "end": row.end_time.strftime("%H:%M"),
            }
            for row in rows
        ]

    source_labels = {
        "ar": {
            booking_services.WORKING_PERIOD_SOURCE_CLOSED: "مغلق",
            booking_services.WORKING_PERIOD_SOURCE_SPECIAL: "ساعات مخصصة",
            booking_services.WORKING_PERIOD_SOURCE_WEEKLY: "الجدول الأسبوعي",
        },
        "en": {
            booking_services.WORKING_PERIOD_SOURCE_CLOSED: "Closed",
            booking_services.WORKING_PERIOD_SOURCE_SPECIAL: "Customized hours",
            booking_services.WORKING_PERIOD_SOURCE_WEEKLY: "Weekly schedule",
        },
    }
    periods = format_periods(effective.periods)
    weekly_periods = format_periods(weekly_rows)
    special_periods = format_periods(special_rows)
    override_reasons = [
        {
            "reason": (
                (row.reason_ar if language == "ar" else row.reason_en)
                or (row.reason_en if language == "ar" else row.reason_ar)
            ),
            "start": row.start_time.strftime("%H:%M"),
            "end": row.end_time.strftime("%H:%M"),
        }
        for row in special_rows
        if row.reason_ar or row.reason_en
    ]
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
        "weekly_periods": weekly_periods,
        "special_periods": special_periods,
        "special_reasons": override_reasons,
        "has_special_hours": bool(special_rows),
        "effective_source": effective.source,
        "effective_source_label": source_labels[language][effective.source],
        "closures": closures,
        "is_closed": effective.source == booking_services.WORKING_PERIOD_SOURCE_CLOSED,
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
    section,
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
    overrides_by_date = {}
    closures_by_date = {}
    appointments_by_date = {}
    if active_doctor:
        schedules = DoctorSchedule.objects.filter(
            doctor=active_doctor,
            is_active=True,
        ).order_by("weekday", "start_time", "id")
        for schedule in schedules:
            schedules_by_weekday.setdefault(schedule.weekday, []).append(schedule)

        overrides = DoctorScheduleOverride.objects.filter(
            doctor=active_doctor,
            is_active=True,
            date__range=(visible_dates[0], visible_dates[-1]),
        ).order_by("date", "start_time", "id")
        for override in overrides:
            overrides_by_date.setdefault(override.date, []).append(override)

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
            active_doctor=active_doctor,
            schedules_by_weekday=schedules_by_weekday,
            overrides_by_date=overrides_by_date,
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
            active_doctor=active_doctor,
            schedules_by_weekday=schedules_by_weekday,
            overrides_by_date=overrides_by_date,
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
    section_labels = {
        "ar": {
            "calendar": "التقويم",
            "weekly": "ساعات العمل الأسبوعية",
            "services": "الخدمات",
            "rules": "قواعد الحجز",
            "closures": "الإغلاقات",
        },
        "en": {
            "calendar": "Calendar",
            "weekly": "Weekly Hours",
            "services": "Services",
            "rules": "Booking Rules",
            "closures": "Closures",
        },
    }[language]
    for day_item in day_items:
        day_item["day_view_url"] = _scheduling_url(
            language,
            view="day",
            selected_date=day_item["date"],
            visit_type=selected_visit_type,
            fragment="calendar",
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
                    section=section,
                    view=view,
                    selected_date=selected_date,
                    visit_type=selected_visit_type,
                )
            ),
            "active_dashboard_nav": "scheduling",
            "dashboard_language_switch_url": _scheduling_url(
                alternate_language,
                section=section,
                view=view,
                selected_date=selected_date,
                visit_type=selected_visit_type,
            ),
            "scheduling_view": view,
            "scheduling_section": section,
            "scheduling_sections": [
                {
                    "key": section_name,
                    "label": section_labels[section_name],
                    "url": _scheduling_url(
                        language,
                        section=section_name,
                        view=view if section_name == "calendar" else None,
                        selected_date=selected_date if section_name == "calendar" else None,
                        visit_type=selected_visit_type if section_name == "calendar" else None,
                        fragment={
                            "calendar": "calendar-toolbar",
                            "weekly": "weekly-hours-title",
                            "services": "services-title",
                            "rules": "booking-rules",
                            "closures": "closures-title",
                        }[section_name],
                    ),
                }
                for section_name in SCHEDULING_SECTION_NAMES
            ],
            "scheduling_selected_date": selected_date,
            "scheduling_today": today,
            "scheduling_timezone": timezone.get_current_timezone_name(),
            "scheduling_doctor": active_doctor,
            "scheduling_visit_types": visit_types,
            "scheduling_selected_visit_type": selected_visit_type,
            "scheduling_current_url": _scheduling_url(
                language,
                section="calendar",
                view=view,
                selected_date=selected_date,
                visit_type=selected_visit_type,
                fragment="day-management",
            ),
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
                fragment="calendar",
            ),
            "scheduling_today_url": _scheduling_url(
                language,
                view=view,
                selected_date=today,
                visit_type=selected_visit_type,
                fragment="calendar",
            ),
            "scheduling_next_url": _scheduling_url(
                language,
                view=view,
                selected_date=next_date,
                visit_type=selected_visit_type,
                fragment="calendar",
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
                        fragment="calendar-toolbar",
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


def _localized_post_url(route_name, language, *, fragment=None, **kwargs):
    url = reverse(route_name, kwargs=kwargs or None)
    url = f"{url}?lang=en" if language == "en" else url
    return f"{url}#{fragment}" if fragment else url


def _special_hours_post_url(
    route_name,
    language,
    selected_date,
    *,
    view,
    visit_type=None,
    **kwargs,
):
    params = {"view": view, "date": selected_date.isoformat()}
    if language == "en":
        params["lang"] = "en"
    if visit_type is not None:
        params["visit_type"] = visit_type.pk
    return (
        f"{reverse(route_name, kwargs=kwargs or None)}?{urlencode(params)}"
        "#day-management"
    )


def _booking_rules_initial():
    settings = booking_services.get_booking_settings()
    return {
        "booking_enabled": "true" if settings.enabled else "false",
        "booking_min_lead_minutes": settings.min_lead_minutes,
        "booking_max_days_ahead": settings.max_days_ahead,
        "booking_slot_interval_minutes": settings.slot_interval_minutes,
        "appointment_reminder_offset_minutes": settings.reminder_offset_minutes,
    }


def _scheduling_management_context(
    *,
    language,
    active_doctor,
    visit_types,
    selected_date,
    view,
    selected_visit_type,
    bound_weekly_create_form=None,
    bound_weekly_create_weekday=None,
    bound_weekly_update_form=None,
    bound_weekly_update_period_id=None,
    closure_form=None,
    closure_conflicts=None,
    closure_stage=None,
    service_create_form=None,
    service_conflicts=None,
    service_confirmation=None,
    duration_form=None,
    duration_visit_type_id=None,
    booking_rules_form=None,
    special_create_form=None,
    special_update_form=None,
    special_update_period_id=None,
    special_conflicts=None,
    special_confirmation=None,
):
    periods_by_weekday = {}
    closures = []
    special_periods = []
    managed_visit_types = []
    if active_doctor:
        for period in DoctorSchedule.objects.filter(
            doctor=active_doctor,
            is_active=True,
        ).order_by("weekday", "start_time", "id"):
            periods_by_weekday.setdefault(period.weekday, []).append(period)
        closures = list(
            ClosedDay.objects.filter(
                is_active=True,
                date__gte=timezone.localdate(),
            )
            .filter(Q(doctor=active_doctor) | Q(doctor__isnull=True))
            .order_by("date", "id")
        )
        special_periods = list(
            DoctorScheduleOverride.objects.filter(
                doctor=active_doctor,
                date=selected_date,
                is_active=True,
            ).order_by("start_time", "id")
        )
        managed_visit_types = list(
            VisitType.objects.filter(Q(doctor=active_doctor) | Q(doctor__isnull=True)).order_by(
                "-is_active",
                "display_order",
                "name_en",
                "id",
            )
        )

    weekly_days = []
    for weekday in SCHEDULING_WEEKDAY_DISPLAY_ORDER:
        weekday_anchor = SCHEDULING_WEEKDAY_ANCHORS[weekday]
        create_form = (
            bound_weekly_create_form
            if bound_weekly_create_form is not None and bound_weekly_create_weekday == weekday
            else WeeklyPeriodCreateForm(
                language=language,
                initial={"weekday": weekday},
                auto_id=f"id_weekday_{weekday}_%s",
            )
        )
        period_items = []
        for period in periods_by_weekday.get(weekday, []):
            update_form = (
                bound_weekly_update_form
                if bound_weekly_update_form is not None
                and bound_weekly_update_period_id == period.pk
                else WeeklyPeriodUpdateForm(
                    language=language,
                    initial={
                        "start_time": period.start_time.strftime("%H:%M"),
                        "end_time": period.end_time.strftime("%H:%M"),
                    },
                    auto_id=f"id_period_{period.pk}_%s",
                )
            )
            period_items.append(
                {
                    "period": period,
                    "update_form": update_form,
                    "update_url": _localized_post_url(
                        "dashboard_scheduling_weekly_update",
                        language,
                        fragment=weekday_anchor,
                        period_id=period.pk,
                    ),
                    "deactivate_url": _localized_post_url(
                        "dashboard_scheduling_weekly_deactivate",
                        language,
                        fragment=weekday_anchor,
                        period_id=period.pk,
                    ),
                }
            )
        weekly_days.append(
            {
                "weekday": weekday,
                "anchor": weekday_anchor,
                "label": SCHEDULING_WEEKDAY_LABELS[language][weekday][0],
                "periods": period_items,
                "create_form": create_form,
                "create_url": _localized_post_url(
                    "dashboard_scheduling_weekly_create",
                    language,
                    fragment=weekday_anchor,
                ),
            }
        )

    service_items = []
    for visit_type in managed_visit_types:
        item_form = (
            duration_form
            if duration_form is not None and duration_visit_type_id == visit_type.pk
            else VisitTypeDurationForm(
                language=language,
                initial={"duration_minutes": visit_type.duration_minutes},
                auto_id=f"id_visit_type_{visit_type.pk}_%s",
            )
        )
        service_items.append(
            {
                "visit_type": visit_type,
                "form": item_form,
                "update_url": _localized_post_url(
                    "dashboard_scheduling_service_duration",
                    language,
                    fragment=f"service-{visit_type.pk}",
                    visit_type_id=visit_type.pk,
                ),
                "deactivate_url": _localized_post_url(
                    "dashboard_scheduling_service_deactivate",
                    language,
                    fragment="service-warning",
                    visit_type_id=visit_type.pk,
                ),
                "reactivate_url": _localized_post_url(
                    "dashboard_scheduling_service_reactivate",
                    language,
                    fragment=f"service-{visit_type.pk}",
                    visit_type_id=visit_type.pk,
                ),
            }
        )

    closure_items = [
        {
            "closure": item,
            "deactivate_url": _localized_post_url(
                "dashboard_scheduling_closure_deactivate",
                language,
                fragment="closures-list",
                closure_id=item.pk,
            ),
        }
        for item in closures
    ]
    special_items = []
    for period in special_periods:
        update_form = (
            special_update_form
            if special_update_form is not None and special_update_period_id == period.pk
            else SpecialHoursForm(
                language=language,
                doctor=active_doctor,
                locked_date=period.date,
                instance=period,
                auto_id=f"id_special_{period.pk}_%s",
            )
        )
        special_items.append(
            {
                "period": period,
                "update_form": update_form,
                "update_url": _special_hours_post_url(
                    "dashboard_scheduling_special_update",
                    language,
                    selected_date,
                    view=view,
                    visit_type=selected_visit_type,
                    period_id=period.pk,
                ),
                "deactivate_url": _special_hours_post_url(
                    "dashboard_scheduling_special_deactivate",
                    language,
                    selected_date,
                    view=view,
                    visit_type=selected_visit_type,
                    period_id=period.pk,
                ),
            }
        )
    return {
        "scheduling_weekly_days": weekly_days,
        "scheduling_weekly_create_url": _localized_post_url(
            "dashboard_scheduling_weekly_create", language, fragment="weekly-hours-title"
        ),
        "scheduling_service_items": service_items,
        "scheduling_service_create_form": (
            service_create_form
            if service_create_form is not None
            else VisitTypeCreateForm(
                language=language,
                doctor=active_doctor,
                auto_id="id_service_create_%s",
            )
        ),
        "scheduling_service_create_url": _localized_post_url(
            "dashboard_scheduling_service_create", language, fragment="add-service"
        ),
        "scheduling_service_conflicts": service_conflicts or [],
        "scheduling_service_confirmation": service_confirmation,
        "scheduling_closure_form": (
            closure_form
            if closure_form is not None
            else ClosureCreateForm(language=language, initial={"date": selected_date})
        ),
        "scheduling_closure_conflicts": closure_conflicts or [],
        "scheduling_closure_stage": closure_stage,
        "scheduling_closure_create_url": _localized_post_url(
            "dashboard_scheduling_closure_create", language, fragment="closure-form"
        ),
        "scheduling_closure_items": closure_items,
        "scheduling_booking_rules_form": (
            booking_rules_form
            if booking_rules_form is not None
            else BookingRulesForm(language=language, initial=_booking_rules_initial())
        ),
        "scheduling_booking_rules_url": _localized_post_url(
            "dashboard_scheduling_rules_update", language, fragment="booking-rules"
        ),
        "scheduling_special_create_form": (
            special_create_form
            if special_create_form is not None
            else SpecialHoursForm(
                language=language,
                doctor=active_doctor,
                initial={
                    "date": selected_date,
                    **(
                        {
                            "start_time": periods_by_weekday[selected_date.weekday()][0].start_time,
                            "end_time": periods_by_weekday[selected_date.weekday()][0].end_time,
                        }
                        if not special_periods
                        and periods_by_weekday.get(selected_date.weekday())
                        else {}
                    ),
                },
                auto_id="id_special_create_%s",
            )
        ),
        "scheduling_special_create_url": _special_hours_post_url(
            "dashboard_scheduling_special_create",
            language,
            selected_date,
            view=view,
            visit_type=selected_visit_type,
        ),
        "scheduling_special_items": special_items,
        "scheduling_special_conflicts": special_conflicts or [],
        "scheduling_special_confirmation": special_confirmation,
        "scheduling_customization_open": bool(
            special_create_form is not None
            or special_update_form is not None
            or special_conflicts
            or special_confirmation
        ),
        "scheduling_special_use_weekly_url": _special_hours_post_url(
            "dashboard_scheduling_special_use_weekly",
            language,
            selected_date,
            view=view,
            visit_type=selected_visit_type,
        ),
        "scheduling_close_selected_day_url": _scheduling_url(
            language,
            section="closures",
            selected_date=selected_date,
            fragment="closure-form",
        ),
    }


def _scheduling_page_context(request, *, section=None, **management_overrides):
    language = _dashboard_language(request)
    section = _parse_scheduling_section(section or request.GET.get("section"))
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
        section=section,
        view=view,
        selected_date=selected_date,
        active_doctor=active_doctor,
        visit_types=visit_types,
        selected_visit_type=selected_visit_type,
    )
    context.update(
        _scheduling_management_context(
            language=language,
            active_doctor=active_doctor,
            visit_types=visit_types,
            selected_date=selected_date,
            view=view,
            selected_visit_type=selected_visit_type,
            **management_overrides,
        )
    )
    return context


def _render_scheduling_section(request, section, *, status=200, **management_overrides):
    return render(
        request,
        "dashboard/scheduling.html",
        _scheduling_page_context(
            request,
            section=section,
            **management_overrides,
        ),
        status=status,
    )


@_staff_required
@require_GET
def dashboard_scheduling(request):
    context = _scheduling_page_context(request)
    return render(request, "dashboard/scheduling.html", context)


def _configuration_audit(
    *,
    user,
    action,
    instance,
    message,
    metadata,
):
    AuditLog.objects.create(
        user=user,
        action=action,
        app_label=instance._meta.app_label,
        model_name=instance.__class__.__name__,
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
        message=message,
        metadata=metadata,
    )


def _locked_active_doctor(active_doctor):
    if active_doctor is None:
        return None
    return (
        Doctor.objects.select_for_update()
        .filter(pk=active_doctor.pk, is_active=True)
        .first()
    )


def _scheduling_unavailable_response(request, section):
    return _render_scheduling_section(request, section, status=409)


def _scheduling_redirect(
    language,
    section,
    *,
    selected_date=None,
    view=None,
    fragment=None,
):
    return redirect(
        _scheduling_url(
            language,
            section=section,
            selected_date=selected_date,
            view=view,
            fragment=fragment,
        )
    )


def _special_hours_redirect(request, language, selected_date):
    params = {
        "section": "calendar",
        "view": _parse_scheduling_view(request.GET.get("view")),
        "date": selected_date.isoformat(),
    }
    if language == "en":
        params["lang"] = "en"
    raw_visit_type = request.GET.get("visit_type")
    if raw_visit_type and raw_visit_type.isdigit():
        params["visit_type"] = raw_visit_type
    return redirect(
        f"{reverse('dashboard_scheduling')}?{urlencode(params)}#day-management"
    )


@_staff_required
@require_POST
def dashboard_scheduling_weekly_create(request):
    language = _dashboard_language(request)
    form = WeeklyPeriodCreateForm(request.POST, language=language)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "weekly")
    if not form.is_valid():
        raw_weekday = request.POST.get("weekday")
        try:
            form_weekday = int(raw_weekday)
        except (TypeError, ValueError):
            form_weekday = 0
        if form_weekday not in range(7):
            form_weekday = 0
        return _render_scheduling_section(
            request,
            "weekly",
            status=400,
            bound_weekly_create_form=form,
            bound_weekly_create_weekday=form_weekday,
        )

    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "weekly")
        weekday = form.cleaned_data["weekday"]
        if not form.validate_no_overlap(doctor=doctor, weekday=weekday):
            return _render_scheduling_section(
                request,
                "weekly",
                status=400,
                bound_weekly_create_form=form,
                bound_weekly_create_weekday=weekday,
            )
        period = DoctorSchedule(
            doctor=doctor,
            weekday=weekday,
            start_time=form.cleaned_data["start_time"],
            end_time=form.cleaned_data["end_time"],
            is_active=True,
        )
        period.full_clean()
        period.save()
        _configuration_audit(
            user=request.user,
            action=AuditLog.Action.CREATE,
            instance=period,
            message="Created recurring weekly working period.",
            metadata={
                "weekday": weekday,
                "new_start": period.start_time.strftime("%H:%M"),
                "new_end": period.end_time.strftime("%H:%M"),
                "active": True,
            },
        )
    messages.success(
        request,
        "Working period added." if language == "en" else "تمت إضافة فترة العمل.",
    )
    return _scheduling_redirect(
        language,
        "weekly",
        fragment=SCHEDULING_WEEKDAY_ANCHORS[weekday],
    )


@_staff_required
@require_POST
def dashboard_scheduling_weekly_update(request, period_id):
    language = _dashboard_language(request)
    form = WeeklyPeriodUpdateForm(request.POST, language=language)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "weekly")
    if not form.is_valid():
        return _render_scheduling_section(
            request,
            "weekly",
            status=400,
            bound_weekly_update_form=form,
            bound_weekly_update_period_id=period_id,
        )

    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "weekly")
        period = get_object_or_404(
            DoctorSchedule.objects.select_for_update(),
            pk=period_id,
            doctor=doctor,
            is_active=True,
        )
        if not form.validate_no_overlap(
            doctor=doctor,
            weekday=period.weekday,
            exclude_period_id=period.pk,
        ):
            return _render_scheduling_section(
                request,
                "weekly",
                status=400,
                bound_weekly_update_form=form,
                bound_weekly_update_period_id=period_id,
            )
        old_start = period.start_time.strftime("%H:%M")
        old_end = period.end_time.strftime("%H:%M")
        period.start_time = form.cleaned_data["start_time"]
        period.end_time = form.cleaned_data["end_time"]
        period.full_clean()
        period.save(update_fields=["start_time", "end_time", "updated_at"])
        _configuration_audit(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=period,
            message="Updated recurring weekly working period.",
            metadata={
                "weekday": period.weekday,
                "old_start": old_start,
                "old_end": old_end,
                "new_start": period.start_time.strftime("%H:%M"),
                "new_end": period.end_time.strftime("%H:%M"),
                "active": True,
            },
        )
    messages.success(
        request,
        "Working period updated." if language == "en" else "تم تحديث فترة العمل.",
    )
    return _scheduling_redirect(
        language,
        "weekly",
        fragment=SCHEDULING_WEEKDAY_ANCHORS[period.weekday],
    )


@_staff_required
@require_POST
def dashboard_scheduling_weekly_deactivate(request, period_id):
    language = _dashboard_language(request)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "weekly")
    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "weekly")
        period = get_object_or_404(
            DoctorSchedule.objects.select_for_update(),
            pk=period_id,
            doctor=doctor,
            is_active=True,
        )
        old_start = period.start_time.strftime("%H:%M")
        old_end = period.end_time.strftime("%H:%M")
        period.is_active = False
        period.save(update_fields=["is_active", "updated_at"])
        _configuration_audit(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=period,
            message="Deactivated recurring weekly working period.",
            metadata={
                "weekday": period.weekday,
                "old_start": old_start,
                "old_end": old_end,
                "active": False,
            },
        )
    messages.success(
        request,
        "Working period deactivated."
        if language == "en"
        else "تم إيقاف فترة العمل.",
    )
    return _scheduling_redirect(
        language,
        "weekly",
        fragment=SCHEDULING_WEEKDAY_ANCHORS[period.weekday],
    )


def _special_hours_period_bounds(day, periods):
    current_timezone = timezone.get_current_timezone()
    return [
        (
            timezone.make_aware(
                datetime.combine(day, period.start_time),
                current_timezone,
            ),
            timezone.make_aware(
                datetime.combine(day, period.end_time),
                current_timezone,
            ),
        )
        for period in periods
    ]


def _special_hours_conflicts(doctor, day, proposed_periods):
    day_start, day_end = _local_day_bounds(day)
    appointments = list(
        Appointment.objects.filter(
            doctor=doctor,
            status__in=booking_services.BLOCKING_APPOINTMENT_STATUSES,
            starts_at__lt=day_end,
            ends_at__gt=day_start,
        )
        .select_related("patient", "visit_type")
        .order_by("starts_at", "id")
    )
    period_bounds = _special_hours_period_bounds(day, proposed_periods)
    return [
        appointment
        for appointment in appointments
        if not any(
            period_start <= appointment.starts_at
            and appointment.ends_at <= period_end
            for period_start, period_end in period_bounds
        )
    ]


def _special_hours_conflict_items(appointments, language):
    return [
        {
            "time": (
                f"{timezone.localtime(appointment.starts_at).strftime('%H:%M')}–"
                f"{timezone.localtime(appointment.ends_at).strftime('%H:%M')}"
            ),
            "patient_name": appointment.patient.full_name,
            "service": _localized_visit_type_name(appointment.visit_type, language),
            "status": DASHBOARD_STATUS_LABELS[language].get(
                appointment.status,
                appointment.get_status_display(),
            ),
        }
        for appointment in appointments
    ]


def _special_hours_confirmation(
    request,
    *,
    language,
    operation,
    day,
    form=None,
    hidden_fields=None,
):
    operation_labels = {
        "ar": {
            "create": "إضافة الساعات المخصصة رغم التعارضات",
            "update": "حفظ الساعات المخصصة رغم التعارضات",
            "deactivate": "إيقاف الفترة المخصصة رغم التعارضات",
            "use_weekly": "استخدام الدوام الأسبوعي رغم التعارضات",
        },
        "en": {
            "create": "Add customized hours despite conflicts",
            "update": "Save customized hours despite conflicts",
            "deactivate": "Deactivate customized period despite conflicts",
            "use_weekly": "Use weekly schedule despite conflicts",
        },
    }
    return {
        "action_url": f"{request.get_full_path()}#day-management",
        "operation": operation,
        "operation_label": operation_labels[language][operation],
        "date": day,
        "form": form,
        "hidden_fields": hidden_fields or [],
    }


def _render_special_hours_form_error(
    request,
    *,
    form,
    period_id=None,
):
    overrides = {"special_create_form": form}
    if period_id is not None:
        overrides = {
            "special_update_form": form,
            "special_update_period_id": period_id,
        }
    return _render_scheduling_section(
        request,
        "calendar",
        status=400,
        **overrides,
    )


@_staff_required
@require_POST
def dashboard_scheduling_special_create(request):
    language = _dashboard_language(request)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "calendar")
    form = SpecialHoursForm(request.POST, language=language, doctor=active_doctor)
    if not form.is_valid():
        return _render_special_hours_form_error(request, form=form)

    confirmed = request.POST.get("confirm_special_hours") == "yes"
    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "calendar")
        form = SpecialHoursForm(request.POST, language=language, doctor=doctor)
        if not form.is_valid() or not form.validate_no_overlap(doctor=doctor):
            return _render_special_hours_form_error(request, form=form)

        special_date = form.cleaned_data["date"]
        current_periods = list(
            DoctorScheduleOverride.objects.select_for_update()
            .filter(doctor=doctor, date=special_date, is_active=True)
            .order_by("start_time", "id")
        )
        proposed_periods = [*current_periods, form.instance]
        conflicts = _special_hours_conflicts(doctor, special_date, proposed_periods)
        if conflicts and not confirmed:
            return _render_scheduling_section(
                request,
                "calendar",
                special_create_form=form,
                special_conflicts=_special_hours_conflict_items(conflicts, language),
                special_confirmation=_special_hours_confirmation(
                    request,
                    language=language,
                    operation="create",
                    day=special_date,
                    form=form,
                ),
            )

        period = form.save(commit=False)
        period.doctor = doctor
        period.is_active = True
        period.full_clean()
        period.save()
        _configuration_audit(
            user=request.user,
            action=AuditLog.Action.CREATE,
            instance=period,
            message="Created date-specific Special Hours.",
            metadata={
                "operation": "create",
                "date": period.date.isoformat(),
                "new_start": period.start_time.strftime("%H:%M"),
                "new_end": period.end_time.strftime("%H:%M"),
                "active": True,
                "reason_ar": period.reason_ar,
                "reason_en": period.reason_en,
            },
        )
    messages.success(
        request,
        "Special Hours added." if language == "en" else "تمت إضافة الساعات الخاصة.",
    )
    return _special_hours_redirect(request, language, special_date)


@_staff_required
@require_POST
def dashboard_scheduling_special_update(request, period_id):
    language = _dashboard_language(request)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "calendar")
    current_period = get_object_or_404(
        DoctorScheduleOverride,
        pk=period_id,
        doctor=active_doctor,
        is_active=True,
    )
    form = SpecialHoursForm(
        request.POST,
        language=language,
        doctor=active_doctor,
        locked_date=current_period.date,
        instance=current_period,
    )
    if not form.is_valid():
        return _render_special_hours_form_error(request, form=form, period_id=period_id)

    confirmed = request.POST.get("confirm_special_hours") == "yes"
    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "calendar")
        period = get_object_or_404(
            DoctorScheduleOverride.objects.select_for_update(),
            pk=period_id,
            doctor=doctor,
            is_active=True,
        )
        old_start = period.start_time.strftime("%H:%M")
        old_end = period.end_time.strftime("%H:%M")
        old_reason_ar = period.reason_ar
        old_reason_en = period.reason_en
        form = SpecialHoursForm(
            request.POST,
            language=language,
            doctor=doctor,
            locked_date=period.date,
            instance=period,
        )
        if not form.is_valid() or not form.validate_no_overlap(
            doctor=doctor,
            exclude_period_id=period.pk,
        ):
            return _render_special_hours_form_error(request, form=form, period_id=period_id)

        current_periods = list(
            DoctorScheduleOverride.objects.select_for_update()
            .filter(doctor=doctor, date=period.date, is_active=True)
            .order_by("start_time", "id")
        )
        proposed_periods = [
            candidate for candidate in current_periods if candidate.pk != period.pk
        ]
        proposed_periods.append(form.instance)
        conflicts = _special_hours_conflicts(doctor, period.date, proposed_periods)
        if conflicts and not confirmed:
            return _render_scheduling_section(
                request,
                "calendar",
                special_update_form=form,
                special_update_period_id=period_id,
                special_conflicts=_special_hours_conflict_items(conflicts, language),
                special_confirmation=_special_hours_confirmation(
                    request,
                    language=language,
                    operation="update",
                    day=period.date,
                    form=form,
                ),
            )

        period = form.save(commit=False)
        period.doctor = doctor
        period.is_active = True
        period.full_clean()
        period.save(
            update_fields=[
                "start_time",
                "end_time",
                "reason_ar",
                "reason_en",
                "updated_at",
            ]
        )
        _configuration_audit(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=period,
            message="Updated date-specific Special Hours.",
            metadata={
                "operation": "update",
                "date": period.date.isoformat(),
                "old_start": old_start,
                "old_end": old_end,
                "new_start": period.start_time.strftime("%H:%M"),
                "new_end": period.end_time.strftime("%H:%M"),
                "active": True,
                "old_reason_ar": old_reason_ar,
                "old_reason_en": old_reason_en,
                "new_reason_ar": period.reason_ar,
                "new_reason_en": period.reason_en,
            },
        )
    messages.success(
        request,
        "Special Hours updated." if language == "en" else "تم تحديث الساعات الخاصة.",
    )
    return _special_hours_redirect(request, language, period.date)


@_staff_required
@require_POST
def dashboard_scheduling_special_deactivate(request, period_id):
    language = _dashboard_language(request)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "calendar")
    confirmed = request.POST.get("confirm_special_hours") == "yes"
    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "calendar")
        period = get_object_or_404(
            DoctorScheduleOverride.objects.select_for_update(),
            pk=period_id,
            doctor=doctor,
            is_active=True,
        )
        current_periods = list(
            DoctorScheduleOverride.objects.select_for_update()
            .filter(doctor=doctor, date=period.date, is_active=True)
            .order_by("start_time", "id")
        )
        proposed_periods = [
            candidate for candidate in current_periods if candidate.pk != period.pk
        ]
        if not proposed_periods:
            proposed_periods = list(
                DoctorSchedule.objects.select_for_update()
                .filter(
                    doctor=doctor,
                    weekday=period.date.weekday(),
                    is_active=True,
                )
                .order_by("start_time", "id")
            )
        conflicts = _special_hours_conflicts(doctor, period.date, proposed_periods)
        if conflicts and not confirmed:
            return _render_scheduling_section(
                request,
                "calendar",
                special_conflicts=_special_hours_conflict_items(conflicts, language),
                special_confirmation=_special_hours_confirmation(
                    request,
                    language=language,
                    operation="deactivate",
                    day=period.date,
                ),
            )

        old_start = period.start_time.strftime("%H:%M")
        old_end = period.end_time.strftime("%H:%M")
        period.is_active = False
        period.save(update_fields=["is_active", "updated_at"])
        _configuration_audit(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=period,
            message="Deactivated date-specific Special Hours.",
            metadata={
                "operation": "deactivate",
                "date": period.date.isoformat(),
                "old_start": old_start,
                "old_end": old_end,
                "active": False,
                "reason_ar": period.reason_ar,
                "reason_en": period.reason_en,
            },
        )
    messages.success(
        request,
        "Special Hours deactivated."
        if language == "en"
        else "تم إيقاف الساعات الخاصة.",
    )
    return _special_hours_redirect(request, language, period.date)


@_staff_required
@require_POST
def dashboard_scheduling_special_use_weekly(request):
    language = _dashboard_language(request)
    form = SpecialHoursDateForm(request.POST, language=language)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "calendar")
    if not form.is_valid():
        return _render_scheduling_section(request, "calendar", status=400)

    confirmed = request.POST.get("confirm_special_hours") == "yes"
    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "calendar")
        form = SpecialHoursDateForm(request.POST, language=language)
        if not form.is_valid():
            return _render_scheduling_section(request, "calendar", status=400)
        special_date = form.cleaned_data["date"]
        periods = list(
            DoctorScheduleOverride.objects.select_for_update()
            .filter(doctor=doctor, date=special_date, is_active=True)
            .order_by("start_time", "id")
        )
        if not periods:
            messages.info(
                request,
                "The weekly schedule is already in use."
                if language == "en"
                else "الجدول الأسبوعي مستخدم بالفعل.",
            )
            return _special_hours_redirect(request, language, special_date)

        weekly_periods = list(
            DoctorSchedule.objects.select_for_update()
            .filter(
                doctor=doctor,
                weekday=special_date.weekday(),
                is_active=True,
            )
            .order_by("start_time", "id")
        )
        conflicts = _special_hours_conflicts(doctor, special_date, weekly_periods)
        if conflicts and not confirmed:
            return _render_scheduling_section(
                request,
                "calendar",
                special_conflicts=_special_hours_conflict_items(conflicts, language),
                special_confirmation=_special_hours_confirmation(
                    request,
                    language=language,
                    operation="use_weekly",
                    day=special_date,
                    hidden_fields=[
                        {"name": "date", "value": special_date.isoformat()}
                    ],
                ),
            )

        for period in periods:
            old_start = period.start_time.strftime("%H:%M")
            old_end = period.end_time.strftime("%H:%M")
            period.is_active = False
            period.save(update_fields=["is_active", "updated_at"])
            _configuration_audit(
                user=request.user,
                action=AuditLog.Action.UPDATE,
                instance=period,
                message="Returned date-specific Special Hours to weekly schedule.",
                metadata={
                    "operation": "use_weekly_schedule",
                    "date": period.date.isoformat(),
                    "old_start": old_start,
                    "old_end": old_end,
                    "active": False,
                    "reason_ar": period.reason_ar,
                    "reason_en": period.reason_en,
                },
            )
    messages.success(
        request,
        "Weekly schedule restored for this date."
        if language == "en"
        else "تمت العودة إلى الجدول الأسبوعي لهذا التاريخ.",
    )
    return _special_hours_redirect(request, language, special_date)


def _closure_conflict_queryset(doctor, closure_date):
    day_start, day_end = _local_day_bounds(closure_date)
    return (
        Appointment.objects.filter(
            doctor=doctor,
            status__in=booking_services.BLOCKING_APPOINTMENT_STATUSES,
            starts_at__lt=day_end,
            ends_at__gt=day_start,
        )
        .select_related("patient", "visit_type")
        .order_by("starts_at", "id")
    )


def _closure_conflict_items(appointments, language):
    return [
        {
            "time": timezone.localtime(appointment.starts_at).strftime("%H:%M"),
            "patient_name": appointment.patient.full_name,
            "service": _localized_visit_type_name(appointment.visit_type, language),
            "status": DASHBOARD_STATUS_LABELS[language].get(
                appointment.status,
                appointment.get_status_display(),
            ),
        }
        for appointment in appointments
    ]


@_staff_required
@require_POST
def dashboard_scheduling_closure_create(request):
    language = _dashboard_language(request)
    form = ClosureCreateForm(request.POST, language=language)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "closures")
    if not form.is_valid():
        return _render_scheduling_section(
            request,
            "closures",
            status=400,
            closure_form=form,
        )

    closure_action = request.POST.get("closure_action")
    confirm_cancellation = request.POST.get("confirm_cancellation") == "yes"
    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "closures")
        closure_date = form.cleaned_data["date"]
        existing = (
            ClosedDay.objects.select_for_update()
            .filter(is_active=True, date=closure_date)
            .filter(Q(doctor=doctor) | Q(doctor__isnull=True))
        )
        if existing.exists():
            form.add_error(
                "date",
                "This date is already closed."
                if language == "en"
                else "هذا التاريخ مغلق بالفعل.",
            )
            return _render_scheduling_section(
                request,
                "closures",
                status=400,
                closure_form=form,
            )

        # Every choice and final confirmation uses the current blocking rows.
        # The final destructive step locks the rows before calling the existing
        # cancellation operation, so it never trusts a previously rendered count.
        conflict_queryset = _closure_conflict_queryset(doctor, closure_date)
        if closure_action == "cancel" and confirm_cancellation:
            conflict_queryset = conflict_queryset.select_for_update()
        conflicts = list(conflict_queryset)
        if conflicts:
            if closure_action == "cancel" and not confirm_cancellation:
                return _render_scheduling_section(
                    request,
                    "closures",
                    closure_form=form,
                    closure_conflicts=_closure_conflict_items(conflicts, language),
                    closure_stage="cancel_confirmation",
                )
            if closure_action not in {"keep", "cancel"}:
                return _render_scheduling_section(
                    request,
                    "closures",
                    closure_form=form,
                    closure_conflicts=_closure_conflict_items(conflicts, language),
                    closure_stage="choices",
                )

        closure = ClosedDay(
            doctor=doctor,
            date=closure_date,
            reason_ar=form.cleaned_data.get("reason_ar", ""),
            reason_en=form.cleaned_data.get("reason_en", ""),
            is_active=True,
        )
        closure.full_clean()
        closure.save()
        _configuration_audit(
            user=request.user,
            action=AuditLog.Action.CREATE,
            instance=closure,
            message="Created full-day clinic closure.",
            metadata={
                "date": closure.date.isoformat(),
                "active": True,
                "reason_ar": closure.reason_ar,
                "reason_en": closure.reason_en,
                "operation": (
                    "close_and_cancel_appointments"
                    if closure_action == "cancel" and confirm_cancellation
                    else "close_and_keep_appointments"
                ),
                "cancelled_appointment_count": (
                    len(conflicts)
                    if closure_action == "cancel" and confirm_cancellation
                    else 0
                ),
            },
        )
        if closure_action == "cancel" and confirm_cancellation:
            for appointment in conflicts:
                booking_operations.cancel_appointment(
                    appointment.pk,
                    actor=request.user,
                    note="Clinic date closed through Scheduling Center.",
                )
    messages.success(
        request,
        (
            f"Full-day closure added and {len(conflicts)} affected appointment(s) cancelled."
            if language == "en"
            else f"تم إغلاق اليوم وإلغاء {len(conflicts)} من المواعيد المتأثرة."
        )
        if closure_action == "cancel" and confirm_cancellation
        else (
            "Full-day closure added. Existing appointments were kept unchanged."
            if language == "en"
            else "تم إغلاق اليوم مع إبقاء المواعيد الموجودة دون تغيير."
        ),
    )
    return _scheduling_redirect(
        language,
        "closures",
        selected_date=closure_date,
        fragment="closures-list",
    )


@_staff_required
@require_POST
def dashboard_scheduling_closure_deactivate(request, closure_id):
    language = _dashboard_language(request)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "closures")
    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "closures")
        closure = get_object_or_404(
            ClosedDay.objects.select_for_update().filter(
                Q(doctor=doctor) | Q(doctor__isnull=True)
            ),
            pk=closure_id,
            is_active=True,
        )
        closure.is_active = False
        closure.save(update_fields=["is_active", "updated_at"])
        _configuration_audit(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=closure,
            message="Deactivated full-day clinic closure.",
            metadata={
                "date": closure.date.isoformat(),
                "active": False,
                "reason_ar": closure.reason_ar,
                "reason_en": closure.reason_en,
            },
        )
    messages.success(
        request,
        "Closure deactivated." if language == "en" else "تم إلغاء تفعيل الإغلاق.",
    )
    return _scheduling_redirect(
        language,
        "closures",
        selected_date=closure.date,
        fragment="closures-list",
    )


@_staff_required
@require_POST
def dashboard_scheduling_service_create(request):
    language = _dashboard_language(request)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "services")
    form = VisitTypeCreateForm(
        request.POST,
        language=language,
        doctor=active_doctor,
    )
    if not form.is_valid():
        return _render_scheduling_section(
            request,
            "services",
            status=400,
            service_create_form=form,
        )

    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "services")
        form = VisitTypeCreateForm(request.POST, language=language, doctor=doctor)
        if not form.is_valid():
            return _render_scheduling_section(
                request,
                "services",
                status=400,
                service_create_form=form,
            )
        visit_type = form.save(commit=False)
        visit_type.doctor = doctor
        visit_type.is_active = True
        visit_type.full_clean()
        visit_type.save()
        _configuration_audit(
            user=request.user,
            action=AuditLog.Action.CREATE,
            instance=visit_type,
            message="Created scheduling visit type.",
            metadata={
                "name_ar": visit_type.name_ar,
                "name_en": visit_type.name_en,
                "duration_minutes": visit_type.duration_minutes,
                "active": True,
            },
        )
    messages.success(
        request,
        "Service added." if language == "en" else "تمت إضافة الخدمة.",
    )
    return _scheduling_redirect(
        language,
        "services",
        fragment=f"service-{visit_type.pk}",
    )


def _service_future_conflict_queryset(doctor, visit_type):
    return (
        Appointment.objects.filter(
            doctor=doctor,
            visit_type=visit_type,
            status__in=booking_services.BLOCKING_APPOINTMENT_STATUSES,
            starts_at__gte=timezone.now(),
        )
        .select_related("patient", "visit_type")
        .order_by("starts_at", "id")
    )


@_staff_required
@require_POST
def dashboard_scheduling_service_deactivate(request, visit_type_id):
    language = _dashboard_language(request)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "services")
    confirmed = request.POST.get("confirm_service_deactivation") == "yes"
    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "services")
        visit_type = get_object_or_404(
            VisitType.objects.select_for_update().filter(
                Q(doctor=doctor) | Q(doctor__isnull=True)
            ),
            pk=visit_type_id,
            is_active=True,
        )
        conflicts = list(_service_future_conflict_queryset(doctor, visit_type))
        if conflicts and not confirmed:
            return _render_scheduling_section(
                request,
                "services",
                service_conflicts=_closure_conflict_items(conflicts, language),
                service_confirmation={
                    "visit_type": visit_type,
                    "action_url": _localized_post_url(
                        "dashboard_scheduling_service_deactivate",
                        language,
                        fragment="service-warning",
                        visit_type_id=visit_type.pk,
                    ),
                    "cancel_url": _scheduling_url(
                        language,
                        section="services",
                        fragment=f"service-{visit_type.pk}",
                    ),
                },
            )
        visit_type.is_active = False
        visit_type.save(update_fields=["is_active", "updated_at"])
        _configuration_audit(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=visit_type,
            message="Deactivated scheduling visit type.",
            metadata={"old_active": True, "new_active": False},
        )
    messages.success(
        request,
        "Service deactivated. Existing appointments were not changed."
        if language == "en"
        else "تم إيقاف الخدمة دون تغيير المواعيد الموجودة.",
    )
    return _scheduling_redirect(
        language,
        "services",
        fragment=f"service-{visit_type.pk}",
    )


@_staff_required
@require_POST
def dashboard_scheduling_service_reactivate(request, visit_type_id):
    language = _dashboard_language(request)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "services")
    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "services")
        visit_type = get_object_or_404(
            VisitType.objects.select_for_update().filter(
                Q(doctor=doctor) | Q(doctor__isnull=True)
            ),
            pk=visit_type_id,
            is_active=False,
        )
        visit_type.is_active = True
        visit_type.full_clean()
        visit_type.save(update_fields=["is_active", "updated_at"])
        _configuration_audit(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=visit_type,
            message="Reactivated scheduling visit type.",
            metadata={"old_active": False, "new_active": True},
        )
    messages.success(
        request,
        "Service reactivated." if language == "en" else "تمت إعادة تفعيل الخدمة.",
    )
    return _scheduling_redirect(
        language,
        "services",
        fragment=f"service-{visit_type.pk}",
    )


@_staff_required
@require_POST
def dashboard_scheduling_service_duration(request, visit_type_id):
    language = _dashboard_language(request)
    form = VisitTypeDurationForm(request.POST, language=language)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "services")
    if not form.is_valid():
        return _render_scheduling_section(
            request,
            "services",
            status=400,
            duration_form=form,
            duration_visit_type_id=visit_type_id,
        )

    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "services")
        visit_type = get_object_or_404(
            VisitType.objects.select_for_update().filter(
                Q(doctor=doctor) | Q(doctor__isnull=True)
            ),
            pk=visit_type_id,
        )
        old_duration = visit_type.duration_minutes
        visit_type.duration_minutes = form.cleaned_data["duration_minutes"]
        visit_type.full_clean()
        visit_type.save(update_fields=["duration_minutes", "updated_at"])
        _configuration_audit(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=visit_type,
            message="Updated visit type scheduling duration.",
            metadata={
                "old_duration_minutes": old_duration,
                "new_duration_minutes": visit_type.duration_minutes,
            },
        )
    messages.success(
        request,
        "Service duration updated." if language == "en" else "تم تحديث مدة الخدمة.",
    )
    return _scheduling_redirect(
        language,
        "services",
        fragment=f"service-{visit_type.pk}",
    )


def _booking_rule_storage_value(field_name, cleaned_value):
    if field_name == "booking_enabled":
        return "true" if cleaned_value else "false"
    return str(cleaned_value)


@_staff_required
@require_POST
def dashboard_scheduling_rules_update(request):
    language = _dashboard_language(request)
    form = BookingRulesForm(request.POST, language=language)
    active_doctor = get_active_doctor()
    if active_doctor is None:
        return _scheduling_unavailable_response(request, "rules")
    if not form.is_valid():
        return _render_scheduling_section(
            request,
            "rules",
            status=400,
            booking_rules_form=form,
        )

    with transaction.atomic():
        doctor = _locked_active_doctor(active_doctor)
        if doctor is None:
            return _scheduling_unavailable_response(request, "rules")
        allowed_keys = [spec["key"] for spec in SCHEDULING_SETTING_FIELDS.values()]
        existing_settings = {
            setting.key: setting
            for setting in SystemSetting.objects.select_for_update().filter(key__in=allowed_keys)
        }
        for field_name, spec in SCHEDULING_SETTING_FIELDS.items():
            new_value = _booking_rule_storage_value(
                field_name,
                form.cleaned_data[field_name],
            )
            setting = existing_settings.get(spec["key"])
            old_value = setting.value if setting is not None else None
            if setting is None:
                setting = SystemSetting.objects.create(
                    key=spec["key"],
                    value=new_value,
                    value_type=spec["value_type"],
                    description=spec["description"],
                )
                changed = True
            else:
                changed = setting.value != new_value or setting.value_type != spec["value_type"]
                setting.value = new_value
                if setting.value_type != spec["value_type"]:
                    setting.value_type = spec["value_type"]
                if changed:
                    setting.save(update_fields=["value", "value_type", "updated_at"])
            if changed:
                _configuration_audit(
                    user=request.user,
                    action=AuditLog.Action.SETTINGS_CHANGE,
                    instance=setting,
                    message="Updated scheduling booking rule.",
                    metadata={
                        "key": spec["key"],
                        "old_value": old_value,
                        "new_value": new_value,
                    },
                )
    messages.success(
        request,
        "Booking rules updated." if language == "en" else "تم تحديث قواعد الحجز.",
    )
    return _scheduling_redirect(language, "rules", fragment="booking-rules")


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
