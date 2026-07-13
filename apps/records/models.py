from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class VisitRecord(models.Model):
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="visit_records",
    )
    appointment = models.ForeignKey(
        "booking.Appointment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visit_records",
    )
    visit_date = models.DateTimeField(default=timezone.now, db_index=True)
    visit_reason = models.TextField(blank=True)
    doctor_notes = models.TextField(
        blank=True,
        help_text="Manual doctor/staff notes only. Do not store generated medical content.",
    )
    diagnosis_plan = models.TextField(
        blank=True,
        help_text="Manual diagnosis/plan written by doctor/staff only.",
    )
    instructions = models.TextField(
        blank=True,
        help_text="Manual instructions written by doctor/staff only.",
    )
    follow_up_notes = models.TextField(
        blank=True,
        help_text="Manual follow-up notes written by doctor/staff only.",
    )
    is_visible_to_patient = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-visit_date", "-created_at"]
        indexes = [
            models.Index(fields=["patient", "visit_date"]),
            models.Index(fields=["patient", "is_visible_to_patient"]),
        ]

    def __str__(self):
        return f"{self.patient} visit on {self.visit_date:%Y-%m-%d}"

    def clean(self):
        if (
            self.appointment_id
            and self.patient_id
            and self.appointment.patient_id != self.patient_id
        ):
            raise ValidationError({"appointment": "Appointment must belong to the selected patient."})

    def get_patient_visible_content(self):
        if not self.is_visible_to_patient:
            return {}
        return {
            "visit_date": self.visit_date,
            "visit_reason": self.visit_reason,
            "doctor_notes": self.doctor_notes,
            "diagnosis_plan": self.diagnosis_plan,
            "instructions": self.instructions,
            "follow_up_notes": self.follow_up_notes,
        }


class ClinicalNote(models.Model):
    class NoteType(models.TextChoices):
        DOCTOR_NOTE = "doctor_note", "Doctor note"
        STAFF_NOTE = "staff_note", "Staff note"
        FOLLOW_UP = "follow_up", "Follow-up"

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="clinical_notes",
    )
    visit = models.ForeignKey(
        VisitRecord,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="clinical_notes",
    )
    note_type = models.CharField(
        max_length=30,
        choices=NoteType.choices,
        default=NoteType.DOCTOR_NOTE,
        db_index=True,
    )
    title = models.CharField(max_length=255, blank=True)
    body = models.TextField(
        help_text="Manual doctor/staff note only. Do not store generated medical content.",
    )
    is_visible_to_patient = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clinical_notes_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["patient", "created_at"]),
            models.Index(fields=["patient", "is_visible_to_patient"]),
        ]

    def __str__(self):
        return self.title or f"{self.get_note_type_display()} for {self.patient}"

    def clean(self):
        if self.visit_id and self.patient_id and self.visit.patient_id != self.patient_id:
            raise ValidationError({"visit": "Visit must belong to the selected patient."})

    def get_patient_visible_content(self):
        if not self.is_visible_to_patient:
            return {}
        return {
            "note_type": self.note_type,
            "title": self.title,
            "body": self.body,
            "created_at": self.created_at,
        }


class RecordMedia(models.Model):
    class MediaType(models.TextChoices):
        IMAGE = "image", "Image"
        SHORT_VIDEO = "short_video", "Short video"

    class Visibility(models.TextChoices):
        PRIVATE_ONLY = "private_only", "Private only"
        VISIBLE_TO_PATIENT = "visible_to_patient", "Visible to patient"
        APPROVED_PUBLIC_CASE = "approved_public_case", "Approved public case"

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="record_media",
    )
    visit = models.ForeignKey(
        VisitRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_items",
    )
    media_type = models.CharField(max_length=20, choices=MediaType.choices)
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    visibility = models.CharField(
        max_length=30,
        choices=Visibility.choices,
        default=Visibility.PRIVATE_ONLY,
        db_index=True,
    )
    consent_confirmed = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["patient", "uploaded_at"]),
            models.Index(fields=["patient", "visibility"]),
            models.Index(fields=["visibility", "consent_confirmed", "is_active"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(visibility="approved_public_case")
                    | models.Q(consent_confirmed=True)
                ),
                name="record_media_public_case_requires_consent",
            ),
        ]

    def __str__(self):
        return self.title or f"{self.get_media_type_display()} for {self.patient}"

    @property
    def is_visible_to_patient(self):
        return self.visibility == self.Visibility.VISIBLE_TO_PATIENT

    @property
    def is_public_case_approved(self):
        return (
            self.visibility == self.Visibility.APPROVED_PUBLIC_CASE
            and self.consent_confirmed
            and self.is_active
        )

    def clean(self):
        if self.visit_id and self.patient_id and self.visit.patient_id != self.patient_id:
            raise ValidationError({"visit": "Visit must belong to the selected patient."})
        if self.visibility == self.Visibility.APPROVED_PUBLIC_CASE and not self.consent_confirmed:
            raise ValidationError(
                {"consent_confirmed": "Public case media requires confirmed consent."}
            )

    def get_patient_visible_metadata(self):
        if not self.is_active or not self.is_visible_to_patient:
            return {}
        return {
            "media_type": self.media_type,
            "title": self.title,
            "description": self.description,
            "uploaded_at": self.uploaded_at,
        }

    def get_public_case_metadata(self):
        if not self.is_public_case_approved:
            return {}
        return {
            "media_type": self.media_type,
            "title": self.title,
            "description": self.description,
        }
