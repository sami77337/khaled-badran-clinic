from django.test import SimpleTestCase
from django.urls import reverse


class HealthRouteTests(SimpleTestCase):
    def test_health_route_responds(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dr. Khaled Badran Clinic")
