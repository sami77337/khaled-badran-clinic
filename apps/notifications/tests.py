"""Synthetic credentials are generated in memory; no live provider requests."""
import base64
from copy import deepcopy
from datetime import time, timedelta
import json
import logging
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection, transaction
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pywebpush import WebPushException
from requests import Response

from apps.booking.models import Appointment
from apps.booking.services import create_public_appointment
from apps.clinic.models import Doctor, DoctorSchedule, VisitType
from apps.patients import consultation_services, transient_services
from apps.patients.models import Consultation, ConsultationNotification, Patient, TransientConsultationChallenge
from .logging import PushPrivacyFilter, push_delivery_in_progress
from .models import StaffPushSubscription
from .services import PushSession, deliver_staff_event, event_payload, schedule_staff_event, vapid_credentials
from .validation import validate_subscription


def encode(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def synthetic_keys():
    key = ec.generate_private_key(ec.SECP256R1())
    public = encode(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    private = encode(key.private_numbers().private_value.to_bytes(32, "big"))
    return public, private


class PushFixture:
    def setUp(self):
        super().setUp()
        cache.clear()
        public, private = synthetic_keys()
        self.config = override_settings(WEB_PUSH_ENABLED=True, WEB_PUSH_VAPID_PUBLIC_KEY=public,
            WEB_PUSH_VAPID_PRIVATE_KEY=private, WEB_PUSH_VAPID_SUBJECT="mailto:synthetic@example.test")
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.staff = get_user_model().objects.create_user(username="push-staff", is_staff=True)
        self.other_staff = get_user_model().objects.create_user(username="push-other-staff", is_staff=True)
        self.patient_user = get_user_model().objects.create_user(username="push-patient")
        self.patient = Patient.objects.create(user=self.patient_user, full_name="Synthetic Private Name", phone_e164="+12025550101")
        self.payload = {"subscription": {"endpoint": "https://fcm.googleapis.com/wp/synthetic-device",
            "keys": {"auth": encode(b"synthetic-secret"), "p256dh": synthetic_keys()[0]}, "expirationTime": None}, "language": "ar"}

    def subscription(self, user=None, endpoint=None, language="ar"):
        values = validate_subscription(self.payload)
        values["endpoint"] = endpoint or values["endpoint"]
        values["language"] = language
        return StaffPushSubscription.objects.create(user=user or self.staff, **values)

    def post(self, name, payload=None, client=None, **kwargs):
        return (client or self.client).post(reverse(name), payload if payload is not None else self.payload,
            content_type="application/json", **kwargs)


class SubscriptionTests(PushFixture, TestCase):
    def test_staff_only_and_post_only(self):
        for user, expected in ((None, 401), (self.patient_user, 403), (self.staff, 200)):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for route, data in (("staff_push_subscribe", self.payload), ("staff_push_status", {"endpoint": self.payload["subscription"]["endpoint"]}),
                    ("staff_push_unsubscribe", {"endpoint": self.payload["subscription"]["endpoint"]})):
                with self.subTest(user=user, route=route):
                    self.assertEqual(self.post(route, data).status_code, expected)
            self.assertEqual(self.client.get(reverse("staff_push_config")).status_code, expected)
        for name in ("staff_push_subscribe", "staff_push_unsubscribe", "staff_push_status"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 405)
            self.assertEqual(self.client.delete(reverse(name)).status_code, 405)

    def test_inactive_staff_cannot_subscribe(self):
        self.staff.is_active = False
        self.staff.save()
        self.client.force_login(self.staff)
        self.assertEqual(self.post("staff_push_subscribe").status_code, 401)
        self.assertEqual(StaffPushSubscription.objects.count(), 0)

    def test_csrf_required_including_cross_origin_and_unsubscribe(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        client.get(reverse("dashboard_home"))
        token = client.cookies["csrftoken"].value
        for name in ("staff_push_subscribe", "staff_push_unsubscribe", "staff_push_status"):
            data = self.payload if name == "staff_push_subscribe" else {"endpoint": self.payload["subscription"]["endpoint"]}
            self.assertEqual(self.post(name, data, client=client).status_code, 403)
            self.assertEqual(self.post(name, data, client=client, HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://evil.example").status_code, 403)
            self.assertEqual(self.post(name, data, client=client, HTTP_X_CSRFTOKEN=token).status_code, 200)
        client.logout()
        client.cookies["csrftoken"] = token
        self.assertEqual(self.post("staff_push_subscribe", client=client, HTTP_X_CSRFTOKEN=token).status_code, 401)

    def test_idempotent_subscription_and_user_scoped_removal(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.post("staff_push_subscribe").status_code, 200)
        self.payload["language"] = "en"
        self.assertEqual(self.post("staff_push_subscribe").status_code, 200)
        stored = StaffPushSubscription.objects.get()
        self.assertEqual((stored.user, stored.language), (self.staff, "en"))
        self.client.force_login(self.other_staff)
        self.assertEqual(self.post("staff_push_subscribe").status_code, 409)
        endpoint = {"endpoint": stored.endpoint}
        self.assertEqual(self.post("staff_push_status", endpoint).json(), {"subscribed": False})
        self.assertEqual(self.post("staff_push_unsubscribe", endpoint).status_code, 200)
        self.assertTrue(StaffPushSubscription.objects.filter(pk=stored.pk).exists())
        self.client.force_login(self.staff)
        self.assertEqual(self.post("staff_push_status", endpoint).json(), {"subscribed": True})
        for _ in range(2):
            self.assertEqual(self.post("staff_push_unsubscribe", endpoint).json(), {"subscribed": False})
        self.assertEqual(StaffPushSubscription.objects.count(), 0)

    def test_concurrent_other_user_insert_does_not_transfer_ownership(self):
        self.client.force_login(self.staff)
        other = self.subscription(user=self.other_staff)
        with patch("apps.notifications.views.StaffPushSubscription.objects.filter") as filtered:
            filtered.return_value.first.return_value = None
            filtered.return_value.count.return_value = 0
            self.assertEqual(self.post("staff_push_subscribe").status_code, 409)
        other.refresh_from_db()
        self.assertEqual(other.user, self.other_staff)

    def test_device_limit_allows_existing_subscription_refresh(self):
        self.client.force_login(self.staff)
        for index in range(10):
            self.subscription(endpoint=f"https://fcm.googleapis.com/wp/synthetic-{index}")
        self.assertEqual(self.post("staff_push_subscribe").status_code, 409)
        self.payload["subscription"]["endpoint"] = "https://fcm.googleapis.com/wp/synthetic-0"
        self.assertEqual(self.post("staff_push_subscribe").status_code, 200)

    def test_invalid_payloads_do_not_persist_or_echo_secrets(self):
        self.client.force_login(self.staff)
        bad_payloads = [None, [], {}, {**self.payload, "user_id": self.other_staff.pk},
            {**self.payload, "language": "fr"}, {**self.payload, "language": []}, {**self.payload, "subscription": []}]
        for path, value in [
            (("subscription", "endpoint"), "http://fcm.googleapis.com/wp/secret"),
            (("subscription", "endpoint"), "https://127.0.0.1/private"),
            (("subscription", "endpoint"), "https://169.254.169.254/latest/meta-data/"),
            (("subscription", "endpoint"), "https://fcm.googleapis.com.evil.test/private"),
            (("subscription", "endpoint"), "https://fcm.googleapis.com@evil.test/private"),
            (("subscription", "endpoint"), "https://fcm.googleapis.com:8443/private"),
            (("subscription", "endpoint"), "https://fcm.googleapis.com/wp/secret#fragment"),
            (("subscription", "endpoint"), "https://fcm.googleapis.com/\nprivate"),
            (("subscription", "endpoint"), "https://fcm.googleapis.com/" + "a" * 2048),
            (("subscription", "endpoint"), {}),
            (("subscription", "keys"), []),
            (("subscription", "keys", "auth"), "not-a-key"),
            (("subscription", "keys", "p256dh"), encode(b"x" * 65)),
            (("subscription", "keys", "p256dh"), "!" * 87),
            (("subscription", "expirationTime"), "medical-secret"),
            (("subscription", "expirationTime"), True),
            (("subscription", "expirationTime"), -1),
            (("subscription", "expirationTime"), float("inf")),
            (("subscription", "notes"), "private medical secret"),
        ]:
            data = deepcopy(self.payload)
            target = data
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = value
            bad_payloads.append(data)
        for data in bad_payloads:
            response = self.client.post(reverse("staff_push_subscribe"), json.dumps(data), content_type="application/json")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), {"error": "invalid_subscription"})
        for raw in ("{", "x" * 4097, "[" * 1500 + "]" * 1500):
            self.assertEqual(self.client.post(reverse("staff_push_subscribe"), raw, content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(reverse("staff_push_subscribe"), {"endpoint": "secret"}).status_code, 400)
        self.assertFalse(StaffPushSubscription.objects.exists())

    def test_supported_transports_and_strict_unsubscribe_body(self):
        self.client.force_login(self.staff)
        for host in ("fcm.googleapis.com", "web.push.apple.com", "updates.push.services.mozilla.com"):
            self.payload["subscription"]["endpoint"] = f"https://{host}/synthetic-device"
            self.assertEqual(self.post("staff_push_subscribe").status_code, 200)
        for data in ({}, {"endpoint": "http://localhost/secret"}, {"endpoint": [], "user": self.staff.pk}):
            self.assertEqual(self.post("staff_push_unsubscribe", data).status_code, 400)

    def test_config_only_exposes_public_key_and_no_cache(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("staff_push_config"))
        self.assertEqual(response.json(), {"available": True, "publicKey": settings.WEB_PUSH_VAPID_PUBLIC_KEY})
        self.assertNotContains(response, settings.WEB_PUSH_VAPID_PRIVATE_KEY)
        self.assertIn("no-store", response["Cache-Control"])
        with override_settings(WEB_PUSH_ENABLED=False):
            self.assertEqual(self.client.get(reverse("staff_push_config")).json(), {"available": False, "publicKey": ""})
            self.assertEqual(self.post("staff_push_subscribe").status_code, 503)
            self.assertEqual(self.post("staff_push_unsubscribe", {"endpoint": self.payload["subscription"]["endpoint"]}).status_code, 200)

    def test_database_failure_returns_generic_api_error(self):
        self.client.force_login(self.staff)
        with patch("apps.notifications.views.StaffPushSubscription.objects.get_or_create", side_effect=RuntimeError("secret keys")):
            response = self.post("staff_push_subscribe")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "unavailable"})

    def test_dashboard_ar_en_and_protected_notification_destinations(self):
        for route in ("dashboard_consultation_list", "staff_appointment_list"):
            self.assertEqual(self.client.get(reverse(route)).status_code, 302)
            self.client.force_login(self.patient_user)
            self.assertEqual(self.client.get(reverse(route)).status_code, 403)
            self.client.logout()
        self.client.force_login(self.staff)
        for language, direction, enable, disable in (
            ("ar", "rtl", "تفعيل إشعارات الهاتف", "إيقاف إشعارات الهاتف"),
            ("en", "ltr", "Enable phone notifications", "Disable phone notifications"),
        ):
            response = self.client.get(reverse("dashboard_home") + ("?lang=en" if language == "en" else ""))
            self.assertContains(response, f'lang="{language}" dir="{direction}"')
            for text in (enable, disable, 'data-phone-enable disabled', 'data-phone-disable hidden', 'role="status"', 'site.webmanifest'):
                self.assertContains(response, text)
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("home")), 'data-phone-notifications')
        self.client.force_login(self.patient_user)
        self.assertNotContains(self.client.get(reverse("patient_portal_dashboard")), 'data-phone-notifications')

    def test_worker_is_public_root_scoped_and_revalidated(self):
        response = self.client.get(reverse("service_worker"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertEqual(response["Content-Type"], "text/javascript")
        body = b"".join(response.streaming_content)
        response.close()
        self.assertIn(b'notificationclick', body)
        self.assertNotIn(b'caches.', body)


class DeliveryTests(PushFixture, TestCase):
    def test_valid_environment_keypair_and_fail_closed_configuration(self):
        self.assertIsNotNone(vapid_credentials())
        for values in ({"WEB_PUSH_ENABLED": False}, {"WEB_PUSH_VAPID_PRIVATE_KEY": "private.pem"},
                {"WEB_PUSH_VAPID_PUBLIC_KEY": synthetic_keys()[0]}, {"WEB_PUSH_VAPID_SUBJECT": "invalid"},
                {"WEB_PUSH_VAPID_SUBJECT": "mailto:@"}):
            with override_settings(**values), patch("apps.notifications.services.webpush") as send:
                self.assertIsNone(vapid_credentials())
                deliver_staff_event("new-consultation")
                send.assert_not_called()

    def test_minimal_payloads_collapse_topics_and_active_staff_only(self):
        self.subscription()
        self.subscription(self.other_staff, "https://web.push.apple.com/synthetic", "en")
        self.subscription(self.patient_user, "https://fcm.googleapis.com/wp/patient")
        inactive = get_user_model().objects.create_user(username="inactive", is_staff=True, is_active=False)
        self.subscription(inactive, "https://fcm.googleapis.com/wp/inactive")
        with patch("apps.notifications.services.webpush") as send:
            for event in ("new-consultation", "new-consultation", "new-booking", "new-booking"):
                deliver_staff_event(event)
            self.assertEqual(send.call_count, 8)
            for call in send.call_args_list:
                values = call.kwargs
                payload = json.loads(values["data"])
                self.assertEqual(set(payload), {"event", "language"})
                self.assertEqual(values["headers"], {"Topic": "kbc-" + payload["event"], "Urgency": "normal"})
                self.assertEqual(values["timeout"], 3)
                self.assertEqual(values["ttl"], 3600)
                self.assertNotIn(self.patient.full_name, values["data"])
                self.assertNotIn(self.patient.phone_e164, values["data"])
            self.assertIsNot(send.call_args_list[0].kwargs["vapid_claims"], send.call_args_list[1].kwargs["vapid_claims"])
        for event in ("reply", "read", "status", "navigation", "profile", "crud"):
            with self.assertRaises(ValueError):
                event_payload(event, "ar")
            with self.assertRaises(ValueError):
                schedule_staff_event(event)

    def test_removed_staff_role_stops_delivery(self):
        self.subscription()
        self.staff.is_staff = False
        self.staff.save()
        with patch("apps.notifications.services.webpush") as send:
            deliver_staff_event("new-booking")
            send.assert_not_called()

    def test_real_webpush_encrypts_and_signs_with_mocked_http_transport(self):
        self.subscription()
        response = Response()
        response.status_code = 202
        response._content = b""
        with patch("requests.Session.request", return_value=response) as request:
            deliver_staff_event("new-consultation")
        request.assert_called_once()
        values = request.call_args.kwargs
        self.assertEqual(values["headers"]["content-encoding"], "aes128gcm")
        self.assertTrue(values["headers"]["Authorization"].startswith("vapid "))
        self.assertEqual(values["headers"]["Topic"], "kbc-new-consultation")
        self.assertIs(values["allow_redirects"], False)
        self.assertIsInstance(values["data"], bytes)
        self.assertNotIn(b"new-consultation", values["data"])

    def test_404_and_410_cleanup_but_transient_failures_preserve_subscription(self):
        for status in (404, 410, 400, 401, 403, 429, 500, 503):
            with self.subTest(status=status):
                stored = self.subscription(endpoint=f"https://fcm.googleapis.com/wp/{status}")
                response = Response()
                response.status_code = status
                response._content = b"PRIVATE provider response"
                with patch("apps.notifications.services.webpush", side_effect=WebPushException("PRIVATE error", response=response)):
                    deliver_staff_event("new-booking")
                self.assertEqual(StaffPushSubscription.objects.filter(pk=stored.pk).exists(), status not in (404, 410))
                StaffPushSubscription.objects.all().delete()

    def test_provider_failure_continues_other_devices_and_never_logs_details(self):
        self.subscription()
        self.subscription(self.other_staff, "https://web.push.apple.com/synthetic")
        with patch("apps.notifications.services.webpush", side_effect=[RuntimeError("PRIVATE endpoint auth payload"), None]) as send:
            with self.assertNoLogs("apps.notifications", level="DEBUG"):
                deliver_staff_event("new-consultation")
            self.assertEqual(send.call_count, 2)

    def test_cleanup_does_not_delete_refreshed_subscription(self):
        stored = self.subscription()
        def stale_response(**kwargs):
            stored.save()
            response = Response()
            response.status_code = 410
            raise WebPushException("expired", response=response)
        with patch("apps.notifications.services.webpush", side_effect=stale_response):
            deliver_staff_event("new-booking")
        self.assertTrue(StaffPushSubscription.objects.filter(pk=stored.pk).exists())

    def test_transport_blocks_redirects_and_untrusted_database_endpoints(self):
        with PushSession() as session, patch("requests.Session.request", return_value=Mock(status_code=302)) as request:
            session.post(self.payload["subscription"]["endpoint"], data=b"encrypted")
            self.assertIs(request.call_args.kwargs["allow_redirects"], False)
            with self.assertRaises(ValueError):
                session.post("https://127.0.0.1/private")
        self.subscription(endpoint="https://127.0.0.1/private")
        with patch("apps.notifications.services.webpush") as send:
            deliver_staff_event("new-booking")
            send.assert_not_called()

    def test_privacy_filter_covers_transport_sql_and_request_error_logs(self):
        privacy = PushPrivacyFilter()
        def record(name, message):
            return logging.LogRecord(name, logging.DEBUG, "", 1, message, (), None)
        sql = record("django.db.backends", "INSERT INTO notifications_staffpushsubscription PRIVATE KEYS")
        self.assertFalse(privacy.filter(sql))
        self.assertTrue(privacy.filter(record("django.db.backends", "SELECT 1")))
        error = record("django.request", "error")
        error.request = RequestFactory().post(reverse("staff_push_subscribe"))
        self.assertFalse(privacy.filter(error))
        token = push_delivery_in_progress.set(True)
        try:
            for name in ("urllib3.connectionpool", "pywebpush", "py_vapid", "root"):
                self.assertFalse(privacy.filter(record(name, "PRIVATE response endpoint key payload")))
        finally:
            push_delivery_in_progress.reset(token)
        self.assertIn("push_privacy", settings.LOGGING["handlers"]["console"]["filters"])


class CreationTests(PushFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.subscription()
        self.doctor = Doctor.objects.create(full_name_ar="طبيب تجريبي", full_name_en="Synthetic Doctor", is_active=True)
        self.visit_type = VisitType.objects.create(doctor=self.doctor, name_ar="زيارة", name_en="Visit", duration_minutes=30, is_active=True)
        self.starts_at = timezone.localtime().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=2)
        DoctorSchedule.objects.create(doctor=self.doctor, weekday=self.starts_at.weekday(), start_time=time(9), end_time=time(13))
        self.request = RequestFactory().get("/")
        self.request.session = {transient_services.SESSION_KEY: "synthetic-browser-secret"}
        TransientConsultationChallenge.objects.create(
            session_digest=transient_services.session_digest(self.request), phone_e164="+12025550102",
            otp_digest="", expires_at=timezone.now() + timedelta(minutes=10),
            verified_at=timezone.now(), grant_expires_at=timezone.now() + timedelta(hours=1))

    def create(self, kind):
        if kind == "registered":
            return consultation_services.create_consultation(user=self.patient_user, question="PRIVATE diagnosis treatment question", uploaded_files=[])
        if kind == "guest":
            return transient_services.create_guest_consultation(self.request, question="PRIVATE guest medical text", display_name="PRIVATE guest name", uploaded_files=[], language="en")
        return create_public_appointment(full_name="PRIVATE booking name", phone_raw="+12025550103", visit_type_id=self.visit_type.pk,
            starts_at=self.starts_at, booking_note="PRIVATE medical booking notes", language="en")

    def test_each_creation_delivers_only_after_outer_commit_with_no_private_payload(self):
        for kind in ("registered", "guest", "booking"):
            with self.subTest(kind=kind), patch("apps.notifications.services.webpush") as send:
                with transaction.atomic():
                    created = self.create(kind)
                    send.assert_not_called()
                    self.assertTrue(type(created).objects.filter(pk=created.pk).exists())
                send.assert_called_once()
                self.assertFalse(connection.in_atomic_block)
                self.assertEqual(json.loads(send.call_args.kwargs["data"]), {
                    "event": "new-booking" if kind == "booking" else "new-consultation", "language": "ar",
                })
        self.assertEqual(ConsultationNotification.objects.filter(kind=ConsultationNotification.Kind.NEW_CONSULTATION).count(), 2)

    def test_each_creation_rollback_discards_push(self):
        for kind in ("registered", "guest", "booking"):
            with self.subTest(kind=kind), patch("apps.notifications.services.webpush") as send:
                with self.assertRaises(RuntimeError):
                    with transaction.atomic():
                        created = self.create(kind)
                        raise RuntimeError("synthetic transaction rollback")
                send.assert_not_called()
                self.assertFalse(type(created).objects.filter(pk=created.pk).exists())
        self.assertFalse(ConsultationNotification.objects.exists())

    def test_provider_failure_cannot_break_any_creation(self):
        for kind in ("registered", "guest", "booking"):
            with self.subTest(kind=kind), patch("apps.notifications.services.webpush", side_effect=RuntimeError("PRIVATE provider body")):
                created = self.create(kind)
                self.assertTrue(type(created).objects.filter(pk=created.pk).exists())

    def test_callback_itself_cannot_break_committed_creation(self):
        with patch("apps.notifications.services.deliver_staff_event", side_effect=RuntimeError("PRIVATE")):
            with self.assertLogs("apps.notifications.services", level="WARNING") as logs:
                created = self.create("registered")
        self.assertTrue(Consultation.objects.filter(pk=created.pk).exists())
        self.assertNotIn("PRIVATE", " ".join(logs.output))

    def test_guest_without_verified_grant_does_not_push(self):
        TransientConsultationChallenge.objects.update(verified_at=None)
        with patch("apps.notifications.services.webpush") as send:
            with self.assertRaises(transient_services.GuestAccessDenied):
                self.create("guest")
            send.assert_not_called()

    def test_public_submission_views_return_success_during_provider_failure(self):
        with patch("apps.notifications.services.webpush", side_effect=RuntimeError("PRIVATE")) as send:
            self.client.force_login(self.patient_user)
            response = self.client.post(reverse("patient_portal_consultation_new"), {"question": "Synthetic private question"})
            self.assertEqual(response.status_code, 302)
            self.client.logout()
            session = self.client.session
            session[transient_services.SESSION_KEY] = self.request.session[transient_services.SESSION_KEY]
            session.save()
            response = self.client.post(reverse("guest_consultation_entry"), {
                "action": "submit", "display_name": "Synthetic Guest", "question": "Synthetic private question"})
            self.assertEqual(response.status_code, 302)
            response = self.client.post(reverse("booking_confirm"), {
                "full_name": "Synthetic Booking", "phone": "+12025550103", "same_as_phone": "on",
                "visit_type": self.visit_type.pk, "starts_at": self.starts_at.isoformat(), "booking_note": "Synthetic private note"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(send.call_count, 3)

    def test_routine_actions_remain_silent(self):
        consultation = self.create("registered")
        appointment = self.create("booking")
        with patch("apps.notifications.services.webpush") as send:
            self.client.force_login(self.staff)
            self.assertEqual(self.client.get(reverse("dashboard_home")).status_code, 200)
            self.assertEqual(self.client.get(reverse("dashboard_consultation_list")).status_code, 200)
            self.client.post(reverse("consultation_notifications_mark_all_read"))
            ConsultationNotification.objects.update(read_at=None)
            consultation_services.update_consultation_reply(consultation=consultation, staff_user=self.staff, reply="Synthetic medical reply", status=Consultation.Status.ANSWERED)
            appointment.status = Appointment.Status.COMPLETED
            appointment.save()
            self.patient.full_name = "Synthetic edited profile"
            self.patient.save()
            Consultation.objects.create(patient=self.patient, question="Synthetic routine CRUD")
            send.assert_not_called()
