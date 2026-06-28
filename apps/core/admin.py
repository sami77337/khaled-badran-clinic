from django.contrib import admin

from .models import AuditLog, SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "value_type", "updated_at")
    list_filter = ("value_type",)
    search_fields = ("key", "value", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "user", "model_name", "object_repr")
    list_filter = ("action", "app_label", "model_name", "created_at")
    search_fields = (
        "user__username",
        "app_label",
        "model_name",
        "object_id",
        "object_repr",
        "message",
    )
    readonly_fields = ("created_at",)
