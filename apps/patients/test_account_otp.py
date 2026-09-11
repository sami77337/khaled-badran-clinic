"""Account OTP regressions using synthetic identities and a mocked sender."""

from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone

from . import account_otp as otp, account_views
from .models import AccountOtpChallenge, Patient
from .otp import WhatsAppOtpServiceUnavailable, send_patient_account_otp


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AccountOtpTests(TestCase):
    phone = "+12025550101"
    password = "Synthetic-account-password-781!"

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.sender = Mock(return_value=True)
        settings = override_settings(PATIENT_ACCOUNT_OTP_SENDER=self.sender)
        settings.enable()
        self.addCleanup(settings.disable)
        code = patch(
            "apps.patients.account_otp.generate_otp_code", return_value="123456"
        )
        code.start()
        self.addCleanup(code.stop)

    def url(self, purpose="registration", language="en"):
        route = (
            "patient_portal_register"
            if purpose == "registration"
            else "patient_portal_account_recovery"
        )
        return reverse(route + ("_en" if language == "en" else ""))

    def start(self, purpose="registration", language="en", client=None, **changes):
        data = {
            "phone": self.phone,
            "full_name": "Synthetic Account",
            "email": "synthetic@example.test",
            "password1": self.password,
            "password2": self.password,
            "action": "start",
        }
        data.update(changes)
        return (client or self.client).post(self.url(purpose, language), data)

    def challenge(self, purpose="registration", client=None):
        token = (client or self.client).session[otp.SESSION_KEYS[purpose]]
        return AccountOtpChallenge.objects.get(pk=token)

    def verify(
        self,
        purpose="registration",
        code="123456",
        client=None,
        language="en",
        **changes,
    ):
        return (client or self.client).post(
            self.url(purpose, language), {"action": "verify", "otp": code, **changes}
        )

    def recovery_start(self):
        self.user = get_user_model().objects.create_user(
            username=self.phone, password=self.password
        )
        return self.start("recovery")

    def reset(
        self, password="Synthetic-replacement-password-912!", client=None, language="en"
    ):
        return (client or self.client).post(
            self.url("recovery", language),
            {
                "action": "reset",
                "new_password1": password,
                "new_password2": password,
            },
        )

    def test_routes_are_explicit_and_no_environment_can_bypass_otp(self):
        self.assertIs(resolve(self.url()).func, account_views.portal_register)
        self.assertIs(
            resolve(self.url("recovery")).func, account_views.portal_account_recovery
        )
        with self.settings(PRODUCTION=False, PATIENT_ACCOUNT_OTP_REQUIRED=False):
            self.assertEqual(self.start().status_code, 302)
        self.assertFalse(get_user_model().objects.exists())

    def test_registration_creates_account_only_after_six_digit_otp_in_both_languages(
        self,
    ):
        for language in ("ar", "en"):
            with self.subTest(language=language):
                cache.clear()
                self.client.logout()
                self.assertRedirects(
                    self.start(language=language),
                    self.url(language=language) + "?verify=1",
                )
                self.assertFalse(get_user_model().objects.exists())
                self.sender.assert_called_with(self.phone, "123456", language)
                challenge = self.challenge()
                self.assertNotEqual(challenge.otp_digest, "123456")
                self.assertNotEqual(
                    challenge.pending_registration["password_hash"], self.password
                )
                self.assertNotIn(self.password, str(dict(self.client.session)))
                response = self.verify(
                    language=language,
                    phone="+12025550109",
                    is_staff="on",
                    is_superuser="on",
                )
                self.assertEqual(response.status_code, 302)
                user = get_user_model().objects.get()
                self.assertEqual(user.username, self.phone)
                self.assertTrue(user.check_password(self.password))
                self.assertFalse(user.is_staff or user.is_superuser)
                self.assertFalse(AccountOtpChallenge.objects.exists())
                user.delete()

    def test_registration_password_validation_happens_before_sending(self):
        response = self.start(password1="123", password2="123")
        self.assertContains(response, "password", status_code=200)
        self.sender.assert_not_called()
        self.assertFalse(AccountOtpChallenge.objects.exists())

    def test_failed_and_malformed_otp_consume_budget_without_sliding_expiry(self):
        self.start()
        challenge = self.challenge()
        expires = challenge.expires_at
        for code in ("000000", "", "abc", "12345", "999999"):
            self.assertEqual(self.verify(code=code).status_code, 200)
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempt_count, otp.OTP_MAX_ATTEMPTS)
        self.assertEqual(challenge.expires_at, expires)
        self.assertEqual(self.verify().status_code, 302)
        self.assertFalse(get_user_model().objects.exists())

    def test_expired_code_cannot_create_account_or_be_resent(self):
        self.start()
        AccountOtpChallenge.objects.update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(self.verify().status_code, 302)
        self.client.post(self.url(), {"action": "resend"})
        self.assertEqual(self.sender.call_count, 1)
        self.assertFalse(get_user_model().objects.exists())

    def test_resend_cooldown_and_old_code_invalidation_preserve_attempt_budget(self):
        self.start()
        challenge = self.challenge()
        self.verify(code="999999")
        self.client.post(self.url(), {"action": "resend"})
        self.assertEqual(self.sender.call_count, 1)
        cache.clear()
        AccountOtpChallenge.objects.update(
            last_sent_at=timezone.now() - timedelta(seconds=61)
        )
        with patch(
            "apps.patients.account_otp.generate_otp_code", return_value="654321"
        ):
            self.client.post(self.url(), {"action": "resend"})
        challenge.refresh_from_db()
        self.assertEqual(self.sender.call_count, 2)
        self.assertEqual(challenge.attempt_count, 1)
        self.assertEqual(self.verify().status_code, 200)
        self.assertFalse(get_user_model().objects.exists())
        self.assertEqual(self.verify(code="654321").status_code, 302)
        self.assertTrue(get_user_model().objects.exists())

    def test_restarting_does_not_bypass_phone_cooldown_and_revokes_old_challenge(self):
        self.start()
        old = self.challenge().pk
        self.start()
        self.assertFalse(AccountOtpChallenge.objects.filter(pk=old).exists())
        self.assertEqual(self.sender.call_count, 1)
        self.verify()
        self.assertFalse(get_user_model().objects.exists())

    def test_challenge_is_bound_to_session_not_just_token_and_code(self):
        self.start()
        other = Client()
        session = other.session
        session[otp.REGISTRATION_SESSION_KEY] = str(self.challenge().pk)
        session[otp.SESSION_BINDING_KEY] = "different-session-binding"
        session.save()
        self.verify(client=other)
        self.assertFalse(get_user_model().objects.exists())
        self.verify()
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_registration_cannot_reuse_recovery_challenge(self):
        self.recovery_start()
        session = self.client.session
        session[otp.REGISTRATION_SESSION_KEY] = session[otp.RECOVERY_SESSION_KEY]
        session.save()
        self.assertEqual(self.verify().status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_existing_phone_has_same_preverification_response_and_no_duplicate(self):
        self.start()
        unknown_page = self.client.get(self.url() + "?verify=1")
        original = get_user_model().objects.create_user(
            username=self.phone, password=self.password
        )
        cache.clear()
        self.client = Client()
        self.start()
        known_page = self.client.get(self.url() + "?verify=1")
        self.assertEqual(known_page.status_code, unknown_page.status_code)
        self.assertEqual(
            known_page.context["masked_phone"], unknown_page.context["masked_phone"]
        )
        self.assertEqual(
            known_page.context["form"].errors, unknown_page.context["form"].errors
        )
        self.assertEqual(self.verify().status_code, 200)
        self.assertEqual(get_user_model().objects.count(), 1)
        original.refresh_from_db()
        self.assertTrue(original.check_password(self.password))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_patient_phone_already_linked_to_nonphone_username_is_not_duplicated(self):
        user = get_user_model().objects.create_user(username="synthetic-legacy")
        Patient.objects.create(user=user, phone_e164=self.phone, full_name="Synthetic")
        self.start()
        self.verify()
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_unlinked_booking_patient_does_not_block_or_auto_link_registration(self):
        patient = Patient.objects.create(
            phone_e164=self.phone, full_name="Synthetic booking"
        )
        self.start()
        self.verify()
        patient.refresh_from_db()
        self.assertIsNone(patient.user_id)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_duplicate_created_after_start_cannot_be_overwritten(self):
        self.start()
        user = get_user_model().objects.create_user(
            username=self.phone, password="Original-synthetic-pass-71!"
        )
        self.verify()
        user.refresh_from_db()
        self.assertTrue(user.check_password("Original-synthetic-pass-71!"))
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_send_failure_is_generic_and_generated_code_cannot_verify(self):
        for purpose in ("registration", "recovery"):
            cache.clear()
            self.sender.side_effect = RuntimeError("private-provider-sentinel")
            self.assertEqual(self.start(purpose).status_code, 302)
            self.assertEqual(self.challenge(purpose).otp_digest, "")
            response = self.verify(purpose)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "private-provider-sentinel")
        self.assertFalse(get_user_model().objects.exists())

    def test_unknown_known_inactive_staff_superuser_and_provider_failures_have_same_recovery_behavior(
        self,
    ):
        expected = None
        for flags in (
            None,
            {},
            {"is_active": False},
            {"is_staff": True},
            {"is_superuser": True},
        ):
            for failure in (False, True):
                cache.clear()
                AccountOtpChallenge.objects.all().delete()
                get_user_model().objects.all().delete()
                if flags is not None:
                    get_user_model().objects.create_user(
                        username=self.phone, password=self.password, **flags
                    )
                self.client = Client()
                self.sender.side_effect = (
                    RuntimeError("private-sentinel") if failure else None
                )
                response = self.start("recovery")
                page = self.client.get(response.url)
                signature = (
                    response.status_code,
                    response.url,
                    page.context["recovery_stage"],
                    [str(m) for m in page.context["messages"]],
                )
                if expected is None:
                    expected = signature
                self.assertEqual(signature, expected)
                resend = self.client.post(
                    self.url("recovery"), {"action": "resend"}, follow=True
                )
                self.assertContains(
                    resend, "Wait briefly before requesting a new code."
                )
                failed = self.verify("recovery", code="000000")
                self.assertContains(
                    failed, "The verification code is invalid or expired."
                )

    def test_recovery_correct_code_for_unknown_phone_cannot_create_grant(self):
        self.start("recovery")
        self.assertEqual(self.verify("recovery").status_code, 200)
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(
            AccountOtpChallenge.objects.filter(verified_at__isnull=False).exists()
        )

    def test_recovery_success_reset_consumes_grant_and_revokes_old_login(self):
        self.recovery_start()
        logged_in = Client()
        logged_in.force_login(self.user)
        self.assertRedirects(self.verify("recovery"), self.url("recovery") + "?reset=1")
        self.assertEqual(self.challenge("recovery").otp_digest, "")
        self.assertRedirects(
            self.reset(), reverse("login_en"), fetch_redirect_response=False
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Synthetic-replacement-password-912!"))
        self.assertFalse(AccountOtpChallenge.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(
            logged_in.get(reverse("patient_portal_dashboard_en")).status_code, 302
        )
        self.assertRedirects(
            self.reset(password="Replay-password-999!"), self.url("recovery")
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password("Replay-password-999!"))

    def test_recovery_expiry_attempt_limit_and_resend(self):
        self.recovery_start()
        self.client.post(self.url("recovery"), {"action": "resend"})
        self.assertEqual(self.sender.call_count, 1)
        for _ in range(5):
            self.verify("recovery", code="000000")
        self.verify("recovery")
        self.assertIsNone(self.challenge("recovery").verified_at)
        AccountOtpChallenge.objects.update(
            attempt_count=0, expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.verify("recovery")
        self.assertIsNone(self.challenge("recovery").verified_at)

    def test_recovery_grant_expires_and_cannot_move_to_other_session(self):
        self.recovery_start()
        self.verify("recovery")
        other = Client()
        session = other.session
        session[otp.RECOVERY_SESSION_KEY] = str(self.challenge("recovery").pk)
        session[otp.SESSION_BINDING_KEY] = "another-binding"
        session.save()
        self.assertRedirects(self.reset(client=other), self.url("recovery"))
        AccountOtpChallenge.objects.update(
            grant_expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertRedirects(self.reset(), self.url("recovery"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))

    def test_password_change_or_phone_change_or_deactivation_revokes_recovery(self):
        for change in ("password", "username", "is_active", "is_staff", "is_superuser"):
            cache.clear()
            get_user_model().objects.all().delete()
            self.recovery_start()
            self.verify("recovery")
            if change == "password":
                self.user.set_password("Changed-synthetic-password-58!")
            else:
                setattr(
                    self.user,
                    change,
                    "+12025550102" if change == "username" else change != "is_active",
                )
            self.user.save()
            self.assertRedirects(self.reset(), self.url("recovery"))

    def test_recovery_password_validation_and_mismatch_are_localized(self):
        self.recovery_start()
        self.verify("recovery")
        for language in ("ar", "en"):
            response = self.reset(password="123", language=language)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
            self.assertNotContains(response, 'value="123"')
            self.assertContains(
                response, "كلمة المرور" if language == "ar" else "password"
            )
            mismatch = self.client.post(
                self.url("recovery", language),
                {
                    "action": "reset",
                    "new_password1": self.password,
                    "new_password2": "mismatch",
                },
            )
            self.assertContains(
                mismatch, "كلمتا المرور غير متطابقتين." if language == "ar" else "match"
            )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))

    def test_new_recovery_revokes_previous_grant_in_same_session(self):
        self.recovery_start()
        self.verify("recovery")
        old = self.challenge("recovery").pk
        cache.clear()
        self.start("recovery")
        self.assertFalse(AccountOtpChallenge.objects.filter(pk=old).exists())
        self.assertRedirects(self.reset(), self.url("recovery"))

    def test_cache_failure_fails_closed_without_sending_or_creating_state(self):
        with patch(
            "apps.patients.account_otp.cache.add",
            side_effect=RuntimeError("private-cache-sentinel"),
        ):
            for purpose in ("registration", "recovery"):
                response = self.start(purpose)
                self.assertContains(
                    response, "Too many attempts. Please try again later."
                )
                self.assertNotContains(response, "private-cache-sentinel")
        self.sender.assert_not_called()
        self.assertFalse(AccountOtpChallenge.objects.exists())

    def test_rate_limit_is_independent_for_phone_and_ip(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/", REMOTE_ADDR="192.0.2.1")
        self.assertTrue(
            otp.allow_request(request, scope="test", phone=self.phone, limit=1)
        )
        request.META["REMOTE_ADDR"] = "192.0.2.2"
        self.assertFalse(
            otp.allow_request(request, scope="test", phone=self.phone, limit=1)
        )
        request.META["REMOTE_ADDR"] = "192.0.2.1"
        self.assertFalse(
            otp.allow_request(request, scope="test", phone="+12025550109", limit=1)
        )

    def test_reset_rate_limit_returns_localized_error_without_consuming_grant(self):
        self.recovery_start()
        self.verify("recovery")
        # Invalid passwords consume the request budget but leave the grant usable.
        for _ in range(20):
            self.assertEqual(self.reset(password="123").status_code, 200)
        for language in ("ar", "en"):
            response = self.reset(language=language)
            self.assertContains(
                response, account_views.auth_error_message("rate_limit", language)
            )
            self.assertEqual(response.context["recovery_stage"], "reset")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))
        self.assertIsNotNone(self.challenge("recovery").verified_at)
        cache.clear()
        self.assertRedirects(self.reset(), reverse("login_en"))

    def test_cache_outage_blocks_verification_and_reset_without_losing_valid_state(self):
        self.recovery_start()
        with patch(
            "apps.patients.account_otp.cache.add",
            side_effect=RuntimeError("private-cache-sentinel"),
        ):
            response = self.verify("recovery")
        self.assertContains(response, account_views.auth_error_message("rate_limit", "en"))
        self.assertIsNone(self.challenge("recovery").verified_at)
        self.assertEqual(self.challenge("recovery").attempt_count, 0)
        self.verify("recovery")
        with patch(
            "apps.patients.account_otp.cache.add",
            side_effect=RuntimeError("private-cache-sentinel"),
        ):
            for language in ("ar", "en"):
                response = self.reset(language=language)
                self.assertContains(
                    response, account_views.auth_error_message("rate_limit", language)
                )
                self.assertNotContains(response, "private-cache-sentinel")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))
        self.assertIsNotNone(self.challenge("recovery").verified_at)
        self.assertRedirects(self.reset(), reverse("login_en"))

    def test_language_switch_retains_verification_and_reset_stages(self):
        self.start()
        page = self.client.get(self.url() + "?verify=1")
        self.assertEqual(
            page.context["auth_language_url"], self.url(language="ar") + "?verify=1"
        )
        cache.clear()
        self.recovery_start()
        self.verify("recovery")
        page = self.client.get(self.url("recovery") + "?reset=1")
        self.assertEqual(
            page.context["auth_language_url"], self.url("recovery", "ar") + "?reset=1"
        )

    def test_csrf_required_at_every_stage_and_real_token_works(self):
        client = Client(enforce_csrf_checks=True)
        for purpose in ("registration", "recovery"):
            for language in ("ar", "en"):
                for action in ("start", "verify", "resend", "reset"):
                    self.assertEqual(
                        client.post(
                            self.url(purpose, language), {"action": action}
                        ).status_code,
                        403,
                    )
        client.get(self.url())
        response = self.start(
            client=client, csrfmiddlewaretoken=client.cookies["csrftoken"].value
        )
        self.assertEqual(response.status_code, 302)
        response = self.verify(
            client=client, csrfmiddlewaretoken=client.cookies["csrftoken"].value
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.exists())

    def test_sender_fallback_and_bad_import_are_handled(self):
        shared = Mock(return_value=True)
        with self.settings(
            PATIENT_ACCOUNT_OTP_SENDER="", GUEST_CONSULTATION_OTP_SENDER=shared
        ):
            send_patient_account_otp(self.phone, "123456", "ar")
        shared.assert_called_once_with(self.phone, "123456", "ar")
        with self.settings(PATIENT_ACCOUNT_OTP_SENDER="invalid.module.sender"):
            with self.assertRaises(WhatsAppOtpServiceUnavailable):
                send_patient_account_otp(self.phone, "123456", "en")

    def test_private_response_and_no_password_or_otp_in_rendered_page(self):
        self.start()
        page = self.client.get(self.url() + "?verify=1")
        for value in (self.password, "123456", self.challenge().otp_digest):
            self.assertNotContains(page, value)
        for directive in ("private", "no-store", "no-cache"):
            self.assertIn(directive, page.headers["Cache-Control"])
