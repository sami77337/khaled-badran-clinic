from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class PublicAuthNavigationTests(TestCase):
    def setUp(self):
        self.User = get_user_model()

    def test_anonymous_home_shows_login_and_patient_portal_enters_patient_login(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-auth-action="login"', count=2)
        self.assertNotContains(response, 'data-auth-action="doctor-dashboard"')
        self.assertContains(
            response,
            f'href="{reverse("login")}?role=patient"',
            count=2,
        )
        self.assertContains(response, 'data-nav-key="patient_portal"', count=2)

    def test_patient_home_hides_login_and_links_portal_directly(self):
        patient_user = self.User.objects.create_user(
            username="synthetic-patient-nav",
            password="SyntheticPass-12345",
        )
        self.client.force_login(patient_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-auth-action="login"')
        self.assertNotContains(response, 'data-auth-action="doctor-dashboard"')
        self.assertContains(
            response,
            f'href="{reverse("patient_portal_dashboard")}"',
            count=2,
        )
        self.assertContains(response, 'data-nav-key="patient_portal"', count=2)

    def test_staff_home_shows_doctor_dashboard_only_and_hides_patient_portal_nav(self):
        staff_user = self.User.objects.create_user(
            username="synthetic-doctor-nav",
            password="SyntheticPass-12345",
            is_staff=True,
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-auth-action="login"')
        self.assertContains(response, 'data-auth-action="doctor-dashboard"', count=2)
        self.assertContains(
            response,
            f'href="{reverse("dashboard_home")}"',
            count=2,
        )
        self.assertNotContains(response, 'data-nav-key="patient_portal"')

    def test_english_auth_navigation_preserves_english_routes(self):
        response = self.client.get(reverse("home_en"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-auth-action="login"', count=2)
        self.assertContains(
            response,
            f'href="{reverse("login_en")}?role=patient"',
            count=2,
        )

        staff_user = self.User.objects.create_user(
            username="synthetic-doctor-nav-en",
            password="SyntheticPass-12345",
            is_staff=True,
        )
        self.client.force_login(staff_user)
        response = self.client.get(reverse("home_en"))

        self.assertContains(response, 'data-auth-action="doctor-dashboard"', count=2)
        self.assertContains(
            response,
            f'href="{reverse("dashboard_home")}?lang=en"',
            count=2,
        )
