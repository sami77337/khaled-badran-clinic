from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.http import HttpResponse, HttpResponseRedirect
from django.test import RequestFactory, TestCase, override_settings

from apps.patients import temporary_otp
from apps.patients.verification_gate import LegacyPatientOtpGateMiddleware


@override_settings(PATIENT_OTP_TEMPORARY_MODE=False)
class LegacyPatientOtpGateTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.group = Group.objects.create(name=temporary_otp.UNVERIFIED_GROUP)
        self.user = get_user_model().objects.create_user(
            username="+12025550101",
            password="Synthetic-password-781!",
        )
        self.user.groups.add(self.group)

    def request(self, path, *, method="get", user=None):
        request = getattr(self.factory, method)(path)
        request.user = user if user is not None else self.user
        return request

    @patch("apps.patients.verification_gate._ensure_current_phone_challenge")
    def test_unverified_existing_session_is_blocked_before_private_portal_view(self, ensure):
        downstream = Mock(return_value=HttpResponse("private"))
        response = LegacyPatientOtpGateMiddleware(downstream)(
            self.request("/portal/appointments/")
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/portal/password/change/")
        downstream.assert_not_called()
        ensure.assert_called_once_with(response.wsgi_request if hasattr(response, "wsgi_request") else ensure.call_args.args[0], "ar")

    @patch("apps.patients.verification_gate._ensure_current_phone_challenge")
    def test_english_portal_uses_english_verification_route(self, ensure):
        downstream = Mock(return_value=HttpResponse("private"))
        request = self.request("/en/portal/medical-records/")
        response = LegacyPatientOtpGateMiddleware(downstream)(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/en/portal/password/change/")
        downstream.assert_not_called()
        ensure.assert_called_once_with(request, "en")

    @patch("apps.patients.verification_gate._ensure_current_phone_challenge")
    def test_verification_page_and_logout_remain_reachable(self, ensure):
        for path in ("/portal/password/change/", "/portal/logout/"):
            with self.subTest(path=path):
                downstream = Mock(return_value=HttpResponse("allowed"))
                response = LegacyPatientOtpGateMiddleware(downstream)(self.request(path))
                self.assertEqual(response.status_code, 200)
                downstream.assert_called_once()
        ensure.assert_not_called()

    @patch("apps.patients.verification_gate._ensure_current_phone_challenge")
    def test_successful_login_is_rechecked_after_auth_login(self, ensure):
        request = self.request("/portal/login/", method="post", user=Mock(is_authenticated=False))

        def login_response(req):
            req.user = self.user
            return HttpResponseRedirect("/portal/")

        response = LegacyPatientOtpGateMiddleware(login_response)(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/portal/password/change/")
        ensure.assert_called_once_with(request, "ar")

    @patch("apps.patients.verification_gate._ensure_current_phone_challenge")
    def test_verified_patient_is_not_gated(self, ensure):
        self.user.groups.clear()
        downstream = Mock(return_value=HttpResponse("private"))
        response = LegacyPatientOtpGateMiddleware(downstream)(
            self.request("/portal/appointments/")
        )

        self.assertEqual(response.status_code, 200)
        downstream.assert_called_once()
        ensure.assert_not_called()

    @patch("apps.patients.verification_gate._ensure_current_phone_challenge")
    def test_staff_is_not_gated_even_if_marker_is_present(self, ensure):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        downstream = Mock(return_value=HttpResponse("staff"))
        response = LegacyPatientOtpGateMiddleware(downstream)(
            self.request("/portal/appointments/")
        )

        self.assertEqual(response.status_code, 200)
        downstream.assert_called_once()
        ensure.assert_not_called()

    @override_settings(PATIENT_OTP_TEMPORARY_MODE=True)
    @patch("apps.patients.verification_gate._ensure_current_phone_challenge")
    def test_temporary_mode_disables_gate(self, ensure):
        downstream = Mock(return_value=HttpResponse("temporary"))
        response = LegacyPatientOtpGateMiddleware(downstream)(
            self.request("/portal/appointments/")
        )

        self.assertEqual(response.status_code, 200)
        downstream.assert_called_once()
        ensure.assert_not_called()
