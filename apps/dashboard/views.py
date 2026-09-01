import calendar
import re
from datetime import date, datetime, time, timedelta
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
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
from apps.records.models import (
    ClinicalNote,
    PatientTimelineEvent,
    PublicCase,
    PublicCaseMedia,
    RecordMedia,
    RecordMediaFolder,
    VisitRecord,
)
from apps.records.storage import schedule_public_case_media_file_deletion

from .forms import (
    BookingRulesForm,
    ClosureCreateForm,
    SpecialHoursDateForm,
    SpecialHoursForm,
    StaffClinicalNoteForm,
    StaffPublicCaseAddMediaForm,
    StaffPublicCaseCreateForm,
    StaffPublicCaseMediaRoleForm,
    StaffPublicCasePublishForm,
    StaffPublicCaseUpdateForm,
    StaffRecordMediaCreateForm,
    StaffRecordMediaFolderForm,
    StaffRecordMediaUpdateForm,
    StaffVisitRecordForm,
    VisitTypeCreateForm,
    VisitTypeDurationForm,
    WeeklyPeriodCreateForm,
    WeeklyPeriodUpdateForm,
)


RECORD_VISIBILITY_LABELS = {
    "ar": {
        RecordMedia.Visibility.PRIVATE_ONLY: "خاص فقط",
        RecordMedia.Visibility.VISIBLE_TO_PATIENT: "ظاهر للمريض",
    },
    "en": {
        RecordMedia.Visibility.PRIVATE_ONLY: "Private only",
        RecordMedia.Visibility.VISIBLE_TO_PATIENT: "Visible to patient",
    },
}
RECORD_NOTE_TYPE_LABELS = {
    "ar": {
        ClinicalNote.NoteType.DOCTOR_NOTE: "ملاحظة طبيب",
        ClinicalNote.NoteType.STAFF_NOTE: "ملاحظة طاقم",
        ClinicalNote.NoteType.FOLLOW_UP: "متابعة",
    },
    "en": dict(ClinicalNote.NoteType.choices),
}
RECORD_MEDIA_TYPE_LABELS = {
    "ar": {
        RecordMedia.MediaType.IMAGE: "صورة",
        RecordMedia.MediaType.SHORT_VIDEO: "فيديو قصير",
    },
    "en": dict(RecordMedia.MediaType.choices),
}
DELETION_MEDIA_TYPE_LABELS = {
    "ar": {
        RecordMedia.MediaType.IMAGE: "صورة",
        RecordMedia.MediaType.SHORT_VIDEO: "فيديو",
    },
    "en": {
        RecordMedia.MediaType.IMAGE: "Image",
        RecordMedia.MediaType.SHORT_VIDEO: "Video",
    },
}
RECENT_UPLOAD_DISCARD_WINDOW = timedelta(minutes=10)
PUBLIC_CASE_ROLE_LABELS = {
    "ar": {
        PublicCaseMedia.Role.PRIMARY: "أساسي",
        PublicCaseMedia.Role.BEFORE: "قبل",
        PublicCaseMedia.Role.AFTER: "بعد",
        PublicCaseMedia.Role.VIDEO: "فيديو",
        PublicCaseMedia.Role.VIDEO_COVER: "غلاف فيديو",
    },
    "en": dict(PublicCaseMedia.Role.choices),
}
PATIENT_GENDER_LABELS = {
    "ar": {
        Patient.Gender.FEMALE: "أنثى",
        Patient.Gender.MALE: "ذكر",
        Patient.Gender.OTHER: "آخر",
        Patient.Gender.PREFER_NOT_TO_SAY: "يفضل عدم الإفصاح",
    },
    "en": dict(Patient.Gender.choices),
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
PATIENT_SEARCH_MAX_LENGTH = 100
E164_PHONE_RE = re.compile(r"^\+[1-9][0-9]{7,14}$")
SAFE_RAW_PHONE_RE = re.compile(r"^\+?[0-9() .-]+$")
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


def _dashboard_patient_list_url(language, *, query=""):
    params = {}
    if language == "en":
        params["lang"] = "en"
    if query:
        params["q"] = query
    encoded_params = urlencode(params)
    route = reverse("dashboard_patient_list")
    return f"{route}?{encoded_params}" if encoded_params else route


def _dashboard_public_case_url(language, route_name="dashboard_public_case_list", **kwargs):
    route = reverse(route_name, kwargs=kwargs or None)
    return f"{route}?lang=en" if language == "en" else route


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
            "public_cases": "الحالات العامة",
            "scheduling": "الجدولة",
        },
        "en": {
            "overview": "Overview",
            "appointments": "Appointments",
            "patients": "Patients",
            "public_cases": "Public Cases",
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
                    "key": "public_cases",
                    "label": labels["public_cases"],
                    "url": _dashboard_public_case_url(language),
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


def _dashboard_record_url(
    route_name,
    language,
    *,
    kwargs=None,
    query_params=None,
    fragment=None,
):
    route = reverse(route_name, kwargs=kwargs)
    params = {
        key: value
        for key, value in (query_params or {}).items()
        if value not in (None, "")
    }
    if language == "en":
        params["lang"] = "en"
    if params:
        route = f"{route}?{urlencode(params)}"
    return f"{route}#{fragment}" if fragment else route


def _patient_record_detail_url(
    patient,
    language="ar",
    *,
    query_params=None,
    fragment=None,
):
    return _dashboard_record_url(
        "dashboard_patient_record_detail",
        language,
        kwargs={"patient_id": patient.id},
        query_params=query_params,
        fragment=fragment,
    )


def _dashboard_record_context(
    request,
    *,
    patient,
    route_name,
    route_kwargs,
    query_params=None,
    **extra,
):
    language = _dashboard_language(request)
    alternate_language = "en" if language == "ar" else "ar"
    context = _dashboard_home_context(
        request,
        language=language,
        metrics={},
        schedule_items=[],
    )
    patient_list_url = _dashboard_patient_list_url(language)
    for nav_item in context["dashboard_nav_items"]:
        if nav_item["key"] == "patients":
            nav_item["url"] = patient_list_url
            break

    current_url = _dashboard_record_url(
        route_name,
        language,
        kwargs=route_kwargs,
        query_params=query_params,
    )
    context.update(
        {
            "page_key": "dashboard_patient_record",
            "page_title": (
                f"سجل المريض | {context['clinic']['name_ar']}"
                if language == "ar"
                else f"Patient Record | {context['clinic']['name_en']}"
            ),
            "meta_description": (
                "إدارة سجل المريض والوسائط الخاصة ضمن بوابة الطاقم."
                if language == "ar"
                else "Manage the patient record and private media in the staff portal."
            ),
            "canonical_url": request.build_absolute_uri(current_url),
            "active_dashboard_nav": "patients",
            "dashboard_patients_url": patient_list_url,
            "dashboard_language_switch_url": _dashboard_record_url(
                route_name,
                alternate_language,
                kwargs=route_kwargs,
                query_params=query_params,
            ),
            "patient": patient,
            "patient_record_url": _patient_record_detail_url(patient, language),
            "patient_gender_label": PATIENT_GENDER_LABELS[language].get(
                patient.gender,
                patient.get_gender_display(),
            ),
            "has_patient_age": patient.age is not None,
        }
    )
    context.update(extra)
    return context


def _record_visibility_label(is_visible_to_patient, language):
    visibility = (
        RecordMedia.Visibility.VISIBLE_TO_PATIENT
        if is_visible_to_patient
        else RecordMedia.Visibility.PRIVATE_ONLY
    )
    return RECORD_VISIBILITY_LABELS[language][visibility]


def _media_status_labels(media, language):
    labels = [
        {
            "label": RECORD_VISIBILITY_LABELS[language].get(
                media.visibility,
                media.get_visibility_display(),
            ),
            "class": f"status-{media.visibility}",
        }
    ]
    if not media.is_active:
        labels.append(
            {
                "label": "غير نشط" if language == "ar" else "Inactive",
                "class": "status-inactive",
            }
        )
    return labels


def _recent_upload_discard_eligible(media, user, *, now=None):
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    now = now or timezone.now()
    return (
        media.uploaded_by_id is not None
        and media.uploaded_by_id == user.id
        and media.trashed_at is None
        and media.is_active
        and media.visibility == RecordMedia.Visibility.PRIVATE_ONLY
        and media.uploaded_at >= now - RECENT_UPLOAD_DISCARD_WINDOW
    )


def _media_items(
    media_queryset,
    language,
    request_user=None,
    *,
    query_params=None,
):
    items = []
    now = timezone.now()
    for media in media_queryset:
        staff_preview_url = ""
        staff_download_url = ""
        if media.is_active and media.file_exists:
            staff_preview_url = reverse(
                "record_private_media_view",
                kwargs={
                    "patient_id": media.patient_id,
                    "public_id": media.public_id,
                },
            )
            staff_download_url = reverse(
                "record_private_media_download",
                kwargs={
                    "patient_id": media.patient_id,
                    "public_id": media.public_id,
                },
            )
        items.append(
            {
                "media": media,
                "media_type_label": RECORD_MEDIA_TYPE_LABELS[language].get(
                    media.media_type,
                    media.get_media_type_display(),
                ),
                "status_labels": _media_status_labels(media, language),
                "staff_preview_url": staff_preview_url,
                "staff_download_url": staff_download_url,
                "folder_label": (
                    media.folder.name
                    if media.folder_id
                    else ("بدون مجلد" if language == "ar" else "Unfiled")
                ),
                "edit_url": _dashboard_record_url(
                    "dashboard_media_update",
                    language,
                    kwargs={
                        "patient_id": media.patient_id,
                        "public_id": media.public_id,
                    },
                ),
                "trash_url": (
                    _dashboard_record_url(
                        "dashboard_media_trash",
                        language,
                        kwargs={
                            "patient_id": media.patient_id,
                            "public_id": media.public_id,
                        },
                        query_params=query_params,
                    )
                    if request_user is not None
                    and media.trashed_at is None
                    and media.uploaded_by_id == request_user.id
                    else ""
                ),
                "discard_url": (
                    _dashboard_record_url(
                        "dashboard_media_discard_recent",
                        language,
                        kwargs={
                            "patient_id": media.patient_id,
                            "public_id": media.public_id,
                        },
                        query_params=query_params,
                    )
                    if _recent_upload_discard_eligible(
                        media,
                        request_user,
                        now=now,
                    )
                    else ""
                ),
            }
        )
    return items


def _staff_display_name(user, language):
    if user is None:
        return "\u0645\u0648\u0638\u0641 \u0633\u0627\u0628\u0642" if language == "ar" else "Former staff"
    return user.get_full_name().strip() or user.get_username()


def _trash_items(media_queryset, language, request_user, *, query_params=None):
    items = []
    for media in media_queryset:
        items.append(
            {
                "media": media,
                "media_type_label": RECORD_MEDIA_TYPE_LABELS[language].get(
                    media.media_type,
                    media.get_media_type_display(),
                ),
                "deleted_by_label": _staff_display_name(media.trashed_by, language),
                "purge_at": media.trashed_at + timedelta(days=30),
                "restore_url": (
                    _dashboard_record_url(
                        "dashboard_media_restore",
                        language,
                        kwargs={
                            "patient_id": media.patient_id,
                            "public_id": media.public_id,
                        },
                        query_params=query_params,
                    )
                    if media.uploaded_by_id == request_user.id
                    else ""
                ),
            }
        )
    return items


def _media_deletion_tombstones(
    patient,
    language,
    *,
    active_media_public_ids,
    selected_filter,
):
    lifecycle_events = list(
        AuditLog.objects.filter(
            app_label="records",
            model_name="RecordMedia",
            metadata__action__in=(
                "record_media_moved_to_trash",
                "record_media_restored_from_trash",
            ),
            metadata__patient_id=patient.pk,
        )
        .select_related("user")
        .order_by("-created_at", "-pk")
    )
    active_public_ids = {str(public_id) for public_id in active_media_public_ids}
    latest_events = {}
    for event in lifecycle_events:
        media_public_id = str(event.metadata.get("media_public_id") or "")
        if media_public_id and media_public_id not in latest_events:
            latest_events[media_public_id] = event

    items = []
    for media_public_id, event in latest_events.items():
        if event.metadata.get("action") != "record_media_moved_to_trash":
            continue
        if media_public_id in active_public_ids:
            continue

        original_folder_id = event.metadata.get("original_folder_id")
        if selected_filter == "unfiled" and original_folder_id != "unfiled":
            continue
        if selected_filter not in ("all", "unfiled") and str(original_folder_id) != selected_filter:
            continue

        chronology = parse_datetime(event.metadata.get("original_uploaded_at") or "")
        if chronology is None:
            chronology = event.created_at
        media_public_id = str(event.metadata.get("media_public_id") or "")
        media_type = event.metadata.get("media_type")
        items.append(
            {
                "kind": "tombstone",
                "event": event,
                "chronology": chronology,
                "media_type_label": DELETION_MEDIA_TYPE_LABELS[language].get(
                    media_type,
                    "\u0648\u0633\u0627\u0626\u0637" if language == "ar" else "Media",
                ),
                "deleted_by_label": _staff_display_name(event.user, language),
            }
        )
    return items


def _private_media_timeline(media_items, tombstones):
    timeline = []
    for item in media_items:
        timeline.append(
            {
                **item,
                "kind": "media",
                "chronology": item["media"].uploaded_at,
            }
        )
    timeline.extend(tombstones)
    return sorted(
        timeline,
        key=lambda item: item["chronology"],
        reverse=True,
    )


def _patient_timeline_items(patient, visits, notes, language):
    timeline = []
    for visit in visits:
        timeline.append(
            {
                "kind": "visit",
                "occurred_at": visit.visit_date,
                "object_id": visit.pk,
                "target_fragment": f"visit-{visit.pk}",
            }
        )
    for note in notes:
        timeline.append(
            {
                "kind": "clinical_note",
                "occurred_at": note.created_at,
                "object_id": note.pk,
                "actor_label": _staff_display_name(note.created_by, language),
                "target_fragment": f"clinical-note-{note.pk}",
            }
        )

    media_events = list(
        AuditLog.objects.filter(
            app_label="records",
            model_name="RecordMedia",
            metadata__patient_id=patient.pk,
            metadata__action__in=(
                "record_media_uploaded",
                "record_media_moved_to_trash",
                "record_media_restored_from_trash",
                "record_media_recent_upload_discarded",
            ),
        )
        .select_related("user")
        .order_by("created_at", "pk")
    )
    discarded_public_ids = {
        str(event.metadata.get("media_public_id") or "")
        for event in media_events
        if event.metadata.get("action") == "record_media_recent_upload_discarded"
    }
    retained_events = [
        event
        for event in media_events
        if str(event.metadata.get("media_public_id") or "") not in discarded_public_ids
    ]
    retained_public_ids = {
        str(event.metadata.get("media_public_id") or "") for event in retained_events
    }
    active_media = {
        str(media.public_id): media
        for media in RecordMedia.objects.filter(
            patient=patient,
            public_id__in=retained_public_ids,
            is_active=True,
            trashed_at__isnull=True,
        )
    }
    event_kind = {
        "record_media_uploaded": "media_uploaded",
        "record_media_moved_to_trash": "media_deleted",
        "record_media_restored_from_trash": "media_restored",
    }
    for event in retained_events:
        action = event.metadata.get("action")
        kind = event_kind.get(action)
        if kind is None:
            continue
        media_public_id = str(event.metadata.get("media_public_id") or "")
        media_type = event.metadata.get("media_type")
        current_media = active_media.get(media_public_id)
        preview_url = ""
        if (
            kind != "media_deleted"
            and current_media is not None
            and current_media.file_exists
        ):
            preview_url = reverse(
                "record_private_media_view",
                kwargs={
                    "patient_id": current_media.patient_id,
                    "public_id": current_media.public_id,
                },
            )
        timeline.append(
            {
                "kind": kind,
                "occurred_at": event.created_at,
                "actor_label": _staff_display_name(event.user, language),
                "media_type": media_type,
                "media_type_label": DELETION_MEDIA_TYPE_LABELS[language].get(
                    media_type,
                    "وسائط" if language == "ar" else "Media",
                ),
                "preview_url": preview_url,
                "media_public_id": media_public_id,
            }
        )

    for event in PatientTimelineEvent.objects.filter(patient=patient).select_related("actor"):
        timeline.append(
            {
                "kind": "public_case_published",
                "occurred_at": event.occurred_at,
                "actor_label": _staff_display_name(event.actor, language),
            }
        )

    return sorted(
        timeline,
        key=lambda item: (item["occurred_at"], item.get("kind", ""), item.get("object_id", 0)),
    )


def _record_media_audit(*, user, action, instance, event, metadata):
    AuditLog.objects.create(
        user=user,
        action=action,
        app_label=instance._meta.app_label,
        model_name=instance.__class__.__name__,
        object_id=str(instance.pk or ""),
        object_repr=f"{instance.__class__.__name__} {instance.pk or ''}".strip(),
        message=event,
        metadata={"action": event, **metadata},
    )


def _public_case_has_publishable_assets(public_case):
    return public_case.has_publishable_media()


def _validated_e164(phone_number):
    candidate = (phone_number or "").strip()
    return candidate if E164_PHONE_RE.fullmatch(candidate) else ""


def _patient_call_uri(phone_e164, phone_raw):
    normalized_phone = _validated_e164(phone_e164)
    if normalized_phone:
        return f"tel:{normalized_phone}"

    raw_phone = (phone_raw or "").strip()
    if not raw_phone or not SAFE_RAW_PHONE_RE.fullmatch(raw_phone):
        return ""
    digits = re.sub(r"[^0-9]", "", raw_phone)
    if not 7 <= len(digits) <= 15:
        return ""
    if raw_phone.startswith("+"):
        sanitized_phone = f"+{digits}"
        if not E164_PHONE_RE.fullmatch(sanitized_phone):
            return ""
    else:
        sanitized_phone = digits
    return f"tel:{sanitized_phone}"


def _patient_whatsapp_url(whatsapp_phone_e164):
    normalized_phone = _validated_e164(whatsapp_phone_e164)
    if not normalized_phone:
        return ""
    return f"https://wa.me/{normalized_phone[1:]}"


@_staff_required
@require_GET
def dashboard_patient_list(request):
    language = _dashboard_language(request)
    alternate_language = "en" if language == "ar" else "ar"
    search_query = (request.GET.get("q") or "").strip()[:PATIENT_SEARCH_MAX_LENGTH]
    total_patient_count = Patient.objects.count()
    patients = Patient.objects.all()
    if search_query:
        patients = patients.filter(
            Q(full_name__icontains=search_query)
            | Q(phone_raw__icontains=search_query)
            | Q(phone_e164__icontains=search_query)
        )
    patients = list(
        patients.annotate(
            visit_count=Count("visit_records", distinct=True),
            note_count=Count("clinical_notes", distinct=True),
            media_count=Count(
                "record_media",
                filter=Q(record_media__trashed_at__isnull=True),
                distinct=True,
            ),
        ).order_by("full_name", "id")
    )
    for row_number, patient in enumerate(patients, start=1):
        patient.contact_dom_key = f"patient-contact-row-{row_number}"
        patient.contact_display_number = (patient.phone or "").strip()
        patient.call_uri = _patient_call_uri(patient.phone_e164, patient.phone_raw)
        patient.whatsapp_url = _patient_whatsapp_url(patient.whatsapp_phone_e164)
        patient.record_url = _patient_record_detail_url(patient, language)

    context = _dashboard_home_context(
        request,
        language=language,
        metrics={},
        schedule_items=[],
    )
    patient_list_url = _dashboard_patient_list_url(language)
    for nav_item in context["dashboard_nav_items"]:
        if nav_item["key"] == "patients":
            nav_item["url"] = patient_list_url
            break
    context.update(
        {
            "page_key": "dashboard_patient_list",
            "page_title": (
                f"المرضى | {context['clinic']['name_ar']}"
                if language == "ar"
                else f"Patients | {context['clinic']['name_en']}"
            ),
            "meta_description": (
                "إدارة ملفات المرضى والوصول إلى السجلات الطبية."
                if language == "ar"
                else "Manage patient files and access medical records."
            ),
            "canonical_url": request.build_absolute_uri(patient_list_url),
            "active_dashboard_nav": "patients",
            "dashboard_patients_url": patient_list_url,
            "dashboard_language_switch_url": _dashboard_patient_list_url(
                alternate_language,
                query=search_query,
            ),
            "patient_search_clear_url": patient_list_url,
            "patient_search_max_length": PATIENT_SEARCH_MAX_LENGTH,
            "patient_search_query": search_query,
            "total_patient_count": total_patient_count,
            "patients": patients,
        }
    )
    return render(request, "dashboard/patient_list.html", context)


def _render_patient_record_detail(
    request,
    patient,
    *,
    folder_create_form=None,
    rename_form=None,
    rename_folder_id=None,
    status=200,
):
    language = _dashboard_language(request)
    visits = list(
        VisitRecord.objects.filter(patient=patient)
        .select_related("appointment", "appointment__doctor", "appointment__visit_type")
        .order_by("-visit_date", "-created_at")
    )
    notes = list(
        ClinicalNote.objects.filter(patient=patient)
        .select_related("visit", "created_by")
        .order_by("-created_at", "-id")
    )
    folders = list(
        RecordMediaFolder.objects.filter(patient=patient)
        .annotate(
            media_count=Count(
                "media_items",
                filter=Q(media_items__trashed_at__isnull=True),
            )
        )
        .order_by("name", "id")
    )
    folder_param = (request.GET.get("folder") or "").strip()
    selected_folder = None
    selected_filter = "all"
    media_queryset = RecordMedia.objects.filter(
        patient=patient,
        trashed_at__isnull=True,
    )
    if folder_param == "unfiled":
        selected_filter = "unfiled"
        media_queryset = media_queryset.filter(folder__isnull=True)
    elif folder_param.isdigit():
        selected_folder = next(
            (folder for folder in folders if folder.pk == int(folder_param)),
            None,
        )
        if selected_folder is not None:
            selected_filter = str(selected_folder.pk)
            media_queryset = media_queryset.filter(folder=selected_folder)

    total_media_count = RecordMedia.objects.filter(
        patient=patient,
        trashed_at__isnull=True,
    ).count()
    unfiled_count = RecordMedia.objects.filter(
        patient=patient,
        folder__isnull=True,
        trashed_at__isnull=True,
    ).count()
    media = list(
        media_queryset.select_related("visit", "folder", "uploaded_by")
        .order_by("-uploaded_at", "-id")
    )
    trashed_media = list(
        RecordMedia.objects.filter(patient=patient, trashed_at__isnull=False)
        .select_related("uploaded_by", "trashed_by")
        .order_by("-trashed_at", "-id")
    )
    selected_query = {"folder": selected_filter} if selected_filter != "all" else {}
    if folder_create_form is None:
        folder_create_form = StaffRecordMediaFolderForm(
            patient=patient,
            created_by=request.user,
            language=language,
        )
    private_media_has_errors = bool(
        (folder_create_form.is_bound and folder_create_form.errors)
        or (rename_form is not None and rename_form.is_bound and rename_form.errors)
    )
    active_media_public_ids = RecordMedia.objects.filter(
        patient=patient,
        trashed_at__isnull=True,
    ).values_list("public_id", flat=True)
    media_items = _media_items(
        media,
        language,
        request.user,
        query_params=selected_query,
    )
    media_tombstones = _media_deletion_tombstones(
        patient,
        language,
        active_media_public_ids=active_media_public_ids,
        selected_filter=selected_filter,
    )
    private_media_timeline = _private_media_timeline(media_items, media_tombstones)
    patient_timeline = _patient_timeline_items(patient, visits, notes, language)
    folder_items = []
    for folder in folders:
        item_rename_form = (
            rename_form
            if rename_folder_id == folder.pk
            else StaffRecordMediaFolderForm(
                patient=patient,
                created_by=request.user,
                language=language,
                instance=folder,
                auto_id=f"id_folder_{folder.pk}_%s",
            )
        )
        folder_items.append(
            {
                "folder": folder,
                "media_count": folder.media_count,
                "is_selected": selected_filter == str(folder.pk),
                "filter_url": _patient_record_detail_url(
                    patient,
                    language,
                    query_params={"folder": folder.pk},
                    fragment="private-media",
                ),
                "rename_url": _dashboard_record_url(
                    "dashboard_media_folder_rename",
                    language,
                    kwargs={"patient_id": patient.pk, "folder_id": folder.pk},
                    query_params=selected_query,
                ),
                "delete_url": _dashboard_record_url(
                    "dashboard_media_folder_delete",
                    language,
                    kwargs={"patient_id": patient.pk, "folder_id": folder.pk},
                    query_params=selected_query,
                ),
                "rename_form": item_rename_form,
                "rename_has_errors": bool(
                    rename_folder_id == folder.pk and item_rename_form.errors
                ),
            }
        )

    return render(
        request,
        "dashboard/patient_record_detail.html",
        _dashboard_record_context(
            request,
            patient=patient,
            route_name="dashboard_patient_record_detail",
            route_kwargs={"patient_id": patient.id},
            query_params=selected_query,
            visit_items=[
                {
                    "visit": visit,
                    "visibility_label": _record_visibility_label(
                        visit.is_visible_to_patient,
                        language,
                    ),
                }
                for visit in visits
            ],
            note_items=[
                {
                    "note": note,
                    "note_type_label": RECORD_NOTE_TYPE_LABELS[language].get(
                        note.note_type,
                        note.get_note_type_display(),
                    ),
                    "visibility_label": _record_visibility_label(
                        note.is_visible_to_patient,
                        language,
                    ),
                }
                for note in notes
            ],
            private_media_timeline=private_media_timeline,
            patient_timeline=patient_timeline,
            patient_timeline_count=len(patient_timeline),
            trash_items=_trash_items(
                trashed_media,
                language,
                request.user,
                query_params=selected_query,
            ),
            trash_count=len(trashed_media),
            visit_count=len(visits),
            note_count=len(notes),
            media_count=total_media_count,
            filtered_media_count=len(media),
            media_folders=folder_items,
            folder_create_form=folder_create_form,
            private_media_has_errors=private_media_has_errors,
            folder_create_url=_dashboard_record_url(
                "dashboard_media_folder_create",
                language,
                kwargs={"patient_id": patient.pk},
                query_params=selected_query,
            ),
            media_all_url=_patient_record_detail_url(
                patient,
                language,
                fragment="private-media",
            ),
            media_unfiled_url=_patient_record_detail_url(
                patient,
                language,
                query_params={"folder": "unfiled"},
                fragment="private-media",
            ),
            unfiled_count=unfiled_count,
            selected_media_filter=selected_filter,
            selected_folder=selected_folder,
            visit_create_url=_dashboard_record_url(
                "dashboard_visit_create",
                language,
                kwargs={"patient_id": patient.id},
            ),
            note_create_url=_dashboard_record_url(
                "dashboard_note_create",
                language,
                kwargs={"patient_id": patient.id},
            ),
            media_create_url=_dashboard_record_url(
                "dashboard_media_create",
                language,
                kwargs={"patient_id": patient.id},
            ),
        ),
        status=status,
    )


@_staff_required
@require_GET
def dashboard_patient_record_detail(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    return _render_patient_record_detail(request, patient)


def _requested_folder_query(request):
    folder_value = (request.GET.get("folder") or "").strip()
    if folder_value == "unfiled" or folder_value.isdigit():
        return {"folder": folder_value}
    return {}


@_staff_required
@require_POST
def dashboard_media_folder_create(request, patient_id):
    language = _dashboard_language(request)
    patient = get_object_or_404(Patient, id=patient_id)
    form = StaffRecordMediaFolderForm(
        request.POST,
        patient=patient,
        created_by=request.user,
        language=language,
    )
    if not form.is_valid():
        return _render_patient_record_detail(
            request,
            patient,
            folder_create_form=form,
            status=400,
        )

    with transaction.atomic():
        folder = form.save(commit=False)
        folder.patient = patient
        folder.created_by = request.user
        folder.save()
        _record_media_audit(
            user=request.user,
            action=AuditLog.Action.CREATE,
            instance=folder,
            event="media_folder_created",
            metadata={"folder_id": folder.pk},
        )
    messages.success(
        request,
        "تم إنشاء المجلد." if language == "ar" else "Folder created.",
    )
    return redirect(
        _patient_record_detail_url(
            patient,
            language,
            query_params={"folder": folder.pk},
            fragment="private-media",
        )
    )


@_staff_required
@require_POST
def dashboard_media_folder_rename(request, patient_id, folder_id):
    language = _dashboard_language(request)
    patient = get_object_or_404(Patient, id=patient_id)
    folder = get_object_or_404(RecordMediaFolder, patient=patient, pk=folder_id)
    form = StaffRecordMediaFolderForm(
        request.POST,
        patient=patient,
        created_by=request.user,
        language=language,
        instance=folder,
        auto_id=f"id_folder_{folder.pk}_%s",
    )
    if not form.is_valid():
        return _render_patient_record_detail(
            request,
            patient,
            rename_form=form,
            rename_folder_id=folder.pk,
            status=400,
        )

    with transaction.atomic():
        folder = form.save()
        _record_media_audit(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=folder,
            event="media_folder_renamed",
            metadata={"folder_id": folder.pk},
        )
    messages.success(
        request,
        "تمت إعادة تسمية المجلد." if language == "ar" else "Folder renamed.",
    )
    return redirect(
        _patient_record_detail_url(
            patient,
            language,
            query_params=_requested_folder_query(request),
            fragment="private-media",
        )
    )


@_staff_required
def dashboard_media_folder_delete(request, patient_id, folder_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    language = _dashboard_language(request)
    patient = get_object_or_404(Patient, id=patient_id)
    folder = get_object_or_404(RecordMediaFolder, patient=patient, pk=folder_id)
    requested_query = _requested_folder_query(request)

    if request.method == "POST":
        deleted_folder_id = folder.pk
        with transaction.atomic():
            _record_media_audit(
                user=request.user,
                action=AuditLog.Action.DELETE,
                instance=folder,
                event="media_folder_deleted",
                metadata={"folder_id": deleted_folder_id},
            )
            folder.delete()
        messages.success(
            request,
            (
                "تم حذف المجلد ونقل ملفاته إلى بدون مجلد."
                if language == "ar"
                else "Folder deleted. Its media is now Unfiled."
            ),
        )
        if requested_query.get("folder") == str(deleted_folder_id):
            requested_query = {"folder": "unfiled"}
        return redirect(
            _patient_record_detail_url(
                patient,
                language,
                query_params=requested_query,
                fragment="private-media",
            )
        )

    return render(
        request,
        "dashboard/media_folder_confirm_delete.html",
        _dashboard_record_context(
            request,
            patient=patient,
            route_name="dashboard_media_folder_delete",
            route_kwargs={"patient_id": patient.pk, "folder_id": folder.pk},
            query_params=requested_query,
            folder=folder,
            folder_media_count=folder.media_items.filter(
                trashed_at__isnull=True,
            ).count(),
            form_title=("حذف المجلد" if language == "ar" else "Delete Folder"),
            delete_url=_dashboard_record_url(
                "dashboard_media_folder_delete",
                language,
                kwargs={"patient_id": patient.pk, "folder_id": folder.pk},
                query_params=requested_query,
            ),
            cancel_url=_patient_record_detail_url(
                patient,
                language,
                query_params=requested_query,
                fragment="private-media",
            ),
        ),
    )


@_staff_required
def dashboard_visit_create(request, patient_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    language = _dashboard_language(request)
    patient = get_object_or_404(Patient, id=patient_id)
    if request.method == "POST":
        form = StaffVisitRecordForm(request.POST, patient=patient, language=language)
        if form.is_valid():
            visit = form.save(commit=False)
            visit.patient = patient
            visit.save()
            messages.success(
                request,
                "تم حفظ الزيارة." if language == "ar" else "Visit saved.",
            )
            return redirect(_patient_record_detail_url(patient, language, fragment="visits"))
        status = 400
    else:
        form = StaffVisitRecordForm(patient=patient, language=language)
        status = 200

    return render(
        request,
        "dashboard/visit_form.html",
        _dashboard_record_context(
            request,
            patient=patient,
            route_name="dashboard_visit_create",
            route_kwargs={"patient_id": patient.id},
            form=form,
            form_title="إضافة زيارة" if language == "ar" else "Add Visit",
            cancel_url=_patient_record_detail_url(patient, language, fragment="visits"),
        ),
        status=status,
    )


@_staff_required
def dashboard_note_create(request, patient_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    language = _dashboard_language(request)
    patient = get_object_or_404(Patient, id=patient_id)
    if request.method == "POST":
        form = StaffClinicalNoteForm(
            request.POST,
            patient=patient,
            created_by=request.user,
            language=language,
        )
        if form.is_valid():
            note = form.save(commit=False)
            note.patient = patient
            note.created_by = request.user
            note.save()
            messages.success(
                request,
                "تم حفظ الملاحظة." if language == "ar" else "Clinical note saved.",
            )
            return redirect(
                _patient_record_detail_url(patient, language, fragment="clinical-notes")
            )
        status = 400
    else:
        form = StaffClinicalNoteForm(
            patient=patient,
            created_by=request.user,
            language=language,
        )
        status = 200

    return render(
        request,
        "dashboard/note_form.html",
        _dashboard_record_context(
            request,
            patient=patient,
            route_name="dashboard_note_create",
            route_kwargs={"patient_id": patient.id},
            form=form,
            form_title="إضافة ملاحظة سريرية" if language == "ar" else "Add Clinical Note",
            cancel_url=_patient_record_detail_url(
                patient,
                language,
                fragment="clinical-notes",
            ),
        ),
        status=status,
    )


@_staff_required
def dashboard_media_create(request, patient_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    language = _dashboard_language(request)
    patient = get_object_or_404(Patient, id=patient_id)
    if request.method == "POST":
        form = StaffRecordMediaCreateForm(
            request.POST,
            request.FILES,
            patient=patient,
            uploaded_by=request.user,
            language=language,
        )
        if form.is_valid():
            media = form.save(commit=False)
            media.patient = patient
            media.uploaded_by = request.user
            with transaction.atomic():
                media.save()
                _record_media_audit(
                    user=request.user,
                    action=AuditLog.Action.CREATE,
                    instance=media,
                    event="record_media_uploaded",
                    metadata={
                        "patient_id": patient.pk,
                        "media_public_id": str(media.public_id),
                        "media_type": media.media_type,
                    },
                )
            messages.success(
                request,
                "تم رفع الملف الخاص." if language == "ar" else "Private media uploaded.",
            )
            return redirect(
                _patient_record_detail_url(patient, language, fragment="private-media")
            )
        status = 400
    else:
        form = StaffRecordMediaCreateForm(
            patient=patient,
            uploaded_by=request.user,
            language=language,
        )
        status = 200

    return render(
        request,
        "dashboard/media_form.html",
        _dashboard_record_context(
            request,
            patient=patient,
            route_name="dashboard_media_create",
            route_kwargs={"patient_id": patient.id},
            form=form,
            form_title="رفع ملف خاص" if language == "ar" else "Upload Private Media",
            cancel_url=_patient_record_detail_url(
                patient,
                language,
                fragment="private-media",
            ),
            is_multipart=True,
        ),
        status=status,
    )


@_staff_required
def dashboard_media_trash(request, patient_id, public_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    language = _dashboard_language(request)
    patient = get_object_or_404(Patient, id=patient_id)
    requested_query = _requested_folder_query(request)
    media = get_object_or_404(
        RecordMedia.objects.select_related("uploaded_by"),
        patient=patient,
        public_id=public_id,
        trashed_at__isnull=True,
    )
    if media.uploaded_by_id is None or media.uploaded_by_id != request.user.id:
        return HttpResponseForbidden("Only the original uploader may move this media to Trash.")

    if request.method == "POST":
        with transaction.atomic():
            media = get_object_or_404(
                RecordMedia.objects.select_for_update(),
                patient=patient,
                public_id=public_id,
                trashed_at__isnull=True,
            )
            if media.uploaded_by_id is None or media.uploaded_by_id != request.user.id:
                return HttpResponseForbidden(
                    "Only the original uploader may move this media to Trash."
                )

            media.trashed_at = timezone.now()
            media.trashed_by = request.user
            media.is_active = False
            media.visibility = RecordMedia.Visibility.PRIVATE_ONLY
            media.save(
                update_fields=[
                    "trashed_at",
                    "trashed_by",
                    "is_active",
                    "visibility",
                ]
            )
            _record_media_audit(
                user=request.user,
                action=AuditLog.Action.DELETE,
                instance=media,
                event="record_media_moved_to_trash",
                metadata={
                    "patient_id": patient.pk,
                    "media_public_id": str(media.public_id),
                    "media_type": media.media_type,
                    "original_uploaded_at": media.uploaded_at.isoformat(),
                    "original_folder_id": media.folder_id or "unfiled",
                },
            )

        messages.success(
            request,
            (
                "\u062a\u0645 \u0646\u0642\u0644 \u0627\u0644\u0648\u0633\u0627\u0626\u0637 \u0625\u0644\u0649 \u0633\u0644\u0629 \u0627\u0644\u0645\u062d\u0630\u0648\u0641\u0627\u062a \u0644\u0645\u062f\u0629 30 \u064a\u0648\u0645\u0627\u064b."
                if language == "ar"
                else "Media moved to Trash for the 30-day retention period."
            ),
        )
        return redirect(
            _patient_record_detail_url(
                patient,
                language,
                query_params=requested_query,
            )
        )

    return render(
        request,
        "dashboard/media_confirm_trash.html",
        _dashboard_record_context(
            request,
            patient=patient,
            route_name="dashboard_media_trash",
            route_kwargs={"patient_id": patient.pk, "public_id": media.public_id},
            media=media,
            media_type_label=RECORD_MEDIA_TYPE_LABELS[language].get(
                media.media_type,
                media.get_media_type_display(),
            ),
            cancel_url=_patient_record_detail_url(
                patient,
                language,
                query_params=requested_query,
                fragment="private-media",
            ),
        ),
    )


@_staff_required
@require_POST
def dashboard_media_discard_recent(request, patient_id, public_id):
    language = _dashboard_language(request)
    patient = get_object_or_404(Patient, id=patient_id)
    requested_query = _requested_folder_query(request)
    storage_deletion_failed = False

    with transaction.atomic():
        media = get_object_or_404(
            RecordMedia.objects.select_for_update(),
            patient=patient,
            public_id=public_id,
        )
        if not _recent_upload_discard_eligible(media, request.user):
            return HttpResponseForbidden("This upload is not eligible for immediate discard.")

        try:
            if media.file and media.file.name:
                media.file.storage.delete(media.file.name)
        except Exception:  # Storage providers expose backend-specific exceptions.
            storage_deletion_failed = True

        if not storage_deletion_failed:
            _record_media_audit(
                user=request.user,
                action=AuditLog.Action.DELETE,
                instance=media,
                event="record_media_recent_upload_discarded",
                metadata={
                    "patient_id": patient.pk,
                    "media_public_id": str(media.public_id),
                    "media_type": media.media_type,
                },
            )
            media.delete()

    if storage_deletion_failed:
        messages.error(
            request,
            (
                "تعذر إلغاء الرفع بأمان. بقي سجل الوسائط دون تغيير."
                if language == "ar"
                else "The upload could not be discarded safely. The media record was preserved."
            ),
        )
    else:
        messages.success(
            request,
            "تم إلغاء الرفع وحذف الملف." if language == "ar" else "Upload discarded.",
        )
    return redirect(
        _patient_record_detail_url(
            patient,
            language,
            query_params=requested_query,
        )
    )


@_staff_required
@require_POST
def dashboard_media_restore(request, patient_id, public_id):
    language = _dashboard_language(request)
    patient = get_object_or_404(Patient, id=patient_id)
    requested_query = _requested_folder_query(request)
    with transaction.atomic():
        media = get_object_or_404(
            RecordMedia.objects.select_for_update(),
            patient=patient,
            public_id=public_id,
            trashed_at__isnull=False,
        )
        if media.uploaded_by_id is None or media.uploaded_by_id != request.user.id:
            return HttpResponseForbidden("Only the original uploader may restore this media.")

        media.trashed_at = None
        media.trashed_by = None
        media.is_active = True
        media.visibility = RecordMedia.Visibility.PRIVATE_ONLY
        media.save(
            update_fields=[
                "trashed_at",
                "trashed_by",
                "is_active",
                "visibility",
            ]
        )
        _record_media_audit(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=media,
            event="record_media_restored_from_trash",
            metadata={
                "patient_id": patient.pk,
                "media_public_id": str(media.public_id),
                "media_type": media.media_type,
            },
        )

    messages.success(
        request,
        "\u062a\u0645\u062a \u0625\u0639\u0627\u062f\u0629 \u0627\u0644\u0648\u0633\u0627\u0626\u0637 \u0643\u0645\u0644\u0641 \u062e\u0627\u0635."
        if language == "ar"
        else "Media restored as private.",
    )
    return redirect(
        _patient_record_detail_url(
            patient,
            language,
            query_params=requested_query,
        )
    )


@_staff_required
def dashboard_media_update(request, patient_id, public_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    language = _dashboard_language(request)
    patient = get_object_or_404(Patient, id=patient_id)
    media = get_object_or_404(
        RecordMedia.objects.select_related(
            "patient",
            "visit",
            "folder",
            "uploaded_by",
        ),
        patient=patient,
        public_id=public_id,
        trashed_at__isnull=True,
    )
    if request.method == "POST":
        original_folder_id = media.folder_id
        form = StaffRecordMediaUpdateForm(
            request.POST,
            instance=media,
            patient=patient,
            language=language,
        )
        if form.is_valid():
            with transaction.atomic():
                media = form.save()
                if media.folder_id != original_folder_id:
                    _record_media_audit(
                        user=request.user,
                        action=AuditLog.Action.UPDATE,
                        instance=media,
                        event="record_media_folder_moved",
                        metadata={
                            "media_public_id": str(media.public_id),
                            "folder_id": media.folder_id,
                        },
                    )
            messages.success(
                request,
                "تم تحديث الملف." if language == "ar" else "Media updated.",
            )
            return redirect(
                _patient_record_detail_url(patient, language, fragment="private-media")
            )
        status = 400
    else:
        form = StaffRecordMediaUpdateForm(
            instance=media,
            patient=patient,
            language=language,
        )
        status = 200

    return render(
        request,
        "dashboard/media_form.html",
        _dashboard_record_context(
            request,
            patient=patient,
            route_name="dashboard_media_update",
            route_kwargs={"patient_id": patient.id, "public_id": media.public_id},
            media=media,
            media_type_label=RECORD_MEDIA_TYPE_LABELS[language].get(
                media.media_type,
                media.get_media_type_display(),
            ),
            form=form,
            form_title="تعديل الملف" if language == "ar" else "Edit Media",
            cancel_url=_patient_record_detail_url(
                patient,
                language,
                fragment="private-media",
            ),
            is_multipart=False,
        ),
        status=status,
    )


def _dashboard_public_case_context(
    request,
    *,
    route_name,
    route_kwargs=None,
    **extra,
):
    language = _dashboard_language(request)
    alternate_language = "en" if language == "ar" else "ar"
    context = _dashboard_home_context(
        request,
        language=language,
        metrics={},
        schedule_items=[],
    )
    current_url = _dashboard_public_case_url(
        language,
        route_name,
        **(route_kwargs or {}),
    )
    context.update(
        {
            "page_key": "dashboard_public_cases",
            "page_title": (
                f"الحالات العامة | {context['clinic']['name_ar']}"
                if language == "ar"
                else f"Public Cases | {context['clinic']['name_en']}"
            ),
            "meta_description": (
                "إدارة الحالات العامة والوسائط الدعائية المستقلة."
                if language == "ar"
                else "Manage standalone public cases and marketing media."
            ),
            "canonical_url": request.build_absolute_uri(current_url),
            "active_dashboard_nav": "public_cases",
            "dashboard_language_switch_url": _dashboard_public_case_url(
                alternate_language,
                route_name,
                **(route_kwargs or {}),
            ),
            "public_case_list_url": _dashboard_public_case_url(language),
        }
    )
    context.update(extra)
    return context


def _public_case_manager_items(language):
    cases = list(
        PublicCase.objects.annotate(
            media_count=Count("media_items"),
            before_count=Count(
                "media_items",
                filter=Q(media_items__role=PublicCaseMedia.Role.BEFORE),
            ),
            after_count=Count(
                "media_items",
                filter=Q(media_items__role=PublicCaseMedia.Role.AFTER),
            ),
            video_count=Count(
                "media_items",
                filter=Q(media_items__role=PublicCaseMedia.Role.VIDEO),
            ),
        ).order_by("-created_at", "-id")
    )
    published_case_ids = {
        int(object_id)
        for object_id in AuditLog.objects.filter(
            app_label="records",
            model_name="PublicCase",
            metadata__action__in=("public_case_published", "public_case_republished"),
        ).values_list("object_id", flat=True)
        if str(object_id).isdigit()
    }
    items = []
    for public_case in cases:
        route_kwargs = {"case_id": public_case.pk}
        was_published = public_case.pk in published_case_ids
        items.append(
            {
                "case": public_case,
                "status_label": (
                    ("منشورة" if language == "ar" else "Published")
                    if public_case.is_published
                    else ("مسودة" if language == "ar" else "Draft")
                ),
                "edit_url": _dashboard_public_case_url(
                    language,
                    "dashboard_public_case_edit",
                    **route_kwargs,
                ),
                "assets_url": _dashboard_public_case_url(
                    language,
                    "dashboard_public_case_assets",
                    **route_kwargs,
                ),
                "publish_url": _dashboard_public_case_url(
                    language,
                    (
                        "dashboard_public_case_republish"
                        if was_published
                        else "dashboard_public_case_publish"
                    ),
                    **route_kwargs,
                ),
                "publish_label": (
                    ("إعادة النشر" if language == "ar" else "Republish")
                    if was_published
                    else ("نشر" if language == "ar" else "Publish")
                ),
                "unpublish_url": _dashboard_public_case_url(
                    language,
                    "dashboard_public_case_unpublish",
                    **route_kwargs,
                ),
                "delete_url": _dashboard_public_case_url(
                    language,
                    "dashboard_public_case_delete",
                    **route_kwargs,
                ),
                "public_preview_url": (
                    reverse(
                        "public_case_detail_en" if language == "en" else "public_case_detail",
                        kwargs={"case_id": public_case.pk},
                    )
                    if (
                        public_case.is_published
                        and public_case.consent_confirmed
                        and _public_case_has_publishable_assets(public_case)
                    )
                    else ""
                ),
            }
        )
    return items


@_staff_required
@require_GET
def dashboard_public_case_list(request):
    language = _dashboard_language(request)
    items = _public_case_manager_items(language)
    return render(
        request,
        "dashboard/public_case_list.html",
        _dashboard_public_case_context(
            request,
            route_name="dashboard_public_case_list",
            public_case_items=items,
            public_case_count=len(items),
            create_url=_dashboard_public_case_url(
                language,
                "dashboard_public_case_create",
            ),
        ),
    )


@_staff_required
def dashboard_public_case_create(request):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    language = _dashboard_language(request)
    if request.method == "POST":
        form = StaffPublicCaseCreateForm(
            request.POST,
            request.FILES,
            uploaded_by=request.user,
            language=language,
        )
        if form.is_valid():
            with transaction.atomic():
                public_case = PublicCase.objects.create(
                    title=form.cleaned_data["case_title"],
                    note=form.cleaned_data.get("short_note", ""),
                    detail_note=form.cleaned_data.get("detail_note", ""),
                    consent_confirmed=bool(form.cleaned_data.get("consent_confirmed")),
                    is_published=False,
                    created_by=request.user,
                )
                media_instances = form.build_media_instances(public_case)
                for media in media_instances:
                    media.save()
                _record_media_audit(
                    user=request.user,
                    action=AuditLog.Action.CREATE,
                    instance=public_case,
                    event="public_case_draft_created",
                    metadata={"media_count": len(media_instances)},
                )
            messages.success(
                request,
                "تم إنشاء مسودة الحالة العامة."
                if language == "ar"
                else "Public case draft created.",
            )
            return redirect(
                _dashboard_public_case_url(
                    language,
                    "dashboard_public_case_assets",
                    case_id=public_case.pk,
                )
            )
        status = 400
    else:
        form = StaffPublicCaseCreateForm(
            uploaded_by=request.user,
            language=language,
        )
        status = 200
    return render(
        request,
        "dashboard/public_case_form.html",
        _dashboard_public_case_context(
            request,
            route_name="dashboard_public_case_create",
            form=form,
            form_title="إنشاء مسودة حالة عامة" if language == "ar" else "Create Public Case Draft",
            submit_label="إنشاء المسودة" if language == "ar" else "Create Draft",
            cancel_url=_dashboard_public_case_url(language),
        ),
        status=status,
    )


@_staff_required
def dashboard_public_case_edit(request, case_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    language = _dashboard_language(request)
    public_case = get_object_or_404(PublicCase, pk=case_id)
    if request.method == "POST":
        form = StaffPublicCaseUpdateForm(
            request.POST,
            instance=public_case,
            language=language,
        )
        if form.is_valid():
            with transaction.atomic():
                locked_case = PublicCase.objects.select_for_update().get(pk=public_case.pk)
                form.instance = locked_case
                public_case = form.save()
                automatically_unpublished = False
                if public_case.is_published and (
                    not public_case.consent_confirmed
                    or not _public_case_has_publishable_assets(public_case)
                ):
                    public_case.is_published = False
                    public_case.save(update_fields=["is_published", "updated_at"])
                    automatically_unpublished = True
                _record_media_audit(
                    user=request.user,
                    action=AuditLog.Action.UPDATE,
                    instance=public_case,
                    event="public_case_metadata_updated",
                    metadata={"automatically_unpublished": automatically_unpublished},
                )
            messages.success(
                request,
                "تم تحديث الحالة العامة." if language == "ar" else "Public case updated.",
            )
            return redirect(_dashboard_public_case_url(language))
        status = 400
    else:
        form = StaffPublicCaseUpdateForm(
            instance=public_case,
            language=language,
        )
        status = 200
    return render(
        request,
        "dashboard/public_case_metadata_form.html",
        _dashboard_public_case_context(
            request,
            route_name="dashboard_public_case_edit",
            route_kwargs={"case_id": public_case.pk},
            public_case=public_case,
            form=form,
            form_title="تعديل الحالة العامة" if language == "ar" else "Edit Public Case",
            submit_label="حفظ التعديلات" if language == "ar" else "Save Changes",
            cancel_url=_dashboard_public_case_url(language),
        ),
        status=status,
    )


def _delete_existing_public_case_video_covers(public_case):
    covers = list(
        PublicCaseMedia.objects.select_for_update().filter(
            public_case=public_case,
            role=PublicCaseMedia.Role.VIDEO_COVER,
        )
    )
    schedule_public_case_media_file_deletion(covers)
    for cover in covers:
        cover.delete()
    return len(covers)


@_staff_required
def dashboard_public_case_add_media(request, case_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    language = _dashboard_language(request)
    public_case = get_object_or_404(PublicCase, pk=case_id)
    kwargs = {
        "uploaded_by": request.user,
        "public_case": public_case,
        "language": language,
    }
    if request.method == "POST":
        form = StaffPublicCaseAddMediaForm(request.POST, request.FILES, **kwargs)
        if form.is_valid():
            with transaction.atomic():
                locked_case = PublicCase.objects.select_for_update().get(pk=public_case.pk)
                media_instances = form.build_media_instances(locked_case)
                replacing_cover = any(
                    media.role == PublicCaseMedia.Role.VIDEO_COVER
                    for media in media_instances
                )
                replaced_cover_count = (
                    _delete_existing_public_case_video_covers(locked_case)
                    if replacing_cover
                    else 0
                )
                for media in media_instances:
                    media.save()
                _record_media_audit(
                    user=request.user,
                    action=AuditLog.Action.CREATE,
                    instance=locked_case,
                    event="public_case_media_added",
                    metadata={
                        "media_count": len(media_instances),
                        "replaced_cover_count": replaced_cover_count,
                    },
                )
            messages.success(
                request,
                "تمت إضافة الوسائط الدعائية."
                if language == "ar"
                else "Marketing media added.",
            )
            return redirect(
                _dashboard_public_case_url(
                    language,
                    "dashboard_public_case_assets",
                    case_id=public_case.pk,
                )
            )
        status = 400
    else:
        form = StaffPublicCaseAddMediaForm(**kwargs)
        status = 200
    return render(
        request,
        "dashboard/public_case_form.html",
        _dashboard_public_case_context(
            request,
            route_name="dashboard_public_case_add_media",
            route_kwargs={"case_id": public_case.pk},
            public_case=public_case,
            form=form,
            form_title="إضافة وسائط دعائية" if language == "ar" else "Add Marketing Media",
            submit_label="إضافة الوسائط" if language == "ar" else "Add Media",
            cancel_url=_dashboard_public_case_url(
                language,
                "dashboard_public_case_assets",
                case_id=public_case.pk,
            ),
        ),
        status=status,
    )


@_staff_required
@require_GET
def dashboard_public_case_assets(request, case_id):
    language = _dashboard_language(request)
    public_case = get_object_or_404(PublicCase, pk=case_id)
    asset_items = []
    for media in public_case.media_items.select_related("uploaded_by").order_by(
        "-uploaded_at",
        "-id",
    ):
        asset_items.append(
            {
                "media": media,
                "media_type_label": (
                    "فيديو قصير"
                    if language == "ar" and media.media_type == PublicCaseMedia.MediaType.SHORT_VIDEO
                    else (
                        "صورة"
                        if language == "ar"
                        else media.get_media_type_display()
                    )
                ),
                "role_label": PUBLIC_CASE_ROLE_LABELS[language].get(
                    media.role,
                    media.get_role_display(),
                ),
                "role_form": StaffPublicCaseMediaRoleForm(
                    instance=media,
                    language=language,
                    auto_id=f"id_asset_{media.pk}_%s",
                ),
                "role_url": _dashboard_public_case_url(
                    language,
                    "dashboard_public_case_asset_role",
                    case_id=public_case.pk,
                    public_id=media.public_id,
                ),
                "preview_url": _dashboard_public_case_url(
                    language,
                    "dashboard_public_case_asset_preview",
                    case_id=public_case.pk,
                    public_id=media.public_id,
                ),
                "download_url": _dashboard_public_case_url(
                    language,
                    "dashboard_public_case_asset_download",
                    case_id=public_case.pk,
                    public_id=media.public_id,
                ),
                "remove_url": _dashboard_public_case_url(
                    language,
                    "dashboard_public_case_asset_remove",
                    case_id=public_case.pk,
                    public_id=media.public_id,
                ),
            }
        )
    return render(
        request,
        "dashboard/public_case_assets.html",
        _dashboard_public_case_context(
            request,
            route_name="dashboard_public_case_assets",
            route_kwargs={"case_id": public_case.pk},
            public_case=public_case,
            asset_items=asset_items,
            add_media_url=_dashboard_public_case_url(
                language,
                "dashboard_public_case_add_media",
                case_id=public_case.pk,
            ),
            cancel_url=_dashboard_public_case_url(language),
        ),
    )


@_staff_required
@require_POST
def dashboard_public_case_asset_role(request, case_id, public_id):
    language = _dashboard_language(request)
    with transaction.atomic():
        public_case = get_object_or_404(
            PublicCase.objects.select_for_update(),
            pk=case_id,
        )
        media = get_object_or_404(
            PublicCaseMedia.objects.select_for_update(),
            public_case=public_case,
            public_id=public_id,
        )
        form = StaffPublicCaseMediaRoleForm(
            request.POST,
            instance=media,
            language=language,
        )
        if form.is_valid():
            form.save()
            if public_case.is_published and (
                not public_case.consent_confirmed
                or not _public_case_has_publishable_assets(public_case)
            ):
                public_case.is_published = False
                public_case.save(update_fields=["is_published", "updated_at"])
            form_is_valid = True
        else:
            form_is_valid = False
    if form_is_valid:
        messages.success(
            request,
            "تم تحديث بيانات الوسائط." if language == "ar" else "Media settings updated.",
        )
    else:
        messages.error(
            request,
            "الدور المحدد لا يطابق نوع الملف."
            if language == "ar"
            else "The selected role does not match the media type.",
        )
    return redirect(
        _dashboard_public_case_url(
            language,
            "dashboard_public_case_assets",
            case_id=case_id,
        )
    )


def _public_case_staff_file_response(media, *, as_attachment):
    if not media.file_exists:
        raise Http404("Media unavailable.")
    try:
        response = FileResponse(
            media.file.open("rb"),
            as_attachment=as_attachment,
            filename=(media.download_filename if as_attachment else media.presentation_filename),
            content_type=media.content_type or "application/octet-stream",
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise Http404("Media unavailable.") from exc
    response["X-Content-Type-Options"] = "nosniff"
    return response


@_staff_required
@require_GET
def dashboard_public_case_asset_preview(request, case_id, public_id):
    media = get_object_or_404(
        PublicCaseMedia,
        public_case_id=case_id,
        public_id=public_id,
    )
    return _public_case_staff_file_response(media, as_attachment=False)


@_staff_required
@require_GET
def dashboard_public_case_asset_download(request, case_id, public_id):
    media = get_object_or_404(
        PublicCaseMedia,
        public_case_id=case_id,
        public_id=public_id,
    )
    return _public_case_staff_file_response(media, as_attachment=True)


@_staff_required
@require_POST
def dashboard_public_case_asset_remove(request, case_id, public_id):
    language = _dashboard_language(request)
    with transaction.atomic():
        media = get_object_or_404(
            PublicCaseMedia.objects.select_for_update(),
            public_case_id=case_id,
            public_id=public_id,
        )
        case = PublicCase.objects.select_for_update().get(pk=media.public_case_id)
        schedule_public_case_media_file_deletion([media])
        _record_media_audit(
            user=request.user,
            action=AuditLog.Action.DELETE,
            instance=case,
            event="public_case_media_deleted",
            metadata={"media_public_id": str(media.public_id)},
        )
        media.delete()
        if case.is_published and not _public_case_has_publishable_assets(case):
            case.is_published = False
            case.save(update_fields=["is_published", "updated_at"])
    messages.success(
        request,
        "تم حذف الوسائط الدعائية نهائيًا."
        if language == "ar"
        else "Marketing media permanently deleted.",
    )
    return redirect(
        _dashboard_public_case_url(
            language,
            "dashboard_public_case_assets",
            case_id=case_id,
        )
    )


def _publish_public_case(request, case_id, *, republish):
    language = _dashboard_language(request)
    public_case = get_object_or_404(PublicCase, pk=case_id)
    if request.method == "POST":
        form = StaffPublicCasePublishForm(request.POST, language=language)
        if form.is_valid():
            with transaction.atomic():
                public_case = PublicCase.objects.select_for_update().get(pk=public_case.pk)
                if not public_case.consent_confirmed or not _public_case_has_publishable_assets(
                    public_case
                ):
                    messages.error(
                        request,
                        (
                            "يتطلب النشر موافقة مؤكدة ووسائط دعائية صالحة واحدة على الأقل."
                            if language == "ar"
                            else "Publishing requires confirmed consent and at least one valid marketing asset."
                        ),
                    )
                    return redirect(_dashboard_public_case_url(language))
                occurred_at = timezone.now()
                public_case.is_published = True
                public_case.save(update_fields=["is_published", "updated_at"])
                timeline_patient = form.cleaned_data.get("patient_timeline_patient")
                if timeline_patient is not None:
                    PatientTimelineEvent.objects.create(
                        patient=timeline_patient,
                        event_type=PatientTimelineEvent.EventType.PUBLIC_CASE_PUBLISHED,
                        actor=request.user,
                        occurred_at=occurred_at,
                    )
                _record_media_audit(
                    user=request.user,
                    action=AuditLog.Action.UPDATE,
                    instance=public_case,
                    event=("public_case_republished" if republish else "public_case_published"),
                    metadata={"timeline_note_added": timeline_patient is not None},
                )
            messages.success(
                request,
                "تمت إعادة نشر الحالة." if language == "ar" and republish else (
                    "تم نشر الحالة." if language == "ar" else (
                        "Case republished." if republish else "Case published."
                    )
                ),
            )
            return redirect(_dashboard_public_case_url(language))
        status = 400
    else:
        form = StaffPublicCasePublishForm(language=language)
        status = 200
    return render(
        request,
        "dashboard/public_case_publish.html",
        _dashboard_public_case_context(
            request,
            route_name=(
                "dashboard_public_case_republish"
                if republish
                else "dashboard_public_case_publish"
            ),
            route_kwargs={"case_id": public_case.pk},
            public_case=public_case,
            form=form,
            republish=republish,
            cancel_url=_dashboard_public_case_url(language),
        ),
        status=status,
    )


@_staff_required
def dashboard_public_case_publish(request, case_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    return _publish_public_case(request, case_id, republish=False)


@_staff_required
def dashboard_public_case_republish(request, case_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    return _publish_public_case(request, case_id, republish=True)


@_staff_required
def dashboard_public_case_unpublish(request, case_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    language = _dashboard_language(request)
    public_case = get_object_or_404(PublicCase, pk=case_id)
    if request.method == "POST":
        with transaction.atomic():
            public_case = PublicCase.objects.select_for_update().get(pk=public_case.pk)
            public_case.is_published = False
            public_case.save(update_fields=["is_published", "updated_at"])
            _record_media_audit(
                user=request.user,
                action=AuditLog.Action.UPDATE,
                instance=public_case,
                event="public_case_unpublished",
                metadata={},
            )
        messages.success(
            request,
            "تم إخفاء الحالة من الموقع العام."
            if language == "ar"
            else "Case removed from the public website.",
        )
        return redirect(_dashboard_public_case_url(language))
    return render(
        request,
        "dashboard/public_case_confirm_unpublish.html",
        _dashboard_public_case_context(
            request,
            route_name="dashboard_public_case_unpublish",
            route_kwargs={"case_id": public_case.pk},
            public_case=public_case,
            cancel_url=_dashboard_public_case_url(language),
        ),
    )


@_staff_required
def dashboard_public_case_delete(request, case_id):
    not_allowed = _method_allowed(request, ["GET", "POST"])
    if not_allowed:
        return not_allowed
    language = _dashboard_language(request)
    public_case = get_object_or_404(PublicCase, pk=case_id)
    if request.method == "POST":
        with transaction.atomic():
            public_case = PublicCase.objects.select_for_update().get(pk=public_case.pk)
            media_items = list(public_case.media_items.select_for_update())
            media_count = len(media_items)
            schedule_public_case_media_file_deletion(media_items)
            _record_media_audit(
                user=request.user,
                action=AuditLog.Action.DELETE,
                instance=public_case,
                event="public_case_permanently_deleted",
                metadata={"media_count": media_count},
            )
            public_case.delete()
        return redirect(_dashboard_public_case_url(language))
    return render(
        request,
        "dashboard/public_case_confirm_delete.html",
        _dashboard_public_case_context(
            request,
            route_name="dashboard_public_case_delete",
            route_kwargs={"case_id": public_case.pk},
            public_case=public_case,
            cancel_url=_dashboard_public_case_url(language),
        ),
    )
