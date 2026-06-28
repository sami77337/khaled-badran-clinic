from django.contrib import admin

from .models import ClinicProfile, ClosedDay, Doctor, DoctorSchedule, VisitType


@admin.register(ClinicProfile)
class ClinicProfileAdmin(admin.ModelAdmin):
    list_display = ("official_name_en", "official_name_ar", "phone_raw", "is_active")
    list_filter = ("is_active",)
    search_fields = ("official_name_en", "official_name_ar", "phone_raw")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = (
        "display_name_en",
        "display_name_ar",
        "specialty_en",
        "is_active",
        "display_order",
    )
    list_filter = ("is_active",)
    search_fields = (
        "full_name_en",
        "full_name_ar",
        "title_en",
        "title_ar",
        "specialty_en",
        "specialty_ar",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(VisitType)
class VisitTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name_en",
        "name_ar",
        "doctor",
        "duration_minutes",
        "price",
        "show_price_to_patient",
        "is_active",
        "display_order",
    )
    list_filter = ("is_active", "show_price_to_patient", "doctor")
    search_fields = ("name_en", "name_ar", "doctor__full_name_en", "doctor__full_name_ar")
    autocomplete_fields = ("doctor",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(admin.ModelAdmin):
    list_display = ("doctor", "weekday", "start_time", "end_time", "is_active")
    list_filter = ("weekday", "is_active", "doctor")
    search_fields = ("doctor__full_name_en", "doctor__full_name_ar")
    autocomplete_fields = ("doctor",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(ClosedDay)
class ClosedDayAdmin(admin.ModelAdmin):
    list_display = ("date", "doctor", "reason_en", "reason_ar", "is_active")
    list_filter = ("is_active", "doctor", "date")
    search_fields = (
        "reason_en",
        "reason_ar",
        "doctor__full_name_en",
        "doctor__full_name_ar",
    )
    autocomplete_fields = ("doctor",)
    readonly_fields = ("created_at", "updated_at")
