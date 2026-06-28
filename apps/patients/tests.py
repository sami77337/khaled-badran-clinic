
from django.test import TestCase

from .models import Patient


class PatientModelTests(TestCase):
    def test_patient_stores_raw_and_normalized_phone_placeholders(self):
        patient = Patient.objects.create(
            full_name="Test Patient",
            phone_raw="0790000000",
            phone_e164="+962790000000",
            whatsapp_phone_raw="0790000000",
            whatsapp_phone_e164="+962790000000",
        )

        self.assertEqual(patient.phone_raw, "0790000000")
        self.assertEqual(patient.phone_e164, "+962790000000")
        self.assertEqual(patient.whatsapp_phone_raw, "0790000000")
        self.assertEqual(patient.whatsapp_phone_e164, "+962790000000")
