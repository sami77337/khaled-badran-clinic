from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.booking.models import Appointment
from apps.booking.phone import normalize_phone
from apps.booking.selectors import get_active_doctor, get_active_visit_type, get_active_visit_types
from apps.clinic.models import ClosedDay, DoctorSchedule
from apps.core.models import SystemSetting
from apps.patients.models import Patient


DEFAULT_BOOKING_ENABLED = True
DEFAULT_BOOKING_MIN_LEAD_MINUTES = 180
DEFAULT_BOOKING_MAX_DAYS_AHEAD = 30
DEFAULT_BOOKING_SLOT_INTERVAL_MINUTES = 15
DEFAULT_APPOINTMENT_REMINDER_OFFSET_MINUTES = 180

BLOCKING_APPOINTMENT_STATUSES = [
    Appointment.Status.CONFIRMED,
    Appointment.Status.ARRIVED,
    Appointment.Status.COMPLETED,
    Appointment.Status.NO_SHOW,
]


@dataclass(frozen=True)
class BookingSettings:
    enabled: bool = DEFAULT_BOOKING_ENABLED
    min_lead_minutes: int = DEFAULT_BOOKING_MIN_LEAD_MINUTES
    max_days_ahead: int = DEFAULT_BOOKING_MAX_DAYS_AHEAD
    slot_interval_minutes: int = DEFAULT_BOOKING_SLOT_INTERVAL_MINUTES
    reminder_offset_minutes: int = DEFAULT_APPOINTMENT_REMINDER_OFFSET_MINUTES


@dataclass(frozen=True)
class BookingSlot:
    starts_at: datetime
    ends_at: datetime

    @property
    def value(self):
        return self.starts_at.isoformat()

    @property
    def local_date(self):
        return timezone.localtime(self.starts_at).date()

    @property
    def local_time(self):
        return timezone.localtime(self.starts_at).time()


def get_bool_setting(key, default):
    setting = SystemSetting.objects.filter(key=key).first()
    if setting is None:
        return default
    return setting.value.strip().lower() in {"1", "true", "yes", "on"}


def get_int_setting(key, default, minimum=0):
    setting = SystemSetting.objects.filter(key=key).first()
    if setting is None:
        return default
    try:
        value = int(setting.value)
    except (TypeError, ValueError):
        return default
    return max(value, minimum)


def get_booking_settings():
    return BookingSettings(
        enabled=get_bool_setting(SystemSetting.BOOKING_ENABLED, DEFAULT_BOOKING_ENABLED),
        min_lead_minutes=get_int_setting(
            SystemSetting.BOOKING_MIN_LEAD_MINUTES,
            DEFAULT_BOOKING_MIN_LEAD_MINUTES,
            minimum=0,
        ),
        max_days_ahead=get_int_setting(
            SystemSetting.BOOKING_MAX_DAYS_AHEAD,
            DEFAULT_BOOKING_MAX_DAYS_AHEAD,
            minimum=1,
        ),
        slot_interval_minutes=get_int_setting(
            SystemSetting.BOOKING_SLOT_INTERVAL_MINUTES,
            DEFAULT_BOOKING_SLOT_INTERVAL_MINUTES,
            minimum=1,
        ),
        reminder_offset_minutes=get_int_setting(
            SystemSetting.APPOINTMENT_REMINDER_OFFSET_MINUTES,
            DEFAULT_APPOINTMENT_REMINDER_OFFSET_MINUTES,
            minimum=0,
        ),
    )


def parse_slot_datetime(value):
    if isinstance(value, datetime):
        starts_at = value
    else:
        starts_at = parse_datetime(str(value or ""))

    if starts_at is None:
        raise ValidationError("Select a valid appointment time.")
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at, timezone.get_current_timezone())
    return starts_at.astimezone(timezone.get_current_timezone())


def is_closed_day(doctor, day):
    return ClosedDay.objects.filter(is_active=True, date=day).filter(
        Q(doctor=doctor) | Q(doctor__isnull=True)
    ).exists()


def overlaps_existing_appointment(doctor, starts_at, ends_at):
    return Appointment.objects.filter(
        doctor=doctor,
        status__in=BLOCKING_APPOINTMENT_STATUSES,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    ).exists()


def _combine_local(day, slot_time):
    combined = datetime.combine(day, slot_time)
    return timezone.make_aware(combined, timezone.get_current_timezone())


def _iter_schedule_slots(schedule, day, visit_type, settings, now):
    starts_at = _combine_local(day, schedule.start_time)
    schedule_ends_at = _combine_local(day, schedule.end_time)
    duration = timedelta(minutes=visit_type.duration_minutes)
    interval = timedelta(minutes=settings.slot_interval_minutes)
    min_start = now + timedelta(minutes=settings.min_lead_minutes)

    while starts_at + duration <= schedule_ends_at:
        ends_at = starts_at + duration
        if starts_at > now and starts_at >= min_start:
            yield BookingSlot(starts_at=starts_at, ends_at=ends_at)
        starts_at += interval


def generate_available_slots(visit_type, target_date=None, now=None, settings=None, doctor=None):
    settings = settings or get_booking_settings()
    if not settings.enabled or visit_type is None or not visit_type.is_active:
        return []

    doctor = doctor or visit_type.doctor or get_active_doctor()
    if doctor is None or not doctor.is_active:
        return []

    now = now or timezone.localtime(timezone.now())
    today = timezone.localdate(now)
    max_date = today + timedelta(days=settings.max_days_ahead)

    if target_date is not None:
        if isinstance(target_date, str):
            target_date = date.fromisoformat(target_date)
        if target_date < today or target_date > max_date:
            return []
        dates = [target_date]
    else:
        dates = [today + timedelta(days=offset) for offset in range(settings.max_days_ahead + 1)]

    slots = []
    for day in dates:
        if is_closed_day(doctor, day):
            continue

        schedules = DoctorSchedule.objects.filter(
            doctor=doctor,
            weekday=day.weekday(),
            is_active=True,
        ).order_by("start_time")

        for schedule in schedules:
            for slot in _iter_schedule_slots(schedule, day, visit_type, settings, now):
                if not overlaps_existing_appointment(doctor, slot.starts_at, slot.ends_at):
                    slots.append(slot)

    return slots


def is_slot_available(visit_type, starts_at, settings=None, doctor=None, now=None):
    settings = settings or get_booking_settings()
    starts_at = parse_slot_datetime(starts_at)
    slots = generate_available_slots(
        visit_type=visit_type,
        target_date=timezone.localtime(starts_at).date(),
        now=now,
        settings=settings,
        doctor=doctor,
    )
    return any(slot.starts_at == starts_at for slot in slots)


def validate_public_booking_request(visit_type, starts_at, settings=None, doctor=None, now=None):
    settings = settings or get_booking_settings()
    if not settings.enabled:
        raise ValidationError("Online booking is currently unavailable.")

    doctor = doctor or (visit_type.doctor if visit_type else None) or get_active_doctor()
    if doctor is None or not doctor.is_active:
        raise ValidationError("No active doctor is available for public booking.")

    if visit_type is None or not visit_type.is_active:
        raise ValidationError("Select an active visit type.")

    starts_at = parse_slot_datetime(starts_at)
    ends_at = starts_at + timedelta(minutes=visit_type.duration_minutes)
    if ends_at <= starts_at:
        raise ValidationError("Appointment end time must be after start time.")

    if not is_slot_available(visit_type, starts_at, settings=settings, doctor=doctor, now=now):
        raise ValidationError("This appointment time is no longer available.")

    return doctor, starts_at, ends_at


@transaction.atomic
def create_public_appointment(
    *,
    full_name,
    phone_raw,
    visit_type_id,
    starts_at,
    booking_note="",
    whatsapp_phone_raw="",
):
    settings = get_booking_settings()
    doctor = get_active_doctor()
    visit_type = get_active_visit_type(visit_type_id, doctor=doctor)
    doctor, starts_at, ends_at = validate_public_booking_request(
        visit_type=visit_type,
        starts_at=starts_at,
        settings=settings,
        doctor=doctor,
    )

    normalized_phone = normalize_phone(phone_raw)
    normalized_whatsapp = normalize_phone(whatsapp_phone_raw) if whatsapp_phone_raw else normalized_phone

    patient = Patient.objects.filter(phone_e164=normalized_phone).order_by("id").first()
    if patient is None:
        patient = Patient.objects.create(
            full_name=full_name.strip(),
            phone_raw=phone_raw.strip(),
            phone_e164=normalized_phone,
            whatsapp_phone_raw=(whatsapp_phone_raw or phone_raw).strip(),
            whatsapp_phone_e164=normalized_whatsapp,
        )
    else:
        changed_fields = []
        updates = {
            "phone_raw": phone_raw.strip(),
            "whatsapp_phone_raw": (whatsapp_phone_raw or phone_raw).strip(),
            "whatsapp_phone_e164": normalized_whatsapp,
        }
        for field, value in updates.items():
            if getattr(patient, field) != value:
                setattr(patient, field, value)
                changed_fields.append(field)
        if changed_fields:
            patient.save(update_fields=changed_fields)

    appointment = Appointment(
        doctor=doctor,
        patient=patient,
        visit_type=visit_type,
        starts_at=starts_at,
        ends_at=ends_at,
        reminder_offset=timedelta(minutes=settings.reminder_offset_minutes),
        booking_note=(booking_note or "").strip(),
    )
    appointment.full_clean()
    appointment.save()
    return appointment


def group_slots_by_date(slots):
    grouped = {}
    for slot in slots:
        grouped.setdefault(slot.local_date, []).append(slot)
    return [{"date": day, "slots": grouped[day]} for day in sorted(grouped)]


def public_visit_types():
    doctor = get_active_doctor()
    return get_active_visit_types(doctor=doctor)
