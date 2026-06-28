from django.contrib import admin

from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone_raw", "phone_e164", "whatsapp_phone_e164", "created_at")
    list_filter = ("created_at",)
    search_fields = (
        "full_name",
        "phone_raw",
        "phone_e164",
        "whatsapp_phone_raw",
        "whatsapp_phone_e164",
    )
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")
