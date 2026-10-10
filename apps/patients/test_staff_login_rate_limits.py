"""Synthetic-only regression tests for the shared Doctor / Clinic Staff sign-in."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.patients import rate_limits
from apps.patients.forms import auth_error_message


class StaffLoginRateLimitTests(TestCase):
    password = "Synthetic-Clinic-Password-391!"

    def setUp(self):
        cache.clear()
        self.clinician = get_user_model().objects.create_user(
            username="synthetic-clinic-login",
            password=self.password,
            is_staff=True,
        )

    def tearDown(self):
        cache.clear()

    def _post_staff(self, *, route="login", username=None, password=None, ip="192.0.2.10"):
        return self.client.post(
            reverse(route),
            {
                "role": "doctor",
                "username": username if username is not None else self.clinician.username,
                "password": password if password is not None else self.password,
            },
            REMOTE_ADDR=ip,
        )

    @override_settings(
        STAFF_LOGIN_IP_ATTEMPTS_PER_WINDOW=1,
        STAFF_LOGIN_USERNAME_ATTEMPTS_PER_WINDOW=100,
    )
    def test_ip_limit_denies_even_correct_staff_password_after_failed_attempt(self):
        self._post_staff(password="synthetic-wrong-password")
        blocked = self._post_staff()
        self.assertRedirects(
            blocked, f'{reverse("login")}?role=doctor',
            fetch_redirect_response=False,
        )
        page = self.client.get(blocked["Location"])
        self.assertContains(page, auth_error_message("rate_limit", "ar"))
        self.assertNotContains(page, "synthetic-wrong-password")
        self.assertNotContains(page, self.password)
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(
        STAFF_LOGIN_IP_ATTEMPTS_PER_WINDOW=100,
        STAFF_LOGIN_USERNAME_ATTEMPTS_PER_WINDOW=1,
    )
    def test_username_limit_blocks_password_guesses_across_different_ips(self):
        self._post_staff(password="synthetic-wrong-password", ip="192.0.2.21")
        blocked = self._post_staff(ip="192.0.2.22")
        self.assertEqual(blocked.status_code, 302)
        page = self.client.get(blocked["Location"])
        self.assertContains(page, auth_error_message("rate_limit", "ar"))
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(
        STAFF_LOGIN_IP_ATTEMPTS_PER_WINDOW=1,
        STAFF_LOGIN_USERNAME_ATTEMPTS_PER_WINDOW=100,
    )
    def test_bilingual_rate_limit_uses_existing_localized_login_errors(self):
        for route, locale, addr in (
            ("login", "ar", "192.0.2.31"),
            ("login_en", "en", "192.0.2.32"),
        ):
            with self.subTest(route=route):
                self._post_staff(
                    route=route, username="missing-clinic-account",
                    password="synthetic-unusable", ip=addr,
                )
                blocked = self._post_staff(
                    route=route, username="missing-clinic-account",
                    password="synthetic-unusable", ip=addr,
                )
                self.assertEqual(blocked.status_code, 302)
                page = self.client.get(blocked["Location"])
                self.assertContains(page, auth_error_message("rate_limit", locale))
                self.assertNotContains(page, "synthetic-unusable")
                self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(
        STAFF_LOGIN_IP_ATTEMPTS_PER_WINDOW=2,
        STAFF_LOGIN_USERNAME_ATTEMPTS_PER_WINDOW=2,
    )
    def test_valid_clinical_staff_sign_in_unchanged_before_threshold(self):
        result = self._post_staff(route="login_en")
        self.assertRedirects(
            result, f'{reverse("dashboard_home")}?lang=en',
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.session["_auth_user_id"], str(self.clinician.pk))

    @override_settings(
        STAFF_LOGIN_IP_ATTEMPTS_PER_WINDOW=1,
        STAFF_LOGIN_USERNAME_ATTEMPTS_PER_WINDOW=100,
    )
    def test_staff_limit_does_not_block_patient_login(self):
        patient = get_user_model().objects.create_user(
            username="+962791234567", password=self.password,
        )
        self._post_staff(username="unknown-staff", password="wrong")
        self._post_staff(username="unknown-staff", password="wrong")
        response = self.client.post(
            reverse("login_en"),
            {
                "role": "patient",
                "phone": "0791234567",
                "password": self.password,
            },
            REMOTE_ADDR="192.0.2.10",
        )
        self.assertRedirects(
            response, reverse("patient_portal_dashboard_en"),
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.session["_auth_user_id"], str(patient.pk))

    def test_cache_keys_never_store_raw_staff_username_or_password(self):
        keys = []
        original = rate_limits.cache.add

        def capture(key, *args, **kwargs):
            keys.append(key)
            return original(key, *args, **kwargs)

        with patch("apps.patients.rate_limits.cache.add", side_effect=capture):
            self._post_staff(
                username="SYNTHETIC-PRIVATE-CLINIC-USERNAME",
                password="SYNTHETIC-PRIVATE-STAFF-PASSWORD",
                ip="198.51.100.19",
            )
        self.assertEqual(len(keys), 2)
        for key in keys:
            self.assertIn("staff-login-", key)
            self.assertNotIn("SYNTHETIC-PRIVATE-CLINIC-USERNAME", key)
            self.assertNotIn("SYNTHETIC-PRIVATE-STAFF-PASSWORD", key)
            self.assertNotIn("198.51.100.19", key)

    def test_limit_does_not_reveal_existence_of_staff_username(self):
        with override_settings(
            STAFF_LOGIN_IP_ATTEMPTS_PER_WINDOW=1,
            STAFF_LOGIN_USERNAME_ATTEMPTS_PER_WINDOW=1,
        ):
            for username, ip in (
                ("missing-synthetic-clinic-user", "203.0.113.11"),
                (self.clinician.username, "203.0.113.12"),
            ):
                with self.subTest(username=username):
                    first = self._post_staff(username=username, password="bad", ip=ip)
                    second = self._post_staff(username=username, password="bad", ip=ip)
                    self.assertEqual(first.status_code, 302)
                    self.assertEqual(second.status_code, 302)
                    self.assertContains(
                        self.client.get(second["Location"]),
                        auth_error_message("rate_limit", "ar"),
                    )
                    self.assertNotIn("_auth_user_id", self.client.session)
