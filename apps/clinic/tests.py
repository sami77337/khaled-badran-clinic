
from decimal import Decimal

from django.test import TestCase

from .models import Doctor, VisitType


class VisitTypeModelTests(TestCase):
    def test_price_is_visible_only_when_enabled_and_present(self):
        visit_type = VisitType.objects.create(
            name_ar="كشف جديد",
            name_en="New consultation",
            duration_minutes=30,
            price=Decimal("25.00"),
            show_price_to_patient=True,
        )

        self.assertTrue(visit_type.is_price_visible_to_patient)
        self.assertEqual(visit_type.patient_visible_price, Decimal("25.00"))

    def test_price_is_hidden_when_visibility_flag_is_disabled(self):
        visit_type = VisitType.objects.create(
            name_ar="مراجعة",
            name_en="Follow-up",
            duration_minutes=15,
            price=Decimal("15.00"),
            show_price_to_patient=False,
        )

        self.assertFalse(visit_type.is_price_visible_to_patient)
        self.assertIsNone(visit_type.patient_visible_price)

    def test_missing_price_is_not_visible_to_patient(self):
        visit_type = VisitType.objects.create(
            name_ar="استشارة",
            name_en="Consultation",
            duration_minutes=30,
            show_price_to_patient=True,
        )

        self.assertFalse(visit_type.is_price_visible_to_patient)
        self.assertIsNone(visit_type.patient_visible_price)


class DoctorModelTests(TestCase):
    def test_doctor_has_arabic_and_english_display_names(self):
        doctor = Doctor.objects.create(
            full_name_ar="خالد حسان بدران",
            full_name_en="Khaled Hassan Badran",
            title_ar="د.",
            title_en="Dr.",
        )

        self.assertEqual(doctor.display_name_ar, "د. خالد حسان بدران")
        self.assertEqual(doctor.display_name_en, "Dr. Khaled Hassan Badran")
