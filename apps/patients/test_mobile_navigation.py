import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.patients.models import Consultation, ConsultationNotification, Patient


class MobileDashboardNavigationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.patient_user = user_model.objects.create_user(username="mobile-nav-patient")
        self.staff = user_model.objects.create_user(username="mobile-nav-staff", is_staff=True)
        self.patient = Patient.objects.create(
            user=self.patient_user,
            full_name="Synthetic Mobile Navigation Patient",
            phone_raw="+962700000201",
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            question="Synthetic mobile navigation consultation",
        )

    def mobile_nav(self, response, scope):
        match = re.search(
            rf'<nav[^>]+data-mobile-bottom-navigation="{scope}".*?</nav>',
            response.content.decode(),
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        return match.group(0)

    def test_patient_navigation_has_exact_actions_canonical_book_and_drawer_reuse(self):
        self.client.force_login(self.patient_user)
        english = self.client.get(reverse("patient_portal_dashboard_en"))
        navigation = self.mobile_nav(english, "patient")

        self.assertEqual(navigation.count("data-mobile-nav-item="), 5)
        for key, label in (
            ("home", "Home"),
            ("appointments", "Appointments"),
            ("book", "Book"),
            ("consultations", "Consultations"),
            ("more", "More"),
        ):
            with self.subTest(key=key):
                self.assertIn(f'data-mobile-nav-item="{key}"', navigation)
                self.assertIn(label, navigation)
        self.assertIn(f'href="{reverse("book_en")}"', navigation)
        self.assertIn('aria-controls="patient-portal-sidebar"', navigation)
        self.assertIn("data-dashboard-menu", navigation)
        self.assertEqual(english.content.decode().count("data-dashboard-menu"), 2)
        self.assertContains(english, 'id="patient-portal-sidebar"', count=1)
        self.assertRegex(
            navigation,
            r'class="dashboard-mobile-nav-item is-active"[^>]+data-mobile-nav-item="home"',
        )

    def test_staff_navigation_has_exact_actions_and_drawer_reuse(self):
        self.client.force_login(self.staff)
        english = self.client.get(f'{reverse("dashboard_home")}?lang=en')
        navigation = self.mobile_nav(english, "staff")

        self.assertEqual(navigation.count("data-mobile-nav-item="), 5)
        for key, label in (
            ("home", "Home"),
            ("appointments", "Appointments"),
            ("consultations", "Consultations"),
            ("patients", "Patients"),
            ("more", "More"),
        ):
            with self.subTest(key=key):
                self.assertIn(f'data-mobile-nav-item="{key}"', navigation)
                self.assertIn(label, navigation)
        self.assertIn('aria-controls="dashboard-sidebar"', navigation)
        self.assertIn("data-dashboard-menu", navigation)
        self.assertEqual(english.content.decode().count("data-dashboard-menu"), 2)
        self.assertContains(english, 'id="dashboard-sidebar"', count=1)
        self.assertRegex(
            navigation,
            r'class="dashboard-mobile-nav-item is-active"[^>]+data-mobile-nav-item="home"',
        )

    def test_arabic_labels_rtl_and_english_labels_ltr(self):
        self.client.force_login(self.patient_user)
        arabic = self.client.get(reverse("patient_portal_dashboard"))
        english = self.client.get(reverse("patient_portal_dashboard_en"))
        arabic_nav = self.mobile_nav(arabic, "patient")
        english_nav = self.mobile_nav(english, "patient")
        self.assertContains(arabic, '<html lang="ar" dir="rtl">')
        self.assertContains(english, '<html lang="en" dir="ltr">')
        for label in ("الرئيسية", "المواعيد", "حجز موعد", "الاستشارات", "المزيد"):
            self.assertIn(label, arabic_nav)
        for label in ("Home", "Appointments", "Book", "Consultations", "More"):
            self.assertIn(label, english_nav)

        self.client.force_login(self.staff)
        staff_ar = self.mobile_nav(self.client.get(reverse("dashboard_home")), "staff")
        staff_en = self.mobile_nav(
            self.client.get(f'{reverse("dashboard_home")}?lang=en'),
            "staff",
        )
        for label in ("الرئيسية", "المواعيد", "الاستشارات", "المرضى", "المزيد"):
            self.assertIn(label, staff_ar)
        for label in ("Home", "Appointments", "Consultations", "Patients", "More"):
            self.assertIn(label, staff_en)

    def test_consultation_badges_use_server_count_in_bottom_and_sidebar_navigation(self):
        ConsultationNotification.objects.create(
            recipient=self.patient_user,
            consultation=self.consultation,
            kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
        )
        self.client.force_login(self.patient_user)
        response = self.client.get(reverse("patient_portal_consultation_list_en"))
        navigation = self.mobile_nav(response, "patient")
        self.assertIn("dashboard-navigation-badge", navigation)
        self.assertContains(response, "dashboard-navigation-badge", count=2)
        self.assertRegex(
            navigation,
            r'class="dashboard-mobile-nav-item is-active"[^>]+data-mobile-nav-item="consultations"',
        )

        staff_notification = ConsultationNotification.objects.create(
            recipient=self.staff,
            consultation=self.consultation,
            kind=ConsultationNotification.Kind.NEW_CONSULTATION,
        )
        self.client.force_login(self.staff)
        staff_response = self.client.get(reverse("dashboard_consultation_list"))
        staff_navigation = self.mobile_nav(staff_response, "staff")
        self.assertIn(str(staff_notification.public_id), staff_response.content.decode())
        self.assertIn("dashboard-navigation-badge", staff_navigation)
        self.assertContains(staff_response, "dashboard-navigation-badge", count=2)

    def test_mobile_header_order_and_shared_notification_component(self):
        self.client.force_login(self.patient_user)
        response = self.client.get(reverse("patient_portal_dashboard_en"))
        html = response.content.decode()
        header = re.search(r'<header class="dashboard-mobile-header.*?</header>', html, re.DOTALL)
        self.assertIsNotNone(header)
        header_html = header.group(0)
        notification_trigger = "consultation-notification-trigger-patient-mobile"
        self.assertLess(header_html.index("dashboard-mobile-brand"), header_html.index(notification_trigger))
        self.assertLess(header_html.index(notification_trigger), header_html.index("dashboard-menu-button"))
        self.assertContains(response, "data-consultation-notifications", count=2)

    def test_phone_only_css_preserves_tablet_desktop_shell_and_content_clearance(self):
        stylesheet = (settings.BASE_DIR / "static" / "css" / "portal-chrome.css").read_text(
            encoding="utf-8"
        )
        dashboard_javascript = (
            settings.BASE_DIR / "static" / "js" / "dashboard.js"
        ).read_text(encoding="utf-8")
        public_stylesheet = (settings.BASE_DIR / "static" / "css" / "public.css").read_text(
            encoding="utf-8"
        )
        self.assertRegex(
            stylesheet,
            r"\.dashboard-mobile-bottom-nav\s*\{\s*display:\s*none;",
        )
        self.assertIn("@media (max-width: 40rem)", stylesheet)
        self.assertIn("env(safe-area-inset-bottom)", stylesheet)
        self.assertIn("padding-block-end", stylesheet)
        self.assertIn("grid-template-columns: repeat(5, minmax(0, 1fr))", stylesheet)
        self.assertIn('[data-mobile-bottom-navigation="patient"]', stylesheet)
        self.assertIn('[data-mobile-nav-item="book"]', stylesheet)
        self.assertIn('[data-mobile-nav-item="more"]::before', stylesheet)
        self.assertIn('[data-mobile-nav-item="more"] > *', stylesheet)
        self.assertIn("scrollbar-width: none", stylesheet)
        self.assertIn('document.querySelectorAll("[data-dashboard-menu]")', dashboard_javascript)
        self.assertIn("setTriggerState", dashboard_javascript)
        self.assertIn("@media (max-width: 767px)", public_stylesheet)
        self.assertIn("backdrop-filter: none", public_stylesheet)
        self.assertIn(".header-inner.has-auth-notifications .brand-name", public_stylesheet)
        self.assertIn(".mobile-drawer-backdrop", public_stylesheet)

        notification_javascript = (
            settings.BASE_DIR / "static" / "js" / "consultation-notifications.js"
        ).read_text(encoding="utf-8")
        self.assertIn('event.key !== "Escape"', notification_javascript)
        self.assertIn("root.contains(event.target)", notification_javascript)
        self.assertIn('trigger.setAttribute("aria-expanded"', notification_javascript)
