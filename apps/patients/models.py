from django.conf import settings
from django.db import models
from django.utils import timezone


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
