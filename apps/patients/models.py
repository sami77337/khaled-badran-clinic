from django.conf import settings
from django.db import models


class Patient(models.Model):
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
