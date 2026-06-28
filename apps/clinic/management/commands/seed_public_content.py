from django.core.management.base import BaseCommand

from apps.clinic.models import ClinicProfile, Doctor, VisitType


CLINIC_DATA = {
    "official_name_ar": "عيادة الدكتور خالد بدران",
    "official_name_en": "Dr. Khaled Badran Clinic",
    "phone_raw": "+962 7X XXX XXXX",
    "address_ar": "العنوان سيضاف بعد اعتماده",
    "address_en": "Address placeholder pending approval",
    "is_active": True,
}

DOCTOR_DATA = {
    "full_name_ar": "خالد حسان بدران",
    "full_name_en": "Khaled Hassan Badran",
    "title_ar": "د.",
    "title_en": "Dr.",
    "specialty_ar": "استشاري الأنف والأذن والحنجرة",
    "specialty_en": "ENT consultant",
    "bio_ar": (
        "نبذة تعريفية أولية للدكتور خالد بدران. "
        "تفاصيل المؤهلات والخبرة والعضويات المهنية تحتاج تدقيقاً قبل النشر النهائي."
    ),
    "bio_en": (
        "Initial public profile for Dr. Khaled Badran. Credentials, experience, "
        "and professional memberships should be verified before final publication."
    ),
    "is_active": True,
    "display_order": 0,
}

VISIT_TYPE_DATA = [
    ("كشف جديد", "New consultation", 30),
    ("مراجعة", "Follow-up", 15),
    ("استشارة أنف وجيوب", "Nose and sinus consultation", 30),
    ("استشارة أذن وسمع", "Ear and hearing consultation", 30),
    ("استشارة حنجرة وصوت", "Throat and voice consultation", 30),
    ("دوخة وتوازن", "Dizziness and balance", 30),
    ("أنف وأذن وحنجرة أطفال", "Pediatric ENT", 30),
    ("إجراء عيادي", "Clinic procedure", 30),
    ("أخرى", "Other", 30),
]


class Command(BaseCommand):
    help = "Seed safe public clinic, doctor, and visit type content."

    def handle(self, *args, **options):
        clinic, clinic_created = self._upsert_first(
            ClinicProfile,
            {"official_name_en": CLINIC_DATA["official_name_en"]},
            CLINIC_DATA,
        )
        doctor, doctor_created = self._upsert_first(
            Doctor,
            {"full_name_en": DOCTOR_DATA["full_name_en"]},
            DOCTOR_DATA,
        )

        visit_created = 0
        visit_updated = 0
        for index, (name_ar, name_en, duration_minutes) in enumerate(VISIT_TYPE_DATA):
            _, created = self._upsert_first(
                VisitType,
                {"name_en": name_en},
                {
                    "doctor": doctor,
                    "name_ar": name_ar,
                    "name_en": name_en,
                    "duration_minutes": duration_minutes,
                    "price": None,
                    "show_price_to_patient": False,
                    "is_active": True,
                    "instructions_ar": "تحدد التفاصيل بعد التقييم الطبي داخل العيادة.",
                    "instructions_en": "Details are confirmed after in-clinic medical assessment.",
                    "display_order": index,
                },
            )
            if created:
                visit_created += 1
            else:
                visit_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded public content: "
                f"clinic={'created' if clinic_created else 'updated'}, "
                f"doctor={'created' if doctor_created else 'updated'}, "
                f"visit_types_created={visit_created}, "
                f"visit_types_updated={visit_updated}."
            )
        )
        self.stdout.write(
            "No patients, appointments, WhatsApp messages, files, prices, or booking slots were created."
        )

    def _upsert_first(self, model, lookup, defaults):
        obj = model.objects.filter(**lookup).order_by("id").first()
        if obj is None:
            return model.objects.create(**defaults), True

        changed_fields = []
        for field, value in defaults.items():
            if getattr(obj, field) != value:
                setattr(obj, field, value)
                changed_fields.append(field)

        if changed_fields:
            obj.save(update_fields=changed_fields)
        return obj, False
