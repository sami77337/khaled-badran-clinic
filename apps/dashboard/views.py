from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.booking.models import Appointment
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
    },
    "en": {
        Appointment.Status.CONFIRMED: "Confirmed",
        Appointment.Status.ARRIVED: "Arrived",
        Appointment.Status.COMPLETED: "Completed",
        Appointment.Status.NO_SHOW: "No-show",
    },
}


def _dashboard_language(request):
    return "en" if request.GET.get("lang") == "en" else "ar"


def _dashboard_home_url(language):
    url = reverse("dashboard_home")
    return f"{url}?lang=en" if language == "en" else url


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
        },
        "en": {
            "overview": "Overview",
            "appointments": "Appointments",
            "patients": "Patients",
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
