from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.booking import services
from apps.core.models import AuditLog, SystemSetting


class PatientCancellationCutoffDashboardTests(TestCase):
    password = "Dashboard-cutoff-pass-728!"

    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="cutoff-staff",
            password=self.password,
            is_staff=True,
        )
        self.patient_user = get_user_model().objects.create_user(
            username="+962796000001",
            password=self.password,
        )
        self.url = reverse("staff_patient_cancellation_cutoff_update")

    def test_default_is_twelve_hours_without_database_row_and_ar_en_render(self):
        self.assertFalse(
            SystemSetting.objects.filter(
                key=SystemSetting.PATIENT_CANCELLATION_CUTOFF_MINUTES
            ).exists()
        )
        self.assertEqual(
            services.get_booking_settings().patient_cancellation_cutoff_minutes,
            720,
        )
        self.client.force_login(self.staff)
        arabic = self.client.get(reverse("staff_appointment_list"))
        english = self.client.get(f"{reverse('staff_appointment_list')}?lang=en")
        self.assertContains(arabic, "مهلة إلغاء المريض للموعد")
        self.assertContains(english, "Patient cancellation cutoff")
        self.assertContains(english, 'value="12"')

    def test_staff_can_update_persist_and_audit_cutoff(self):
        self.client.force_login(self.staff)
        response = self.client.post(f"{self.url}?lang=en", {"cutoff_hours": "24"})
        self.assertEqual(response.status_code, 302)
        setting = SystemSetting.objects.get(
            key=SystemSetting.PATIENT_CANCELLATION_CUTOFF_MINUTES
        )
        self.assertEqual(setting.value, "1440")
        self.assertEqual(setting.value_type, SystemSetting.ValueType.DURATION_MINUTES)
        self.assertEqual(
            services.get_booking_settings().patient_cancellation_cutoff_minutes,
            1440,
        )
        audit = AuditLog.objects.get(action=AuditLog.Action.SETTINGS_CHANGE)
        self.assertEqual(audit.user, self.staff)
        self.assertEqual(
            audit.metadata,
            {
                "key": SystemSetting.PATIENT_CANCELLATION_CUTOFF_MINUTES,
                "old_value": None,
                "new_value": "1440",
            },
        )

    def test_anonymous_and_patient_cannot_update(self):
        anonymous = self.client.post(self.url, {"cutoff_hours": "24"})
        self.assertEqual(anonymous.status_code, 302)
        self.client.force_login(self.patient_user)
        patient = self.client.post(self.url, {"cutoff_hours": "24"})
        self.assertEqual(patient.status_code, 403)
        self.assertFalse(
            SystemSetting.objects.filter(
                key=SystemSetting.PATIENT_CANCELLATION_CUTOFF_MINUTES
            ).exists()
        )

    def test_invalid_values_are_rejected_without_setting_or_audit(self):
        self.client.force_login(self.staff)
        for value in ("-1", "169", "1.5", "not-a-number"):
            with self.subTest(value=value):
                response = self.client.post(f"{self.url}?lang=en", {"cutoff_hours": value})
                self.assertEqual(response.status_code, 400)
        self.assertFalse(
            SystemSetting.objects.filter(
                key=SystemSetting.PATIENT_CANCELLATION_CUTOFF_MINUTES
            ).exists()
        )
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.SETTINGS_CHANGE).exists())

    def test_setting_post_enforces_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        self.assertEqual(
            csrf_client.post(self.url, {"cutoff_hours": "12"}).status_code,
            403,
        )
