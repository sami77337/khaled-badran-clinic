"""Failed sign-ins must finish on a credential-free GET, for either role."""
import json
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.patients.forms import auth_error_message
from apps.patients import rate_limits


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LoginFailureRedirectTests(TestCase):
    password = "Synthetic-login-password-778!"

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.patient = get_user_model().objects.create_user(
            username="+12025550101", password=self.password,
        )
        self.doctor = get_user_model().objects.create_user(
            username="synthetic-login-doctor", password=self.password, is_staff=True,
        )

    def credentials(self, role, *, password="Synthetic-wrong-password-993!"):
        return {
            "role": role, "password": password,
            "username" if role == "doctor" else "phone": (
                self.doctor.username if role == "doctor" else self.patient.username
            ),
        }

    def assert_no_credentials(self, client, response, credentials):
        surfaces = [
            response.get("Location", ""), response.content.decode(),
            json.dumps(dict(client.session), ensure_ascii=False),
            str(response.cookies),
            str([str(message) for message in get_messages(response.wsgi_request)]),
        ]
        for field in ("username", "phone", "password"):
            value = credentials.get(field)
            if value and value.strip():
                for surface in surfaces:
                    self.assertTrue(value not in surface, f"{field} must not be reflected or persisted")

    def test_failed_roles_redirect_to_get_and_refresh_does_not_authenticate_again(self):
        for language in ("ar", "en"):
            for role in ("patient", "doctor"):
                with self.subTest(language=language, role=role):
                    client = Client()
                    url = reverse("login_en" if language == "en" else "login")
                    credentials = self.credentials(role)
                    response = client.post(url, credentials)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.url, f"{url}?role={role}")
                    self.assert_no_credentials(client, response, credentials)
                    self.assertNotIn("_auth_user_id", client.session)
                    with patch("apps.patients.forms.authenticate") as authenticate, patch(
                        "apps.patients.rate_limits.check_login_attempt_rate_limit"
                    ) as limit:
                        page = client.get(response.url)
                        self.assertEqual(page.wsgi_request.method, "GET")
                        self.assertContains(page, auth_error_message("login_generic", language), count=1)
                        self.assertEqual(page.context["selected_role"], role)
                        self.assertContains(page, '<ul class="errorlist nonfield">')
                        for name in ("patient_form", "doctor_form"):
                            self.assertFalse(page.context[name].is_bound)
                            self.assertEqual(dict(page.context[name].data), {})
                        self.assert_no_credentials(client, page, credentials)
                        refreshed = client.get(response.url)
                        self.assertEqual(refreshed.status_code, 200)
                        self.assertEqual(refreshed.wsgi_request.method, "GET")
                        self.assertEqual(refreshed.context["selected_role"], role)
                        self.assertNotContains(refreshed, auth_error_message("login_generic", language))
                        self.assert_no_credentials(client, refreshed, credentials)
                        authenticate.assert_not_called()
                        limit.assert_not_called()

    def test_failed_redirect_preserves_only_existing_safe_next_and_normalized_role(self):
        for role in ("patient", "doctor"):
            for destination, secure, expected in (
                ("/portal/account/?tab=details", False, "/portal/account/?tab=details"),
                ("https://testserver/dashboard/", True, "https://testserver/dashboard/"),
                ("http://testserver/dashboard/", True, None),
                ("https://attacker.example/", False, None),
                ("//attacker.example/", False, None),
                ("javascript:alert(1)", False, None),
            ):
                with self.subTest(role=role, destination=destination):
                    cache.clear()
                    client = Client()
                    credentials = self.credentials(role)
                    response = client.post(
                        reverse("login_en"),
                        {**credentials, "next": destination, "unrelated": "discard-me"},
                        secure=secure,
                    )
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(urlsplit(response.url).path, reverse("login_en"))
                    query = {"role": [role]}
                    if expected:
                        query["next"] = [expected]
                    self.assertEqual(parse_qs(urlsplit(response.url).query), query)
                    page = client.get(response.url, secure=secure)
                    self.assertEqual(page.context["next_url"], expected or "")
                    self.assert_no_credentials(client, response, credentials)

        response = self.client.post(reverse("login") + "?next=/portal/account/", {"role": "untrusted-role"})
        self.assertEqual(parse_qs(urlsplit(response.url).query), {
            "role": ["patient"], "next": ["/portal/account/"],
        })

    def test_legacy_login_failures_redirect_to_canonical_localized_get(self):
        for suffix in ("", "_en"):
            for role in ("patient", "doctor"):
                response = self.client.post(reverse("patient_portal_login" + suffix), self.credentials(role))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, reverse("login" + suffix) + f"?role={role}")

    def test_success_after_failure_keeps_existing_destinations_and_clears_failure(self):
        for suffix in ("", "_en"):
            for role in ("patient", "doctor"):
                for next_url in ("", "/portal/account/"):
                    with self.subTest(suffix=suffix, role=role, next_url=next_url):
                        cache.clear()
                        client = Client()
                        url = reverse("login" + suffix)
                        client.post(url, self.credentials(role))
                        response = client.post(url, {
                            **self.credentials(role, password=self.password), "next": next_url,
                        })
                        default = (
                            reverse("dashboard_home") + ("?lang=en" if suffix else "")
                            if role == "doctor" else reverse("patient_portal_dashboard" + suffix)
                        )
                        self.assertEqual(response.status_code, 302)
                        self.assertEqual(response.url, next_url or default)
                        self.assertEqual(client.session["_auth_user_id"], str(
                            self.doctor.pk if role == "doctor" else self.patient.pk,
                        ))
                        self.assertNotIn("portal_login_failure", client.session)
                        self.assertNotIn(self.password, json.dumps(dict(client.session)))

    @override_settings(PATIENT_PORTAL_LOGIN_IP_ATTEMPTS_PER_WINDOW=1)
    def test_rate_limited_post_redirects_and_get_does_not_spend_attempts(self):
        for suffix, language in (("", "ar"), ("_en", "en")):
            cache.clear()
            client = Client()
            url = reverse("login" + suffix)
            with patch(
                "apps.patients.rate_limits.check_login_attempt_rate_limit",
                wraps=rate_limits.check_login_attempt_rate_limit,
            ) as limit:
                response = client.post(url, self.credentials("patient"))
                client.get(response.url)
                client.get(response.url)
                self.assertEqual(limit.call_count, 1)
                blocked = client.post(url, self.credentials("patient", password=self.password))
                self.assertEqual(blocked.status_code, 302)
                self.assertNotIn("_auth_user_id", client.session)
                page = client.get(blocked.url)
                self.assertContains(page, auth_error_message("rate_limit", language))
                self.assertEqual(limit.call_count, 2)
                self.assert_no_credentials(client, blocked, self.credentials("patient", password=self.password))

    def test_safe_validation_codes_survive_redirect_in_both_languages(self):
        cases = (
            ("patient", {"phone": ""}, "phone_required"),
            ("patient", {"phone": "   "}, "phone_required"),
            ("patient", {"phone": "not-a-phone"}, "phone_invalid"),
            ("patient", {"phone": "1" * 51}, "phone_invalid"),
            ("patient", {"password": ""}, "password_required"),
            ("patient", {"phone": "", "password": ""}, "phone_required"),
            ("patient", {"phone": "not-a-phone", "password": ""}, "phone_invalid"),
            ("doctor", {"username": ""}, "username_required"),
            ("doctor", {"username": "   "}, "username_required"),
            ("doctor", {"password": ""}, "password_required"),
            ("doctor", {"username": "", "password": ""}, "username_required"),
        )
        destination = "/portal/account/?tab=details"
        for suffix, language in (("", "ar"), ("_en", "en")):
            for role, invalid_fields, code in cases:
                with self.subTest(language=language, role=role, fields=tuple(invalid_fields), code=code):
                    cache.clear()
                    client = Client()
                    credentials = {**self.credentials(role), **invalid_fields}
                    with self.assertNoLogs("apps.patients", level="DEBUG"), patch(
                        "apps.patients.forms.authenticate"
                    ) as authenticate, patch(
                        "apps.patients.rate_limits.check_login_attempt_rate_limit",
                        wraps=rate_limits.check_login_attempt_rate_limit,
                    ) as limit:
                        response = client.post(reverse("login" + suffix), {
                            **credentials, "next": destination,
                        })
                        self.assertEqual(response.status_code, 302)
                        self.assertEqual(urlsplit(response.url).path, reverse("login" + suffix))
                        self.assertEqual(parse_qs(urlsplit(response.url).query), {
                            "role": [role], "next": [destination],
                        })
                        self.assertEqual(client.session["portal_login_failure"], {"role": role, "code": code})
                        self.assert_no_credentials(client, response, credentials)
                        page = client.get(response.url)
                        self.assertEqual(page.wsgi_request.method, "GET")
                        self.assertContains(page, auth_error_message(code, language), count=1)
                        self.assertNotContains(page, auth_error_message("login_generic", language))
                        self.assertEqual(page.context["selected_role"], role)
                        self.assertEqual(page.context["next_url"], destination)
                        self.assertNotIn("portal_login_failure", client.session)
                        self.assert_no_credentials(client, page, credentials)
                        refreshed = client.get(response.url)
                        self.assertEqual(refreshed.status_code, 200)
                        self.assertEqual(refreshed.wsgi_request.method, "GET")
                        self.assertNotContains(refreshed, auth_error_message(code, language))
                        self.assert_no_credentials(client, refreshed, credentials)
                        authenticate.assert_not_called()
                        self.assertEqual(limit.call_count, 1 if role == "patient" else 0)

    @override_settings(PATIENT_PORTAL_LOGIN_IP_ATTEMPTS_PER_WINDOW=1)
    def test_rate_limit_takes_priority_over_safe_validation_errors(self):
        for suffix, language in (("", "ar"), ("_en", "en")):
            for invalid_fields in ({"phone": ""}, {"phone": "not-a-phone"}, {"password": ""}):
                with self.subTest(language=language, fields=tuple(invalid_fields)):
                    cache.clear()
                    client = Client()
                    url = reverse("login" + suffix)
                    client.post(url, self.credentials("patient"))
                    credentials = {**self.credentials("patient"), **invalid_fields}
                    response = client.post(url, credentials)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(client.session["portal_login_failure"], {
                        "role": "patient", "code": "rate_limit",
                    })
                    self.assert_no_credentials(client, response, credentials)
                    page = client.get(response.url)
                    self.assertContains(page, auth_error_message("rate_limit", language), count=1)
                    self.assertEqual(list(page.context["login_errors"]), [auth_error_message("rate_limit", language)])
                    self.assertNotIn("_auth_user_id", client.session)

    def test_inactive_accounts_and_nonstaff_doctor_attempts_remain_generic(self):
        inactive = get_user_model().objects.create_user(
            username="+12025550102", password=self.password, is_active=False, is_staff=True,
        )
        for suffix, language in (("", "ar"), ("_en", "en")):
            for role, data in (
                ("patient", {"phone": inactive.username, "password": self.password}),
                ("patient", {"phone": "+12025550103", "password": "wrong"}),
                ("doctor", {"username": inactive.username, "password": self.password}),
                ("doctor", {"username": "unknown-user", "password": "wrong"}),
                ("doctor", {"username": self.patient.username, "password": self.password}),
            ):
                with self.subTest(language=language, role=role, identity=data.get("username", data.get("phone"))):
                    client = Client()
                    credentials = {"role": role, **data}
                    response = client.post(reverse("login" + suffix), credentials)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.url, reverse("login" + suffix) + f"?role={role}")
                    self.assertEqual(client.session["portal_login_failure"], {"role": role, "code": "login_generic"})
                    self.assert_no_credentials(client, response, credentials)
                    page = client.get(response.url)
                    self.assertContains(page, auth_error_message("login_generic", language), count=1)
                    self.assert_no_credentials(client, page, credentials)
                    self.assertNotIn("_auth_user_id", client.session)

    def test_role_switch_cannot_display_another_roles_failure(self):
        self.client.post(reverse("login"), self.credentials("doctor"))
        page = self.client.get(reverse("login") + "?role=patient")
        self.assertNotContains(page, auth_error_message("login_generic", "ar"))

    def test_csrf_rejection_remains_403_for_both_roles(self):
        for role in ("patient", "doctor"):
            client = Client(enforce_csrf_checks=True)
            response = client.post(reverse("login"), self.credentials(role))
            self.assertEqual(response.status_code, 403)
            self.assertNotIn("portal_login_failure", client.session)
