"""Exercise one-time consumption against real database row locks."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db import close_old_connections
from django.test import (
    RequestFactory,
    TransactionTestCase,
    override_settings,
    skipUnlessDBFeature,
)

from . import account_otp as otp
from .account_views import _localized_set_password_form
from .models import AccountOtpChallenge


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
@skipUnlessDBFeature("has_select_for_update")
class AccountOtpConcurrencyTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.request = RequestFactory().post("/")
        self.request.session = {}

    def start(self, purpose):
        with override_settings(PATIENT_ACCOUNT_OTP_SENDER=Mock(return_value=True)):
            with patch(
                "apps.patients.account_otp.generate_otp_code", return_value="123456"
            ):
                otp.start(
                    self.request,
                    purpose,
                    "+12025550101",
                    "en",
                    registration={
                        "full_name": "Synthetic concurrency",
                        "email": "",
                        "password_hash": make_password("Synthetic-pass-987!"),
                    }
                    if purpose == "registration"
                    else None,
                )

    def race(self, operation):
        barrier = Barrier(2)
        session_data = dict(self.request.session)

        def worker():
            close_old_connections()
            try:
                request = RequestFactory().post("/")
                request.session = dict(session_data)
                barrier.wait(timeout=10)
                return operation(request)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(worker) for _ in range(2)]
            return [future.result(timeout=15) for future in futures]

    def test_concurrent_registration_verification_creates_exactly_one_user(self):
        self.start("registration")
        results = self.race(
            lambda request: bool(otp.verify(request, "registration", "123456"))
        )
        self.assertCountEqual(results, [True, False])
        self.assertEqual(
            get_user_model().objects.filter(username="+12025550101").count(), 1
        )
        self.assertFalse(AccountOtpChallenge.objects.exists())

    def test_concurrent_password_reset_consumes_grant_exactly_once(self):
        user = get_user_model().objects.create_user(
            username="+12025550101", password="Synthetic-original-456!"
        )
        self.start("recovery")
        self.assertIsNotNone(otp.verify(self.request, "recovery", "123456"))
        data = {
            "new_password1": "Synthetic-replacement-987!",
            "new_password2": "Synthetic-replacement-987!",
        }
        results = self.race(
            lambda request: otp.reset_password(
                request, data, _localized_set_password_form, "en"
            )[1]
        )
        self.assertCountEqual(results, [True, False])
        self.assertFalse(AccountOtpChallenge.objects.exists())
        user.refresh_from_db()
        self.assertTrue(user.check_password(data["new_password1"]))
