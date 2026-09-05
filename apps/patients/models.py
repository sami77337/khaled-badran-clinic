import uuid
import re
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.patients.storage import (
    consultation_attachment_storage,
    consultation_attachment_upload_path,
    consultation_audio_reply_storage,
    consultation_audio_reply_upload_path,
)


CONSULTATION_IMAGE_MAX_BYTES = 10 * 1024 * 1024
CONSULTATION_PDF_MAX_BYTES = 10 * 1024 * 1024
CONSULTATION_VIDEO_MAX_BYTES = 50 * 1024 * 1024
CONSULTATION_MAX_ATTACHMENTS = 5
CONSULTATION_AUDIO_MAX_BYTES = 15 * 1024 * 1024

CONSULTATION_AUDIO_POLICIES = {
    "audio/webm": {".webm"},
    "audio/ogg": {".ogg"},
    "audio/mp4": {".m4a", ".mp4"},
}

CONSULTATION_ATTACHMENT_POLICIES = {
    "image": {
        "extensions": {".jpg", ".jpeg", ".png", ".webp"},
        "content_types": {"image/jpeg", "image/png", "image/webp"},
        "max_bytes": CONSULTATION_IMAGE_MAX_BYTES,
    },
    "short_video": {
        "extensions": {".mp4"},
        "content_types": {"video/mp4"},
        "max_bytes": CONSULTATION_VIDEO_MAX_BYTES,
    },
    "pdf": {
        "extensions": {".pdf"},
        "content_types": {"application/pdf"},
        "max_bytes": CONSULTATION_PDF_MAX_BYTES,
    },
}


def safe_upload_basename(filename):
    basename = PurePosixPath(str(filename or "").replace("\\", "/")).name
    return re.sub(r"[\x00-\x1f\x7f]", "_", basename).strip()[:255]


def consultation_file_category(filename):
    extension = PurePosixPath(safe_upload_basename(filename)).suffix.lower()
    for category, policy in CONSULTATION_ATTACHMENT_POLICIES.items():
        if extension in policy["extensions"]:
            return category
    return ""


def validate_consultation_upload(uploaded_file, *, category=""):
    filename = safe_upload_basename(getattr(uploaded_file, "name", ""))
    resolved_category = category or consultation_file_category(filename)
    policy = CONSULTATION_ATTACHMENT_POLICIES.get(resolved_category)
    if policy is None:
        raise ValidationError("Unsupported consultation attachment extension.")

    size = getattr(uploaded_file, "size", 0) or 0
    content_type = (getattr(uploaded_file, "content_type", "") or "").strip().lower()
    extension = PurePosixPath(filename).suffix.lower()
    if size <= 0:
        raise ValidationError("Consultation attachments cannot be empty.")
    if extension not in policy["extensions"]:
        raise ValidationError("Unsupported consultation attachment extension.")
    if content_type not in policy["content_types"]:
        raise ValidationError("Unsupported consultation attachment content type.")
    if size > policy["max_bytes"]:
        raise ValidationError("Consultation attachment exceeds the allowed size.")
    return {
        "file_category": resolved_category,
        "original_filename": filename,
        "file_size": size,
        "content_type": content_type,
    }


def validate_consultation_audio_upload(uploaded_file):
    filename = safe_upload_basename(getattr(uploaded_file, "name", ""))
    extension = PurePosixPath(filename).suffix.lower()
    content_type = (
        (getattr(uploaded_file, "content_type", "") or "")
        .split(";", 1)[0]
        .strip()
        .lower()
    )
    size = getattr(uploaded_file, "size", 0) or 0
    allowed_extensions = CONSULTATION_AUDIO_POLICIES.get(content_type)

    if allowed_extensions is None:
        raise ValidationError("Unsupported consultation audio content type.")
    if extension not in allowed_extensions:
        raise ValidationError("Consultation audio extension does not match its content type.")
    if size <= 0:
        raise ValidationError("Consultation audio cannot be empty.")
    if size > CONSULTATION_AUDIO_MAX_BYTES:
        raise ValidationError("Consultation audio exceeds the allowed size.")
    return {
        "content_type": content_type,
        "file_size": size,
    }


class Patient(models.Model):
    class Gender(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        OTHER = "other", "Other"
        PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patient_profile",
    )
    full_name = models.CharField(max_length=255)
    phone_raw = models.CharField(max_length=50)
    phone_e164 = models.CharField(max_length=20, blank=True)
    whatsapp_phone_raw = models.CharField(max_length=50, blank=True)
    whatsapp_phone_e164 = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=30, choices=Gender.choices, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["phone_raw"]),
            models.Index(fields=["phone_e164"]),
        ]

    def __str__(self):
        return self.full_name

    @property
    def phone(self):
        return self.phone_e164 or self.phone_raw

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = timezone.localdate()
        age = today.year - self.date_of_birth.year
        if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
            age -= 1
        return age


class Consultation(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        ANSWERED = "answered", "Answered"
        CLOSED = "closed", "Closed"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="consultations",
    )
    question = models.TextField(max_length=5000)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )
    staff_reply = models.TextField(max_length=5000, blank=True)
    replied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultations_replied",
    )
    replied_at = models.DateTimeField(null=True, blank=True)
    staff_handled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["patient", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"Consultation {self.public_id}"


class ConsultationAttachment(models.Model):
    class FileCategory(models.TextChoices):
        IMAGE = "image", "Image"
        SHORT_VIDEO = "short_video", "Short video"
        PDF = "pdf", "PDF"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(
        upload_to=consultation_attachment_upload_path,
        storage=consultation_attachment_storage,
    )
    file_category = models.CharField(max_length=20, choices=FileCategory.choices)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveBigIntegerField()
    content_type = models.CharField(max_length=100)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at", "id"]
        indexes = [models.Index(fields=["consultation", "uploaded_at"])]

    def __str__(self):
        return f"Attachment {self.public_id}"

    @property
    def presentation_filename(self):
        extension = PurePosixPath(self.original_filename).suffix.lower()
        return f"consultation-attachment-{self.public_id}{extension}"

    @property
    def file_exists(self):
        if not self.file or not self.file.name:
            return False
        try:
            return self.file.storage.exists(self.file.name)
        except Exception:
            return False

    def populate_file_metadata(self):
        if not self.file:
            return
        uploaded_file = getattr(self.file, "_file", None)
        if uploaded_file is not None and not getattr(self.file, "_committed", True):
            metadata = validate_consultation_upload(
                uploaded_file,
                category=self.file_category,
            )
            self.file_category = metadata["file_category"]
            self.original_filename = metadata["original_filename"]
            self.file_size = metadata["file_size"]
            self.content_type = metadata["content_type"]

    def clean(self):
        if not self.file:
            raise ValidationError({"file": "Consultation attachment file is required."})
        self.populate_file_metadata()
        policy = CONSULTATION_ATTACHMENT_POLICIES.get(self.file_category)
        extension = PurePosixPath(self.original_filename or self.file.name).suffix.lower()
        errors = {}
        if policy is None or extension not in policy["extensions"]:
            errors["file"] = "Unsupported consultation attachment extension."
        if policy is not None and self.content_type not in policy["content_types"]:
            errors["content_type"] = "Unsupported consultation attachment content type."
        if not self.file_size:
            errors["file_size"] = "Consultation attachments cannot be empty."
        elif policy is not None and self.file_size > policy["max_bytes"]:
            errors["file_size"] = "Consultation attachment exceeds the allowed size."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.populate_file_metadata()
        self.full_clean()
        return super().save(*args, **kwargs)


class ConsultationAudioReply(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    consultation = models.OneToOneField(
        Consultation,
        on_delete=models.CASCADE,
        related_name="audio_reply",
    )
    file = models.FileField(
        upload_to=consultation_audio_reply_upload_path,
        storage=consultation_audio_reply_storage,
    )
    content_type = models.CharField(max_length=100)
    file_size = models.PositiveBigIntegerField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="consultation_audio_replies_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Consultation audio reply {self.public_id}"

    @property
    def presentation_filename(self):
        extension = PurePosixPath(self.file.name if self.file else "").suffix.lower()
        return f"consultation-audio-reply-{self.public_id}{extension}"

    @property
    def file_exists(self):
        if not self.file or not self.file.name:
            return False
        try:
            return self.file.storage.exists(self.file.name)
        except Exception:
            return False

    def populate_file_metadata(self):
        if not self.file:
            return
        uploaded_file = getattr(self.file, "_file", None)
        if uploaded_file is not None and not getattr(self.file, "_committed", True):
            metadata = validate_consultation_audio_upload(uploaded_file)
            self.content_type = metadata["content_type"]
            self.file_size = metadata["file_size"]

    def clean(self):
        if not self.file:
            raise ValidationError({"file": "Consultation audio reply file is required."})
        self.populate_file_metadata()
        extension = PurePosixPath(self.file.name).suffix.lower()
        allowed_extensions = CONSULTATION_AUDIO_POLICIES.get(self.content_type)
        errors = {}
        if allowed_extensions is None:
            errors["content_type"] = "Unsupported consultation audio content type."
        elif extension not in allowed_extensions:
            errors["file"] = "Consultation audio extension does not match its content type."
        if not self.file_size:
            errors["file_size"] = "Consultation audio cannot be empty."
        elif self.file_size > CONSULTATION_AUDIO_MAX_BYTES:
            errors["file_size"] = "Consultation audio exceeds the allowed size."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.populate_file_metadata()
        self.full_clean()
        return super().save(*args, **kwargs)


class ConsultationNotification(models.Model):
    class Kind(models.TextChoices):
        NEW_CONSULTATION = "new_consultation", "New consultation"
        CONSULTATION_REPLIED = "consultation_replied", "Consultation replied"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consultation_notifications",
    )
    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "consultation", "kind"],
                name="unique_consultation_notification",
            ),
        ]
        indexes = [
            models.Index(
                fields=["recipient", "read_at", "created_at"],
                name="pat_not_rec_read_created",
            ),
            models.Index(
                fields=["consultation", "kind"],
                name="pat_not_consult_kind",
            ),
        ]

    def __str__(self):
        return f"Consultation notification {self.public_id}"


class AccountPhoneChangeChallenge(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account_phone_change_challenges",
    )
    phone_raw = models.CharField(max_length=50)
    phone_e164 = models.CharField(max_length=20, db_index=True)
    propagate_to_upcoming_appointments = models.BooleanField(default=True)
    otp_digest = models.CharField(max_length=128)
    expires_at = models.DateTimeField(db_index=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    last_sent_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "consumed_at", "expires_at"]),
        ]

    def __str__(self):
        return f"Account phone verification {self.public_id}"

    @property
    def is_active(self):
        return (
            self.consumed_at is None
            and self.expires_at > timezone.now()
            and self.attempt_count < self.max_attempts
        )


class AppointmentLinkRecoveryChallenge(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="appointment_link_recovery_challenges",
    )
    phone_raw = models.CharField(max_length=50)
    phone_e164 = models.CharField(max_length=20, db_index=True)
    otp_digest = models.CharField(max_length=128)
    expires_at = models.DateTimeField(db_index=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    last_sent_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True, db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "consumed_at", "expires_at"]),
        ]

    def __str__(self):
        return f"Appointment link recovery {self.public_id}"

    @property
    def is_active(self):
        return (
            self.consumed_at is None
            and self.expires_at > timezone.now()
            and self.attempt_count < self.max_attempts
        )
