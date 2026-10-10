"""Synthetic-only Django Admin login throttle and isolation regressions."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse

from apps.core.admin_auth import ADMIN_THROTTLE_NOTICE, throttled_admin_login
from apps.patients import rate_limits


class AdminLoginRateLimitTests(TestCase):
    password = "Synthetic-Admin-Password-391!"

    def setUp(self):
        cache.clear()
        self.admin_user = get_user_model().objects.create_superuser(
            username="synthetic-clinic-admin",
            email="synthetic-admin@example.invalid",
            password=self.password,
        )

    def tearDown(self):
        cache.clear()

    def _post(self, *, username=None, password=None, ip="192.0.2.10"):
        return self.client.post(
            reverse("admin:login"),
            {
                "username": username if username is not None else self.admin_user.username,
                "password": password if password is not None else self.password,
                "next": reverse("admin:index"),
            },
            REMOTE_ADDR=ip,
        )

    def test_admin_url_uses_guard_and_anonymous_get_preserves_django_login(self):
        url = reverse("admin:login")
        self.assertEqual(url, "/admin/login/")
        self.assertIs(resolve(url).func, throttled_admin_login)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/login.html")
        self.assertIn("no-store", response.get("Cache-Control", ""))

    @override_settings(
        ADMIN_LOGIN_IP_ATTEMPTS_PER_WINDOW=1,
        ADMIN_LOGIN_USERNAME_ATTEMPTS_PER_WINDOW=100,
    )
    def test_ip_limit_blocks_correct_admin_password_after_wrong_attempt(self):
        self._post(password="synthetic-incorrect")
        blocked = self._post()
        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, ADMIN_THROTTLE_NOTICE, status_code=429)
        self.assertNotContains(blocked, self.password, status_code=429)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn("no-store", blocked["Cache-Control"])

    @override_settings(
        ADMIN_LOGIN_IP_ATTEMPTS_PER_WINDOW=100,
        ADMIN_LOGIN_USERNAME_ATTEMPTS_PER_WINDOW=1,
    )
    def test_username_limit_blocks_guesses_from_separate_ips(self):
        self._post(password="bad-pass", ip="192.0.2.31")
        response = self._post(ip="192.0.2.32")
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(
        ADMIN_LOGIN_IP_ATTEMPTS_PER_WINDOW=1,
        ADMIN_LOGIN_USERNAME_ATTEMPTS_PER_WINDOW=1,
    )
    def test_get_requests_do_not_spend_attempts_and_normal_admin_login_works(self):
        self.assertEqual(self.client.get(reverse("admin:login")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:login")).status_code, 200)
        response = self._post()
        self.assertRedirects(response, reverse("admin:index"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.admin_user.pk))
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        # Already authenticated Admin sessions remain usable; no new idle timeout.
        self.assertNotEqual(self._post().status_code, 429)

    @override_settings(
        ADMIN_LOGIN_IP_ATTEMPTS_PER_WINDOW=1,
        ADMIN_LOGIN_USERNAME_ATTEMPTS_PER_WINDOW=100,
    )
    def test_django_admin_limit_does_not_block_existing_staff_portal(self):
        self._post(password="bad-password")
        self.assertEqual(self._post(password="bad-password").status_code, 429)
        portal = self.client.post(
            reverse("login"),
            {
                "role": "doctor",
                "username": self.admin_user.username,
                "password": self.password,
            },
            REMOTE_ADDR="192.0.2.10",
        )
        self.assertEqual(portal.status_code, 302)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.admin_user.pk))

    def test_cache_keys_never_contain_admin_username_ip_or_password(self):
        captured = []
        add = rate_limits.cache.add

        def record_key(key, *args, **kwargs):
            captured.append(key)
            return add(key, *args, **kwargs)

        with patch("apps.patients.rate_limits.cache.add", side_effect=record_key):
            self._post(
                username="SYNTHETIC-PRIVATE-ADMIN-USERNAME",
                password="SYNTHETIC-PRIVATE-ADMIN-PASSWORD",
                ip="198.51.100.76",
            )
        self.assertEqual(len(captured), 2)
        for key in captured:
            self.assertIn("admin-login-", key)
            self.assertNotIn("SYNTHETIC-PRIVATE-ADMIN-USERNAME", key)
            self.assertNotIn("SYNTHETIC-PRIVATE-ADMIN-PASSWORD", key)
            self.assertNotIn("198.51.100.76", key)

    @override_settings(ADMIN_LOGIN_IP_ATTEMPTS_PER_WINDOW=1)
    def test_csrf_rejection_does_not_exhaust_admin_login_quota(self):
        strict = Client(enforce_csrf_checks=True)
        ip = "203.0.113.40"
        denied = strict.post(
            reverse("admin:login"),
            {"username": self.admin_user.username, "password": "bad"},
            REMOTE_ADDR=ip,
        )
        self.assertEqual(denied.status_code, 403)
        key = rate_limits.build_rate_limit_cache_key("admin-login-ip-window", f"ip:{ip}")
        self.assertIsNone(cache.get(key))

    @override_settings(
        ADMIN_LOGIN_IP_ATTEMPTS_PER_WINDOW=1,
        ADMIN_LOGIN_USERNAME_ATTEMPTS_PER_WINDOW=1,
    )
    def test_admin_user_existence_not_disclosed_by_block_notice(self):
        for username, ip in (
            ("synthetic-unknown-admin", "203.0.113.61"),
            (self.admin_user.username, "203.0.113.62"),
        ):
            with self.subTest(username=username):
                self._post(username=username, password="bad", ip=ip)
                second = self._post(username=username, password="bad", ip=ip)
                self.assertEqual(second.status_code, 429)
                self.assertEqual(second.content.decode("utf-8"), ADMIN_THROTTLE_NOTICE)
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_non_staff_password_cannot_enter_django_admin(self):
        other = get_user_model().objects.create_user(
            username="synthetic-patient-admin-denied",
            password=self.password,
        )
        response = self._post(username=other.username)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
