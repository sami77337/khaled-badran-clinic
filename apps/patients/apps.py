from django.apps import AppConfig


class PatientsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.patients"
    verbose_name = "Patients"

    def ready(self):
        # Preserve the existing route table and local/test behavior while making
        # production registration and recovery use the OTP implementation.
        from apps.patients import account_otp, views

        if not hasattr(views, "_legacy_portal_register"):
            views._legacy_portal_register = views.portal_register
        if not hasattr(views, "_legacy_portal_account_recovery"):
            views._legacy_portal_account_recovery = views.portal_account_recovery
        views.portal_register = account_otp.portal_register
        views.portal_account_recovery = account_otp.portal_account_recovery
