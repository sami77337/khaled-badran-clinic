from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class RegistrationSecurityContractTests(TestCase):
    password = "Registration-contract-pass-782!"

    def test_patient_panel_keeps_create_account_and_doctor_panel_never_has_it(self):
        cases = (
            ("login", "إنشاء حساب"),
            ("login_en", "Create account"),
        )
        for route_name, create_label in cases:
            with self.subTest(route=route_name):
                response = self.client.get(f"{reverse(route_name)}?role=doctor")
                html = response.content.decode()
                patient_panel, doctor_panel = html.split('id="patient-login-panel"', 1)[1].split(
                    'id="doctor-login-panel"', 1
                )
                self.assertIn(create_label, patient_panel)
                self.assertIn(reverse("patient_portal_register" if route_name == "login" else "patient_portal_register_en"), patient_panel)
                self.assertNotIn(create_label, doctor_panel)
                self.assertNotIn("portal/register", doctor_panel)

    def test_no_public_doctor_staff_or_dashboard_registration_endpoint_exists(self):
        paths = (
            "/doctor/register/",
            "/staff/register/",
            "/dashboard/register/",
            "/portal/doctor/register/",
            "/portal/staff/register/",
            "/en/doctor/register/",
            "/en/staff/register/",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
                self.assertEqual(
                    self.client.post(
                        path,
                        {"username": "attacker", "password": self.password},
                    ).status_code,
                    404,
                )

    def test_anonymous_patient_registration_cannot_set_staff_or_superuser_flags(self):
        response = self.client.post(
            reverse("patient_portal_register_en"),
            {
                "full_name": "Unprivileged Patient",
                "phone": "+962790399991",
                "email": "patient@example.test",
                "password1": self.password,
                "password2": self.password,
                "role": "doctor",
                "is_staff": "on",
                "is_superuser": "on",
                "user_permissions": ["1", "2", "3"],
            },
        )

        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username="+962790399991")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.user_permissions.count(), 0)

    def test_doctor_login_still_authenticates_only_a_provisioned_staff_user(self):
        staff = get_user_model().objects.create_user(
            username="provisioned-doctor",
            password=self.password,
            is_staff=True,
        )

        response = self.client.post(
            reverse("login_en"),
            {
                "role": "doctor",
                "username": staff.username,
                "password": self.password,
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('dashboard_home')}?lang=en",
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.session["_auth_user_id"], str(staff.pk))

    def test_django_admin_superuser_provisioning_surface_remains_available(self):
        user_model = get_user_model()
        self.assertIn(user_model, admin.site._registry)
        superuser = user_model.objects.create_superuser(
            username="back-office-owner",
            email="owner@example.test",
            password=self.password,
        )
        self.client.force_login(superuser)

        add_user = self.client.get(reverse("admin:auth_user_add"))

        self.assertEqual(add_user.status_code, 200)
        self.assertContains(add_user, 'name="username"')
        self.assertContains(add_user, 'name="password1"')
        self.assertContains(add_user, 'name="password2"')
