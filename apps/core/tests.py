from django.test import TestCase
from django.urls import reverse

from apps.booking.models import Appointment


class HealthRouteTests(TestCase):
    def test_health_route_responds(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dr. Khaled Badran Clinic")


class PublicPageSmokeTests(TestCase):
    def test_arabic_public_pages_return_200(self):
        route_names = [
            "home",
            "doctor",
            "services",
            "contact",
            "privacy",
            "terms",
            "medical_disclaimer",
            "whatsapp_policy",
        ]

        for route_name in route_names:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)

    def test_english_public_pages_return_200(self):
        route_names = [
            "home_en",
            "doctor_en",
            "services_en",
            "contact_en",
        ]

        for route_name in route_names:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)


class PublicPageContentTests(TestCase):
    def test_arabic_clinic_name_appears_on_arabic_home(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "عيادة الدكتور خالد بدران")

    def test_english_clinic_name_appears_on_english_home(self):
        response = self.client.get(reverse("home_en"))

        self.assertContains(response, "Dr. Khaled Badran Clinic")

    def test_doctor_name_appears_on_doctor_page(self):
        response = self.client.get(reverse("doctor"))

        self.assertContains(response, "د. خالد حسان بدران")

    def test_services_page_includes_fallback_service(self):
        response = self.client.get(reverse("services"))

        self.assertContains(response, "كشف جديد")

    def test_legal_pages_include_legal_review_or_emergency_disclaimer(self):
        route_names = [
            "privacy",
            "terms",
            "medical_disclaimer",
            "whatsapp_policy",
        ]

        for route_name in route_names:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))

                self.assertContains(response, "مراجعة قانونية")

    def test_booking_cta_points_to_public_booking_flow(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'href="/book/"')
        self.assertNotContains(response, "<form")

    def test_public_pages_do_not_create_appointments(self):
        route_names = [
            "home",
            "doctor",
            "services",
            "contact",
            "privacy",
            "terms",
            "medical_disclaimer",
            "whatsapp_policy",
            "home_en",
            "doctor_en",
            "services_en",
            "contact_en",
        ]

        for route_name in route_names:
            self.client.get(reverse(route_name))

        self.assertEqual(Appointment.objects.count(), 0)

    def test_robots_and_sitemap_routes_render(self):
        robots_response = self.client.get(reverse("robots_txt"))
        sitemap_response = self.client.get(reverse("sitemap_xml"))

        self.assertContains(robots_response, "Sitemap:")
        self.assertContains(sitemap_response, "<urlset", status_code=200)
