from django.contrib import admin

from .models import Appointment, AppointmentStatusHistory


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "starts_at",
        "ends_at",
        "patient",
        "doctor",
        "visit_type",
        "status",
        "reminder_offset",
        "reminder_enabled",
    )
    list_filter = ("status", "doctor", "visit_type", "reminder_enabled", "starts_at")
    search_fields = (
        "patient__full_name",
        "patient__phone_raw",
        "patient__phone_e164",
        "doctor__full_name_en",
        "doctor__full_name_ar",
        "visit_type__name_en",
        "visit_type__name_ar",
    )
    autocomplete_fields = ("doctor", "patient", "visit_type")
    readonly_fields = ("created_at", "updated_at", "reminder_due_at_display")

    @admin.display(description="Reminder due at")
    def reminder_due_at_display(self, obj):
        return obj.reminder_due_at


@admin.register(AppointmentStatusHistory)
class AppointmentStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("appointment", "old_status", "new_status", "changed_by", "created_at")
    list_filter = ("new_status", "old_status", "created_at")
    search_fields = (
        "appointment__patient__full_name",
        "appointment__patient__phone_raw",
        "appointment__doctor__full_name_en",
        "appointment__doctor__full_name_ar",
        "note",
    )
    autocomplete_fields = ("appointment", "changed_by")
    readonly_fields = ("created_at",)
