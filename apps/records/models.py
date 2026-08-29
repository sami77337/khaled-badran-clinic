import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .storage import private_record_media_storage, private_record_media_upload_path


IMAGE_MAX_BYTES = 10 * 1024 * 1024
SHORT_VIDEO_MAX_BYTES = 50 * 1024 * 1024

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_SHORT_VIDEO_EXTENSIONS = {".mp4"}
ALLOWED_SHORT_VIDEO_CONTENT_TYPES = {"video/mp4"}


def _safe_basename(filename):
    return PurePosixPath(str(filename or "").replace("\\", "/")).name[:255]


def _filename_extension(filename):
    return PurePosixPath(str(filename or "").replace("\\", "/")).suffix.lower()


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


class RecordMediaFolder(models.Model):
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="media_folders",
    )
    name = models.CharField(max_length=120)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="record_media_folders_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name

    def clean(self):
        self.name = (self.name or "").strip()
        if not self.name:
            raise ValidationError({"name": "Folder name is required."})
        if self.patient_id:
            duplicates = RecordMediaFolder.objects.filter(
                patient_id=self.patient_id,
                name__iexact=self.name,
            )
            if self.pk:
                duplicates = duplicates.exclude(pk=self.pk)
            if duplicates.exists():
                raise ValidationError(
                    {"name": "A folder with this name already exists for this patient."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class RecordMedia(models.Model):
    class MediaType(models.TextChoices):
        IMAGE = "image", "Image"
        SHORT_VIDEO = "short_video", "Short video"

    class Visibility(models.TextChoices):
        PRIVATE_ONLY = "private_only", "Private only"
        VISIBLE_TO_PATIENT = "visible_to_patient", "Visible to patient"
        APPROVED_PUBLIC_CASE = "approved_public_case", "Approved public case"

    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
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
    folder = models.ForeignKey(
        RecordMediaFolder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_items",
    )
    media_type = models.CharField(max_length=20, choices=MediaType.choices)
    file = models.FileField(
        upload_to=private_record_media_upload_path,
        storage=private_record_media_storage,
        default="",
    )
    original_filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=100, blank=True)
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
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="record_media_uploaded",
    )
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
    def download_filename(self):
        original_filename = _safe_basename(self.original_filename)
        if original_filename:
            return original_filename
        extension = _filename_extension(self.file.name)
        return f"record-media-{self.public_id}{extension}"

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

    def _uploaded_file(self):
        return getattr(self.file, "_file", None)

    def _file_size(self):
        uploaded_file = self._uploaded_file()
        if uploaded_file is not None and hasattr(uploaded_file, "size"):
            return uploaded_file.size
        if self.file_size:
            return self.file_size
        if self.file:
            try:
                return self.file.size
            except (FileNotFoundError, OSError, ValueError):
                return 0
        return 0

    def _file_content_type(self):
        uploaded_file = self._uploaded_file()
        if uploaded_file is not None:
            return (getattr(uploaded_file, "content_type", "") or "").strip()
        return self.content_type.strip()

    def populate_file_metadata(self):
        if not self.file:
            return

        uploaded_file = self._uploaded_file()
        if uploaded_file is not None or not self.original_filename:
            source_name = getattr(uploaded_file, "name", "") or self.file.name
            self.original_filename = _safe_basename(source_name)

        self.file_size = self._file_size()
        content_type = self._file_content_type()
        if content_type:
            self.content_type = content_type[:100]

    def _media_policy(self):
        if self.media_type == self.MediaType.IMAGE:
            return {
                "extensions": ALLOWED_IMAGE_EXTENSIONS,
                "content_types": ALLOWED_IMAGE_CONTENT_TYPES,
                "max_bytes": IMAGE_MAX_BYTES,
                "label": "image",
            }
        if self.media_type == self.MediaType.SHORT_VIDEO:
            return {
                "extensions": ALLOWED_SHORT_VIDEO_EXTENSIONS,
                "content_types": ALLOWED_SHORT_VIDEO_CONTENT_TYPES,
                "max_bytes": SHORT_VIDEO_MAX_BYTES,
                "label": "short video",
            }
        return None

    def _validate_private_file(self):
        if not self.file:
            raise ValidationError({"file": "Private media file is required."})

        policy = self._media_policy()
        if policy is None:
            return

        extension = _filename_extension(self.original_filename or self.file.name)
        content_type = self.content_type.strip()
        errors = {}

        if extension not in policy["extensions"]:
            errors["file"] = f"Unsupported {policy['label']} file extension."
        if content_type not in policy["content_types"]:
            errors["content_type"] = f"Unsupported {policy['label']} content type."
        if self.file_size > policy["max_bytes"]:
            errors["file_size"] = f"{policy['label'].title()} file exceeds the allowed size."

        if errors:
            raise ValidationError(errors)

    def clean(self):
        self.populate_file_metadata()
        self._validate_private_file()

        if self.visit_id and self.patient_id and self.visit.patient_id != self.patient_id:
            raise ValidationError({"visit": "Visit must belong to the selected patient."})
        if self.folder_id and self.patient_id and self.folder.patient_id != self.patient_id:
            raise ValidationError({"folder": "Folder must belong to the selected patient."})
        if self.visibility == self.Visibility.APPROVED_PUBLIC_CASE and not self.consent_confirmed:
            raise ValidationError(
                {"consent_confirmed": "Public case media requires confirmed consent."}
            )

    def save(self, *args, **kwargs):
        self.populate_file_metadata()
        self.full_clean()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            update_fields.update({"original_filename", "file_size", "content_type", "updated_at"})
            kwargs["update_fields"] = update_fields
        return super().save(*args, **kwargs)

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
