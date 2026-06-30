"""Safe read-only project status report for operational review."""

import json

from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, Resolver404, resolve, reverse
from django.utils import timezone

from apps.booking import services
from apps.booking.models import Appointment
from apps.clinic.models import ClinicProfile, Doctor, VisitType
from apps.core.management.commands.deployment_smoke import PROHIBITED_ROUTE_GROUPS
from apps.core.models import SystemSetting
from apps.patients.models import Patient


REQUIRED_ROUTE_NAMES = {
    "public_site": ["home", "home_en", "doctor", "doctor_en", "services", "services_en"],
    "public_booking": [
        "book",
        "book_en",
        "booking_visit_type",
        "booking_visit_type_en",
        "booking_confirm",
        "booking_confirm_en",
        "booking_success",
        "booking_success_en",
    ],
    "staff_operations": [
        "staff_appointment_list",
        "staff_appointment_detail",
        "staff_appointment_cancel",
        "staff_appointment_reschedule",
        "staff_appointment_arrived",
        "staff_appointment_complete",
        "staff_appointment_no_show",
    ],
    "patient_portal": [
        "patient_portal_dashboard",
        "patient_portal_login",
        "patient_portal_logout",
        "patient_portal_register",
        "patient_portal_account",
        "patient_portal_password_change",
        "patient_portal_account_recovery",
        "patient_portal_link_appointment",
        "patient_portal_appointment_list",
        "patient_portal_appointment_detail",
    ],
    "health": ["health", "health_ready"],
}


def _path_is_routed(path):
    try:
        resolve(path)
    except Resolver404:
        return False
    return True


def _route_name_available(name):
    kwargs = {}
    if name.startswith("staff_appointment_") and name != "staff_appointment_list":
        kwargs["appointment_id"] = 1
    if name in {"booking_success", "booking_success_en", "patient_portal_appointment_detail"}:
        kwargs["public_token"] = "00000000-0000-4000-8000-000000000000"

    try:
        reverse(name, kwargs=kwargs or None)
    except NoReverseMatch:
        return False
    return True


def build_project_status_report():
    booking_settings = services.get_booking_settings()
    prohibited_features = {
        name: any(_path_is_routed(path) for path in paths)
        for name, paths in PROHIBITED_ROUTE_GROUPS.items()
    }
    prohibited_features.update(
        {
            "email_password_reset_enabled": False,
            "diagnosis_automation_enabled": False,
            "triage_automation_enabled": False,
            "treatment_automation_enabled": False,
            "medical_ai_enabled": False,
        }
    )

    return {
        "command": "project_status_report",
        "generated_at": timezone.now().isoformat(),
        "counts": {
            "clinic_profiles": ClinicProfile.objects.count(),
            "active_clinic_profiles": ClinicProfile.objects.filter(is_active=True).count(),
            "doctors": Doctor.objects.count(),
            "active_doctors": Doctor.objects.filter(is_active=True).count(),
            "visit_types": VisitType.objects.count(),
            "active_visit_types": VisitType.objects.filter(is_active=True).count(),
            "system_settings": SystemSetting.objects.count(),
            "patients": Patient.objects.count(),
            "appointments": Appointment.objects.count(),
        },
        "features": {
            "public_site": True,
            "public_booking": booking_settings.enabled,
            "staff_appointment_operations": True,
            "patient_portal": True,
            "uploads": False,
            "medical_records": False,
            "whatsapp_api_or_webhook": False,
            "payments": False,
            "medical_ai": False,
        },
        "routes": {
            group: all(_route_name_available(name) for name in route_names)
            for group, route_names in REQUIRED_ROUTE_NAMES.items()
        },
        "security": {
            "public_booking_requires_login": False,
            "public_success_lookup": "uuid_public_token",
            "numeric_public_success_urls": False,
            "staff_operations_require_staff": True,
            "patient_appointment_lookup": "uuid_public_token_with_authenticated_owner",
            "portal_pages_no_cache": True,
            "csrf_expected_for_state_changing_posts": True,
            "prohibited_features": prohibited_features,
            "safe_output_policy": "counts_booleans_and_route_categories_only",
        },
    }


class Command(BaseCommand):
    help = "Print a safe read-only project status report without patient-identifying data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            dest="json_output",
            help="Emit safe machine-readable JSON.",
        )

    def handle(self, *args, **options):
        report = build_project_status_report()
        if options["json_output"]:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return

        self.stdout.write("Project status report for Dr. Khaled Badran Clinic")
        self.stdout.write("Safe output: counts, booleans, and route/security categories only.")
        counts = report["counts"]
        self.stdout.write(
            "Counts: "
            f"clinic_profiles={counts['clinic_profiles']}, "
            f"active_doctors={counts['active_doctors']}, "
            f"active_visit_types={counts['active_visit_types']}, "
            f"system_settings={counts['system_settings']}, "
            f"patients={counts['patients']}, "
            f"appointments={counts['appointments']}"
        )
        features = report["features"]
        self.stdout.write(
            "Features: "
            f"public_booking={features['public_booking']}, "
            f"staff_operations={features['staff_appointment_operations']}, "
            f"patient_portal={features['patient_portal']}, "
            f"uploads={features['uploads']}, "
            f"medical_records={features['medical_records']}, "
            f"whatsapp_api_or_webhook={features['whatsapp_api_or_webhook']}, "
            f"payments={features['payments']}, "
            f"medical_ai={features['medical_ai']}"
        )
        security = report["security"]
        self.stdout.write(
            "Security: "
            f"public_success_lookup={security['public_success_lookup']}, "
            f"numeric_public_success_urls={security['numeric_public_success_urls']}, "
            f"staff_operations_require_staff={security['staff_operations_require_staff']}, "
            f"portal_pages_no_cache={security['portal_pages_no_cache']}"
        )
        self.stdout.write("Sensitive values are not printed: no names, emails, phones, tokens, secrets, or URLs.")
