from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


CLINIC_OFFICIAL_NAME_AR = "عيادة الدكتور خالد بدران"
CLINIC_OFFICIAL_NAME_EN = "Dr. Khaled Badran Clinic"


class ClinicProfile(models.Model):
    official_name_ar = models.CharField(max_length=255, default=CLINIC_OFFICIAL_NAME_AR)
    official_name_en = models.CharField(max_length=255, default=CLINIC_OFFICIAL_NAME_EN)
    phone_raw = models.CharField(max_length=50, blank=True)
    address_ar = models.TextField(blank=True)
    address_en = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["official_name_en"]

    def __str__(self):
        return self.official_name_en or self.official_name_ar


class Doctor(models.Model):
    full_name_ar = models.CharField(max_length=255)
    full_name_en = models.CharField(max_length=255)
    title_ar = models.CharField(max_length=80, blank=True)
    title_en = models.CharField(max_length=80, blank=True)
    specialty_ar = models.CharField(max_length=255, blank=True)
    specialty_en = models.CharField(max_length=255, blank=True)
    bio_ar = models.TextField(blank=True)
    bio_en = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "full_name_en"]

    def __str__(self):
        return self.display_name_en or self.display_name_ar

    @property
    def display_name_ar(self):
        return " ".join(part for part in [self.title_ar, self.full_name_ar] if part)

    @property
    def display_name_en(self):
        return " ".join(part for part in [self.title_en, self.full_name_en] if part)


class VisitType(models.Model):
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="visit_types",
    )
    name_ar = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)
    duration_minutes = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    show_price_to_patient = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    instructions_ar = models.TextField(blank=True)
    instructions_en = models.TextField(blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "name_en"]

    def __str__(self):
        return self.name_en or self.name_ar

    @property
    def is_price_visible_to_patient(self):
        return self.show_price_to_patient and self.price is not None

    @property
    def patient_visible_price(self):
        if not self.is_price_visible_to_patient:
            return None
        return self.price


class DoctorSchedule(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["doctor", "weekday", "start_time"]
        indexes = [
            models.Index(fields=["doctor", "weekday", "is_active"]),
        ]

    def __str__(self):
        return f"{self.doctor} - {self.get_weekday_display()} {self.start_time}-{self.end_time}"

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": "End time must be after start time."})


class ClosedDay(models.Model):
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="closed_days",
    )
    date = models.DateField()
    reason_ar = models.CharField(max_length=255, blank=True)
    reason_en = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date"]
        indexes = [
            models.Index(fields=["date", "is_active"]),
            models.Index(fields=["doctor", "date"]),
        ]

    def __str__(self):
        scope = self.doctor or CLINIC_OFFICIAL_NAME_EN
        return f"{scope} closed on {self.date}"
