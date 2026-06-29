from datetime import timedelta
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def default_appointment_reminder_offset():
    return timedelta(hours=3)


class Appointment(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        ARRIVED = "arrived", "Arrived"
        COMPLETED = "completed", "Completed"
        NO_SHOW = "no_show", "No-show"
        CANCELLED = "cancelled", "Cancelled"
        RESCHEDULED = "rescheduled", "Rescheduled"

    doctor = models.ForeignKey(
        "clinic.Doctor",
        on_delete=models.PROTECT,
        related_name="appointments",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="appointments",
    )
    visit_type = models.ForeignKey(
        "clinic.VisitType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="appointments",
    )
    public_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CONFIRMED,
        db_index=True,
    )
    reminder_offset = models.DurationField(default=default_appointment_reminder_offset)
    reminder_enabled = models.BooleanField(default=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    booking_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["doctor", "starts_at"]),
            models.Index(fields=["doctor", "status", "starts_at"]),
            models.Index(fields=["patient", "starts_at"]),
            models.Index(fields=["status", "starts_at"]),
            models.Index(fields=["starts_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="appointment_ends_after_start",
            ),
            models.UniqueConstraint(
                fields=["doctor", "starts_at", "status"],
                name="unique_appointment_doctor_start_status",
            ),
            models.UniqueConstraint(
                fields=["doctor", "starts_at"],
                condition=models.Q(
                    status__in=[
                        "confirmed",
                        "arrived",
                        "rescheduled",
                    ]
                ),
                name="unique_active_appointment_doctor_start",
            ),
        ]

    def __str__(self):
        return f"{self.patient} with {self.doctor} at {self.starts_at}"

    @property
    def reminder_due_at(self):
        return self.starts_at - self.reminder_offset

    @property
    def confirmation_reference(self):
        return str(self.public_token).split("-")[0].upper()

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "End time must be after start time."})


class AppointmentStatusHistory(models.Model):
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    old_status = models.CharField(
        max_length=20,
        choices=Appointment.Status.choices,
        blank=True,
    )
    new_status = models.CharField(
        max_length=20,
        choices=Appointment.Status.choices,
        db_index=True,
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointment_status_changes",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["appointment", "created_at"]),
        ]

    def __str__(self):
        return f"{self.appointment_id}: {self.old_status or 'new'} -> {self.new_status}"
