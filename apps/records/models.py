import re
import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .storage import (
    private_record_media_storage,
    private_record_media_upload_path,
    public_case_media_storage,
    public_case_media_upload_path,
)


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


def _uploaded_file(instance):
    return getattr(instance.file, "_file", None)


def _file_size(instance):
    uploaded_file = _uploaded_file(instance)
    if uploaded_file is not None and hasattr(uploaded_file, "size"):
        return uploaded_file.size
    if instance.file_size:
        return instance.file_size
    if instance.file:
        try:
            return instance.file.size
        except (FileNotFoundError, OSError, ValueError):
            return 0
    return 0


def _file_content_type(instance):
    uploaded_file = _uploaded_file(instance)
    if uploaded_file is not None:
        return (getattr(uploaded_file, "content_type", "") or "").strip()
    return instance.content_type.strip()


def _populate_file_metadata(instance):
    if not instance.file:
        return

    uploaded_file = _uploaded_file(instance)
    if uploaded_file is not None or not instance.original_filename:
        source_name = getattr(uploaded_file, "name", "") or instance.file.name
        instance.original_filename = _safe_basename(source_name)

    instance.file_size = _file_size(instance)
    content_type = _file_content_type(instance)
    if content_type:
        instance.content_type = content_type[:100]


def _stored_file_exists(field_file):
    if not field_file or not field_file.name:
        return False
    try:
        return field_file.storage.exists(field_file.name)
    except Exception:  # Storage backends expose provider-specific availability errors.
        return False


def _media_policy(media_type):
    if media_type == "image":
        return {
            "extensions": ALLOWED_IMAGE_EXTENSIONS,
            "content_types": ALLOWED_IMAGE_CONTENT_TYPES,
            "max_bytes": IMAGE_MAX_BYTES,
            "label": "image",
        }
    if media_type == "short_video":
        return {
            "extensions": ALLOWED_SHORT_VIDEO_EXTENSIONS,
            "content_types": ALLOWED_SHORT_VIDEO_CONTENT_TYPES,
            "max_bytes": SHORT_VIDEO_MAX_BYTES,
            "label": "short video",
        }
    return None


def _validate_uploaded_media(instance, *, required_message):
    if not instance.file:
        raise ValidationError({"file": required_message})

    policy = _media_policy(instance.media_type)
    if policy is None:
        return

    extension = _filename_extension(instance.original_filename or instance.file.name)
    content_type = instance.content_type.strip()
    errors = {}
    if extension not in policy["extensions"]:
        errors["file"] = f"Unsupported {policy['label']} file extension."
    if content_type not in policy["content_types"]:
        errors["content_type"] = f"Unsupported {policy['label']} content type."
    if instance.file_size > policy["max_bytes"]:
        errors["file_size"] = f"{policy['label'].title()} file exceeds the allowed size."
    if errors:
        raise ValidationError(errors)


_PUBLIC_EMAIL_PATTERN = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b", re.IGNORECASE)
_PUBLIC_PHONE_PATTERN = re.compile(r"(?:\+?\d[\d\s().-]*){7,}")


def _validate_public_marketing_text(value):
    text = (value or "").strip()
    if _PUBLIC_EMAIL_PATTERN.search(text) or _PUBLIC_PHONE_PATTERN.search(text):
        raise ValidationError("Public case content must not contain patient contact information.")


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


class PublicCase(models.Model):
    title = models.CharField(max_length=180, blank=True)
    note = models.TextField(blank=True)
    detail_note = models.TextField(blank=True)
    consent_confirmed = models.BooleanField(default=False, db_index=True)
    is_published = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="public_cases_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title or f"Public case {self.pk or 'unsaved'}"

    def clean(self):
        for field_name in ("title", "note", "detail_note"):
            try:
                _validate_public_marketing_text(getattr(self, field_name))
            except ValidationError as error:
                raise ValidationError({field_name: error.messages}) from error

    def has_publishable_media(self):
        if not self.pk or not self.consent_confirmed:
            return False
        candidates = self.media_items.filter(
            consent_confirmed=True,
            is_active=True,
            role__in=PublicCaseMedia.publishable_roles(),
        ).exclude(file="")
        return any(media.file_exists for media in candidates)

    def ensure_publication_eligibility(self):
        if self.is_published and not self.has_publishable_media():
            type(self).objects.filter(pk=self.pk, is_published=True).update(
                is_published=False,
                updated_at=timezone.now(),
            )
            self.is_published = False

    def save(self, *args, **kwargs):
        if not self.consent_confirmed:
            self.is_published = False
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"is_published", "updated_at"}
        self.full_clean()
        return super().save(*args, **kwargs)


class PublicCaseMedia(models.Model):
    class MediaType(models.TextChoices):
        IMAGE = "image", "Image"
        SHORT_VIDEO = "short_video", "Short video"

    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary"
        BEFORE = "before", "Before"
        AFTER = "after", "After"
        VIDEO = "video", "Video"
        VIDEO_COVER = "video_cover", "Video cover"

    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    public_case = models.ForeignKey(
        PublicCase,
        on_delete=models.CASCADE,
        related_name="media_items",
    )
    role = models.CharField(max_length=20, choices=Role.choices, db_index=True)
    media_type = models.CharField(max_length=20, choices=MediaType.choices)
    file = models.FileField(
        upload_to=public_case_media_upload_path,
        storage=public_case_media_storage,
    )
    original_filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=100, blank=True)
    consent_confirmed = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="public_case_media_uploaded",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-uploaded_at", "-id"]
        indexes = [
            models.Index(fields=["public_case", "uploaded_at"]),
            models.Index(fields=["role", "consent_confirmed", "is_active"]),
        ]

    def __str__(self):
        return f"{self.get_role_display()} asset for public case {self.public_case_id}"

    @property
    def download_filename(self):
        original_filename = _safe_basename(self.original_filename)
        if original_filename:
            return original_filename
        extension = _filename_extension(self.file.name)
        return f"public-case-media-{self.public_id}{extension}"

    @property
    def presentation_filename(self):
        extension = _filename_extension(self.file.name)
        return f"public-case-media-{self.public_id}{extension}"

    @classmethod
    def publishable_roles(cls):
        return (
            cls.Role.PRIMARY,
            cls.Role.BEFORE,
            cls.Role.AFTER,
            cls.Role.VIDEO,
        )

    @property
    def file_exists(self):
        return _stored_file_exists(self.file)

    @property
    def is_publicly_available(self):
        return (
            self.public_case.consent_confirmed
            and self.public_case.is_published
            and self.consent_confirmed
            and self.is_active
            and self.role in self.publishable_roles()
            and self.file_exists
        )

    def populate_file_metadata(self):
        _populate_file_metadata(self)

    def clean(self):
        self.populate_file_metadata()
        _validate_uploaded_media(
            self,
            required_message="Public case media file is required.",
        )
        image_roles = {
            self.Role.PRIMARY,
            self.Role.BEFORE,
            self.Role.AFTER,
            self.Role.VIDEO_COVER,
        }
        if self.role in image_roles and self.media_type != self.MediaType.IMAGE:
            raise ValidationError({"role": "This public case role requires image media."})
        if self.role == self.Role.VIDEO and self.media_type != self.MediaType.SHORT_VIDEO:
            raise ValidationError({"role": "The video role requires short video media."})

    def save(self, *args, **kwargs):
        self.populate_file_metadata()
        self.full_clean()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            update_fields.update({"original_filename", "file_size", "content_type", "updated_at"})
            kwargs["update_fields"] = update_fields
        saved = super().save(*args, **kwargs)
        self.public_case.ensure_publication_eligibility()
        return saved

    def delete(self, *args, **kwargs):
        public_case = self.public_case
        deleted = super().delete(*args, **kwargs)
        public_case.refresh_from_db(fields=["consent_confirmed", "is_published"])
        public_case.ensure_publication_eligibility()
        return deleted


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
    is_active = models.BooleanField(default=True, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="record_media_uploaded",
    )
    trashed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    trashed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="record_media_trashed",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["patient", "uploaded_at"]),
            models.Index(fields=["patient", "visibility"]),
            models.Index(fields=["visibility", "is_active"]),
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
    def presentation_filename(self):
        """Return an opaque filename for protected inline presentation."""
        extension = _filename_extension(self.file.name)
        return f"record-media-{self.public_id}{extension}"

    @property
    def file_exists(self):
        return _stored_file_exists(self.file)

    @property
    def is_visible_to_patient(self):
        return self.trashed_at is None and self.visibility == self.Visibility.VISIBLE_TO_PATIENT

    @property
    def is_trashed(self):
        return self.trashed_at is not None

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
        _populate_file_metadata(self)

    def _media_policy(self):
        return _media_policy(self.media_type)

    def _validate_private_file(self):
        _validate_uploaded_media(self, required_message="Private media file is required.")

    def clean(self):
        self.populate_file_metadata()
        self._validate_private_file()

        if self.visit_id and self.patient_id and self.visit.patient_id != self.patient_id:
            raise ValidationError({"visit": "Visit must belong to the selected patient."})
        if self.folder_id and self.patient_id and self.folder.patient_id != self.patient_id:
            raise ValidationError({"folder": "Folder must belong to the selected patient."})

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
        if not self.is_active or self.is_trashed or not self.is_visible_to_patient:
            return {}
        return {
            "media_type": self.media_type,
            "title": self.title,
            "description": self.description,
            "uploaded_at": self.uploaded_at,
        }



class PatientTimelineEvent(models.Model):
    class EventType(models.TextChoices):
        PUBLIC_CASE_PUBLISHED = "public_case_published", "Public case published"

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="timeline_events",
    )
    event_type = models.CharField(
        max_length=40,
        choices=EventType.choices,
        default=EventType.PUBLIC_CASE_PUBLISHED,
        db_index=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patient_timeline_events",
    )
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["occurred_at", "id"]
        indexes = [models.Index(fields=["patient", "occurred_at"])]

    def __str__(self):
        return f"{self.get_event_type_display()} for patient {self.patient_id}"
