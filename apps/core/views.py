from pathlib import PurePosixPath

from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.clinic.models import (
    CLINIC_OFFICIAL_NAME_AR,
    CLINIC_OFFICIAL_NAME_EN,
    ClinicProfile,
    Doctor,
    VisitType,
)
from apps.records.models import RecordMedia


SUPPORTED_LANGUAGES = {"ar", "en"}
DEFAULT_LANGUAGE = "ar"

DOCTOR_DEFAULT = {
    "full_name_ar": "خالد حسان بدران",
    "full_name_en": "Khaled Hassan Badran",
    "display_name_ar": "د. خالد حسان بدران",
    "display_name_en": "Dr. Khaled Hassan Badran",
    "specialty_ar": "استشاري الأنف والأذن والحنجرة",
    "specialty_en": "Consultant Ear, Nose and Throat Surgeon",
    "credential_label_ar": "البورد الأوروبي والبورد الأردني للأنف والأذن والحنجرة",
    "credential_label_en": "European ENT Board · Jordanian ENT Board",
    "public_focus_ar": "الأنف والأذن والحنجرة وجراحة الأنف الوظيفية والتجميلية",
    "public_focus_en": "ENT & Functional and Cosmetic Rhinoplasty",
    "hero_summary_ar": "رعاية متخصصة للكبار والأطفال، مع اهتمام خاص بجراحة الأنف الوظيفية والتجميلية.",
    "hero_summary_en": "Specialized adult and pediatric ENT care, with a particular focus on functional and cosmetic rhinoplasty.",
    "footer_summary_ar": "استشاري الأنف والأذن والحنجرة · جراحة الأنف الوظيفية والتجميلية",
    "footer_summary_en": "Consultant Ear, Nose and Throat Surgeon · Functional and Cosmetic Rhinoplasty",
    "bio_ar": (
        "استشاري في أمراض وجراحة الأنف والأذن والحنجرة للكبار والأطفال، "
        "حاصل على البورد الأوروبي والبورد الأردني، مع خبرة مهنية في مستشفيات "
        "المملكة المتحدة واهتمام خاص بجراحة الأنف الوظيفية والتجميلية."
    ),
    "bio_en": (
        "Consultant in adult and pediatric ear, nose and throat medicine and "
        "surgery, certified by the European and Jordanian Boards, with "
        "professional experience in UK hospitals and a special focus on "
        "functional and cosmetic rhinoplasty."
    ),
}

APPROVED_CLINIC_PHONE = {
    "display": "+962 7 8976 6332",
    "e164": "+962789766332",
    "whatsapp_url": "https://wa.me/962789766332",
}

APPROVED_CLINIC_LOCATION = {
    "address_ar": (
        "عمّان – الشميساني\n"
        "شارع رفيق العظم 13\n"
        "مجمع الفيحاء الطبي – الطابق الأول\n"
        "مقابل مستشفى الشميساني وحديقة الطيور"
    ),
    "address_en": (
        "Al Shmeisani, Amman\n"
        "Rafiq Al Athem St. 13\n"
        "Al Fayhaa Medical Complex – First Floor\n"
        "Opposite Shmeisani Hospital and Bird Garden"
    ),
    "coordinates": "31.970276,35.8934391",
    "map_url": "https://www.google.com/maps/search/?api=1&query=31.970276%2C35.8934391",
    "map_embed_url": "https://www.google.com/maps?q=31.970276,35.8934391&z=16&output=embed",
}

APPROVED_PUBLIC_CLINIC_GALLERY = (
    {
        "asset_path": "img/clinic/clinic-interior-1.png",
        "alt_ar": "منطقة الاستقبال داخل عيادة الدكتور خالد بدران",
        "alt_en": "Reception area inside Dr. Khaled Badran Clinic",
    },
    {
        "asset_path": "img/clinic/clinic-interior-2.png",
        "alt_ar": "غرفة الفحص وتجهيزاتها داخل العيادة",
        "alt_en": "Examination room and equipment inside the clinic",
    },
    {
        "asset_path": "img/clinic/clinic-interior-3.png",
        "alt_ar": "مساحة الاستشارة داخل عيادة الدكتور خالد بدران",
        "alt_en": "Consultation space inside Dr. Khaled Badran Clinic",
    },
    {
        "asset_path": "img/clinic/clinic-interior-4.webp",
        "alt_ar": "إطلالة واسعة على منطقة الاستقبال والعيادة",
        "alt_en": "Wide view of the clinic reception and interior",
    },
    {
        "asset_path": "img/clinic/clinic-interior-5.webp",
        "alt_ar": "منطقة الانتظار داخل عيادة الدكتور خالد بدران",
        "alt_en": "Waiting area inside Dr. Khaled Badran Clinic",
    },
)

FALLBACK_VISIT_TYPES = [
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

SERVICE_GROUPS = {
    "ar": [
        {
            "title": "أنف وأذن وحنجرة للبالغين",
            "bullet_items": ["التقييم السريري", "التهابات الأذن والأنف والحنجرة", "متابعة الحالات المزمنة"],
        },
        {
            "title": "أنف وأذن وحنجرة للأطفال",
            "bullet_items": ["التهابات الأذن المتكررة", "مشاكل اللوز واللحمية", "صعوبات التنفس الأنفي"],
        },
        {
            "title": "الأنف والجيوب الأنفية",
            "bullet_items": ["انسداد الأنف", "التهاب الجيوب", "الحساسية الأنفية"],
        },
        {
            "title": "الأذن والسمع والتوازن",
            "bullet_items": ["ألم الأذن", "ضعف السمع", "الدوخة ومشاكل التوازن"],
        },
        {
            "title": "الحنجرة والصوت",
            "bullet_items": ["بحة الصوت", "آلام الحلق", "مشاكل البلع الأولية"],
        },
        {
            "title": "إجراءات عيادية",
            "bullet_items": ["إجراءات بسيطة داخل العيادة", "تفاصيل الإجراءات تحدد بعد التقييم الطبي"],
        },
    ],
    "en": [
        {
            "title": "Adult ENT",
            "bullet_items": ["Clinical assessment", "Ear, nose, and throat infections", "Ongoing ENT follow-up"],
        },
        {
            "title": "Pediatric ENT",
            "bullet_items": ["Recurrent ear infections", "Tonsil and adenoid concerns", "Nasal breathing concerns"],
        },
        {
            "title": "Nose and Sinus",
            "bullet_items": ["Nasal obstruction", "Sinus concerns", "Allergic rhinitis"],
        },
        {
            "title": "Ear, Hearing, and Balance",
            "bullet_items": ["Ear pain", "Hearing concerns", "Dizziness and balance symptoms"],
        },
        {
            "title": "Throat and Voice",
            "bullet_items": ["Hoarseness", "Sore throat", "Initial swallowing concerns"],
        },
        {
            "title": "Clinic Procedures",
            "bullet_items": ["Simple in-clinic procedures", "Procedure details are confirmed after medical assessment"],
        },
    ],
}

DOCTOR_PUBLIC_PROFILE = {
    "ar": {
        "experience": [
            "الدكتور خالد يعمل حالياً في عيادته الخاصة في عمّان.",
            "زمالة/تدريب في الأنف والأذن والحنجرة في مستشفى مونكلاندز، المملكة المتحدة.",
            "عمل لمدة أربعة أعوام كمستشار في اختصاص الأنف والأذن والحنجرة في مستشفى الوادي الرابع الملكي",
            "عمل كطبيب اختصاصي مسجل في عدد كبير من المستشفيات البريطانية.",
        ],
        "education": [
            "بكالوريوس الطب والجراحة — الجامعة الأردنية، الأردن",
            "ماجستير في العلوم الصحية — جامعة لانكشاير المركزية، المملكة المتحدة",
            "زمالة — أنف وأذن وحنجرة — مستشفى مونكلاندز، المملكة المتحدة",
            "تخصص — أنف وأذن وحنجرة — مستشفى الجامعة الأردنية، الأردن",
            "الاختصاص العالي — الجامعة الأردنية",
        ],
        "boards": [
            "شهادة البورد الأوروبي — أنف وأذن وحنجرة (EBC)",
            "شهادة البورد الأردني — أنف وأذن وحنجرة (JBC)",
        ],
        "memberships": [
            {"label": "الكلية الملكية للجراحين - أيرلندا", "acronym": "FRCSI"},
            {"label": "المجلس الطبي العام البريطاني", "acronym": "GMC"},
            {
                "label": "الأكاديمية الأمريكية لجراحة الأنف والأذن والحنجرة والرأس والرقبة",
                "acronym": "BAO-HNS",
            },
            {"label": "اتحاد الدفاع الطبي", "acronym": "MDU"},
            {"label": "عضو الكلية الملكية للجراحين - أيرلندا", "acronym": "MRCSI"},
        ],
        "specialties": [
            "أنف وأذن وحنجرة",
            "أنف وأذن وحنجرة كبار",
            "أنف وأذن وحنجرة أطفال",
            "جراحة أنف وأذن وحنجرة كبار",
            "جراحة أنف وأذن وحنجرة أطفال",
            "جراحة تجميل الأنف",
        ],
        "awards": [
            "جائزة مركز الحسين للسرطان — 2015",
            "جائزة المرشح الرئاسي — 2011",
        ],
        "languages": ["العربية", "الإنجليزية"],
    },
    "en": {
        "experience": [
            "Dr. Khaled currently works in his private clinic in Amman.",
            "ENT fellowship/training at Monklands Hospital, United Kingdom.",
            "Four years of ENT consultant experience in a UK hospital.",
            "Specialist registrar experience across multiple UK hospitals.",
        ],
        "education": [
            "Bachelor of Medicine and Surgery — University of Jordan, Jordan",
            "Master’s in Health Sciences — University of Central Lancashire, United Kingdom",
            "ENT Fellowship — Monklands Hospital, United Kingdom",
            "ENT Specialization — University of Jordan Hospital, Jordan",
            "Higher Specialization — University of Jordan",
        ],
        "boards": [
            "European Board Certificate — ENT (EBC)",
            "Jordanian Board Certificate — ENT (JBC)",
        ],
        "memberships": [
            {"label": "", "acronym": "FRCSI"},
            {"label": "", "acronym": "GMC"},
            {"label": "", "acronym": "BAO-HNS"},
            {"label": "", "acronym": "MDU"},
            {"label": "", "acronym": "MRCSI"},
        ],
        "specialties": [
            "Ear, Nose and Throat",
            "Adult ENT",
            "Pediatric ENT",
            "Adult ENT Surgery",
            "Pediatric ENT Surgery",
            "Rhinoplasty",
        ],
        "awards": [
            "King Hussein Cancer Center Award — 2015",
            "Presidential Candidate Award — 2011",
        ],
        "languages": ["Arabic", "English"],
    },
}

DOCTOR_CONDITIONS = {
    "ar": [
        "التهاب الجيوب الأنفية المزمن",
        "الرشح",
        "طنين الأذن",
        "ألم الأذن",
        "الحالات الطارئة لأمراض الأنف والأذن والحنجرة",
        "الشخير",
        "التهاب الأذن",
        "التهاب الحلق المزمن",
        "التهاب الحنجرة",
        "التهاب اللوزتين عند الكبار",
        "لحمية الأنف (سليلة أنفية)",
    ],
    "en": [
        "Chronic sinusitis",
        "Common cold",
        "Tinnitus",
        "Ear pain",
        "ENT emergencies",
        "Snoring",
        "Ear infection",
        "Chronic sore throat",
        "Laryngitis",
        "Adult tonsillitis",
        "Nasal polyps (nasal polyp)",
    ],
}

PAGE_COPY = {
    "ar": {
        "home": {
            "title": "الرئيسية",
            "description": "موقع عيادة الدكتور خالد بدران، استشاري الأنف والأذن والحنجرة.",
            "hero_label": "عيادة أنف وأذن وحنجرة",
            "headline": "رعاية أنف وأذن وحنجرة بهدوء واهتمام بالتفاصيل",
        },
        "doctor": {
            "title": "الدكتور",
            "description": "نبذة تعريفية عن د. خالد حسان بدران، استشاري الأنف والأذن والحنجرة.",
            "headline": "د. خالد حسان بدران",
            "subtitle": "استشاري الأنف والأذن والحنجرة",
        },
        "services": {
            "title": "الخدمات",
            "description": "خدمات الأنف والأذن والحنجرة المتاحة في عيادة الدكتور خالد بدران.",
            "headline": "خدمات العيادة",
            "subtitle": "تصنيف واضح لخدمات الأنف والأذن والحنجرة للبالغين والأطفال.",
        },
        "cases": {
            "title": "الحالات والإنجازات",
            "description": "وسائط عرض عامة معتمدة وموافق عليها فقط من عيادة الدكتور خالد بدران.",
            "headline": "حالات وإنجازات معتمدة للعرض",
            "subtitle": "تُعرض هنا فقط الحالات المصرّح بنشرها بموافقة صريحة.",
        },
        "contact": {
            "title": "التواصل والموقع",
            "description": "معلومات التواصل والموقع المعتمد لعيادة الدكتور خالد بدران.",
            "headline": "موقع العيادة",
            "subtitle": "عيادة الدكتور خالد بدران في الشميساني، داخل مجمع الفيحاء الطبي، مقابل مستشفى الشميساني وحديقة الطيور.",
        },
        "privacy": {
            "title": "سياسة الخصوصية",
            "description": "مسودة تشغيلية أولية لسياسة الخصوصية في عيادة الدكتور خالد بدران.",
            "headline": "سياسة الخصوصية",
            "subtitle": "مسودة أولية تحتاج مراجعة قانونية قبل الإنتاج.",
        },
        "terms": {
            "title": "شروط الاستخدام",
            "description": "مسودة تشغيلية أولية لشروط استخدام موقع عيادة الدكتور خالد بدران.",
            "headline": "شروط الاستخدام",
            "subtitle": "مسودة أولية لا تغني عن المراجعة القانونية.",
        },
        "medical_disclaimer": {
            "title": "إخلاء مسؤولية طبي",
            "description": "تنبيه طبي حول حدود استخدام موقع عيادة الدكتور خالد بدران.",
            "headline": "إخلاء مسؤولية طبي",
            "subtitle": "الموقع للتعريف والتواصل، وليس للتشخيص أو الطوارئ.",
        },
        "whatsapp_policy": {
            "title": "سياسة استخدام واتساب",
            "description": "مسودة سياسة استخدام واتساب للتواصل مع عيادة الدكتور خالد بدران.",
            "headline": "سياسة استخدام واتساب",
            "subtitle": "واتساب قناة تواصل إدارية ومبدئية، وليس قناة طوارئ أو تشخيص.",
        },
        "booking": {
            "title": "حجز موعد",
            "description": "حجز موعد مؤكد في عيادة الدكتور خالد بدران.",
            "headline": "حجز موعد",
            "subtitle": "اختر نوع الزيارة والوقت المتاح، ثم أكد بيانات التواصل.",
        },
        "patient_portal": {
            "title": "بوابة المريض",
            "description": "بوابة اختيارية لعرض المواعيد المرتبطة فقط في عيادة الدكتور خالد بدران.",
            "headline": "بوابة المريض",
            "subtitle": "حساب اختياري لربط المواعيد باستخدام رمز التأكيد ورقم الهاتف.",
        },
    },
    "en": {
        "home": {
            "title": "Home",
            "description": "Public website for Dr. Khaled Badran Clinic, ENT consultant care.",
            "hero_label": "ENT Clinic",
            "headline": "Warm, focused ENT care in a calm clinic setting",
        },
        "doctor": {
            "title": "Doctor",
            "description": "Profile page for Dr. Khaled Hassan Badran, ENT consultant.",
            "headline": "Dr. Khaled Hassan Badran",
            "subtitle": "ENT consultant",
        },
        "services": {
            "title": "Services",
            "description": "ENT service categories available at Dr. Khaled Badran Clinic.",
            "headline": "Clinic Services",
            "subtitle": "Clear ENT service groups for adults and children.",
        },
        "cases": {
            "title": "Cases and Achievements",
            "description": "Approved and consented public showcase media for Dr. Khaled Badran Clinic.",
            "headline": "Approved Cases and Achievements",
            "subtitle": "Only cases explicitly approved for public display are shown.",
        },
        "contact": {
            "title": "Contact & Location",
            "description": "Contact details and the approved location for Dr. Khaled Badran Clinic.",
            "headline": "Clinic Location",
            "subtitle": "Dr. Khaled Badran Clinic is in Al Shmeisani, inside Al Fayhaa Medical Complex, opposite Shmeisani Hospital and Bird Garden.",
        },
        "privacy": {
            "title": "Privacy Policy",
            "description": "Initial operational draft privacy policy for Dr. Khaled Badran Clinic.",
            "headline": "Privacy Policy",
            "subtitle": "Initial draft for legal review before production.",
        },
        "terms": {
            "title": "Terms of Use",
            "description": "Initial operational draft terms of use for Dr. Khaled Badran Clinic.",
            "headline": "Terms of Use",
            "subtitle": "Initial draft, not a substitute for legal review.",
        },
        "medical_disclaimer": {
            "title": "Medical Disclaimer",
            "description": "Medical disclaimer for the public website of Dr. Khaled Badran Clinic.",
            "headline": "Medical Disclaimer",
            "subtitle": "The website supports information and contact only, not diagnosis or emergencies.",
        },
        "whatsapp_policy": {
            "title": "WhatsApp Use Policy",
            "description": "Initial WhatsApp communication policy for Dr. Khaled Badran Clinic.",
            "headline": "WhatsApp Use Policy",
            "subtitle": "WhatsApp is for administrative and initial communication, not emergencies or diagnosis.",
        },
        "booking": {
            "title": "Book an Appointment",
            "description": "Book a confirmed appointment at Dr. Khaled Badran Clinic.",
            "headline": "Book an Appointment",
            "subtitle": "Choose a visit type and available time, then confirm contact details.",
        },
        "patient_portal": {
            "title": "Patient Portal",
            "description": "Optional patient portal for linked appointments only at Dr. Khaled Badran Clinic.",
            "headline": "Patient Portal",
            "subtitle": "Optional account access for appointments linked by confirmation token and phone number.",
        },
    },
}

LABELS = {
    "ar": {
        "book": "احجز موعداً",
        "book_note": "يتم تأكيد الموعد بعد اختيار الوقت وإرسال بيانات التواصل في خطوة التأكيد.",
        "whatsapp": "واتساب العيادة",
        "whatsapp_note": "تواصل مع العيادة مباشرة عبر واتساب.",
        "contact": "التواصل والموقع",
        "services": "الخدمات",
        "cases": "الحالات",
        "doctor": "الدكتور",
        "home": "الرئيسية",
        "privacy": "الخصوصية",
        "terms": "الشروط",
        "medical_disclaimer": "إخلاء طبي",
        "whatsapp_policy": "سياسة واتساب",
        "patient_portal": "بوابة المريض",
        "not_emergency": "الموقع وواتساب غير مخصصين للطوارئ. في الحالات الطارئة اتصل بخدمات الطوارئ المحلية فوراً.",
        "public_emergency": "الموقع وواتساب ليسا للطوارئ.",
        "verify_profile": "تحتاج تفاصيل المؤهلات والعضويات والخبرة إلى تدقيق نهائي قبل النشر العام.",
    },
    "en": {
        "book": "Book an Appointment",
        "book_note": "Your appointment is confirmed after choosing a time and submitting the confirmation step.",
        "whatsapp": "Clinic WhatsApp",
        "whatsapp_note": "Contact the clinic directly on WhatsApp.",
        "contact": "Contact & Location",
        "services": "Services",
        "cases": "Cases",
        "doctor": "Doctor",
        "home": "Home",
        "privacy": "Privacy",
        "terms": "Terms",
        "medical_disclaimer": "Medical Disclaimer",
        "whatsapp_policy": "WhatsApp Policy",
        "patient_portal": "Patient Portal",
        "not_emergency": "This website and WhatsApp are not for emergencies. For urgent symptoms, contact local emergency services immediately.",
        "public_emergency": "The website and WhatsApp are not for emergencies.",
        "verify_profile": "Credentials, memberships, and experience details should be verified before final public publication.",
    },
}

ROUTE_NAMES = {
    "home": {"ar": "home", "en": "home_en"},
    "doctor": {"ar": "doctor", "en": "doctor_en"},
    "services": {"ar": "services", "en": "services_en"},
    "cases": {"ar": "public_cases", "en": "public_cases_en"},
    "contact": {"ar": "contact", "en": "contact_en"},
    "privacy": {"ar": "privacy", "en": "privacy_en"},
    "terms": {"ar": "terms", "en": "terms_en"},
    "medical_disclaimer": {"ar": "medical_disclaimer", "en": "medical_disclaimer_en"},
    "whatsapp_policy": {"ar": "whatsapp_policy", "en": "whatsapp_policy_en"},
    "booking": {"ar": "book", "en": "book_en"},
    "patient_portal": {"ar": "patient_portal_dashboard", "en": "patient_portal_dashboard_en"},
}

PUBLIC_CASE_LABELS = {
    "ar": {
        "approved_only": "تُعرض هنا فقط الحالات المصرّح بنشرها بموافقة صريحة.",
        "empty_title": "لا توجد حالات منشورة حالياً.",
        "view_media": "عرض الوسيط",
        "view_all": "عرض الحالات",
        "image": "صورة",
        "short_video": "فيديو قصير",
        "untitled": "وسيط معتمد",
    },
    "en": {
        "approved_only": "Only cases explicitly approved for public display are shown.",
        "empty_title": "No public cases are currently published.",
        "view_media": "View media",
        "view_all": "View cases",
        "image": "Image",
        "short_video": "Short video",
        "untitled": "Approved media",
    },
}


@require_GET
@never_cache
def health_check(request):
    return JsonResponse(
        {
            "status": "ok",
            "service": "Dr. Khaled Badran Clinic",
        }
    )


@require_GET
@never_cache
def readiness_check(request):
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def _normalize_language(language):
    return language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def _route_url(page_key, language):
    return reverse(ROUTE_NAMES[page_key][_normalize_language(language)])


def _active_clinic():
    return ClinicProfile.objects.filter(is_active=True).order_by("id").first()


def _active_doctor():
    return Doctor.objects.filter(is_active=True).order_by("display_order", "id").first()


def _is_placeholder_value(value):
    normalized = (value or "").strip().casefold()
    placeholder_markers = ("placeholder", "pending approval", "سيضاف", "لحين اعتماد")
    return not normalized or any(marker in normalized for marker in placeholder_markers)


def _clinic_context():
    clinic = _active_clinic()
    address_ar = clinic.address_ar if clinic and not _is_placeholder_value(clinic.address_ar) else ""
    address_en = clinic.address_en if clinic and not _is_placeholder_value(clinic.address_en) else ""
    return {
        "object": clinic,
        "name_ar": clinic.official_name_ar if clinic else CLINIC_OFFICIAL_NAME_AR,
        "name_en": clinic.official_name_en if clinic else CLINIC_OFFICIAL_NAME_EN,
        "phone_raw": APPROVED_CLINIC_PHONE["display"],
        "phone_display": APPROVED_CLINIC_PHONE["display"],
        "phone_e164": APPROVED_CLINIC_PHONE["e164"],
        "address_ar": address_ar or APPROVED_CLINIC_LOCATION["address_ar"],
        "address_en": address_en or APPROVED_CLINIC_LOCATION["address_en"],
        "coordinates": APPROVED_CLINIC_LOCATION["coordinates"],
        "map_url": APPROVED_CLINIC_LOCATION["map_url"],
        "map_embed_url": APPROVED_CLINIC_LOCATION["map_embed_url"],
        "whatsapp_url": APPROVED_CLINIC_PHONE["whatsapp_url"],
    }


def _clinic_gallery(language):
    language = _normalize_language(language)
    return [
        {
            "asset_path": photo["asset_path"],
            "alt": photo[f"alt_{language}"],
        }
        for photo in APPROVED_PUBLIC_CLINIC_GALLERY
    ]


def _doctor_context():
    doctor = _active_doctor()
    if not doctor:
        return dict(DOCTOR_DEFAULT, object=None)

    return {
        "object": doctor,
        "full_name_ar": doctor.full_name_ar,
        "full_name_en": doctor.full_name_en,
        "display_name_ar": doctor.display_name_ar,
        "display_name_en": doctor.display_name_en,
        "specialty_ar": doctor.specialty_ar or DOCTOR_DEFAULT["specialty_ar"],
        "specialty_en": doctor.specialty_en or DOCTOR_DEFAULT["specialty_en"],
        "bio_ar": doctor.bio_ar or DOCTOR_DEFAULT["bio_ar"],
        "bio_en": doctor.bio_en or DOCTOR_DEFAULT["bio_en"],
        "credential_label_ar": DOCTOR_DEFAULT["credential_label_ar"],
        "credential_label_en": DOCTOR_DEFAULT["credential_label_en"],
        "public_focus_ar": DOCTOR_DEFAULT["public_focus_ar"],
        "public_focus_en": DOCTOR_DEFAULT["public_focus_en"],
        "hero_summary_ar": DOCTOR_DEFAULT["hero_summary_ar"],
        "hero_summary_en": DOCTOR_DEFAULT["hero_summary_en"],
        "footer_summary_ar": DOCTOR_DEFAULT["footer_summary_ar"],
        "footer_summary_en": DOCTOR_DEFAULT["footer_summary_en"],
    }


def _visit_types(language):
    language = _normalize_language(language)
    rows = []
    for visit_type in VisitType.objects.filter(is_active=True).order_by("display_order", "name_en"):
        visible_price = visit_type.patient_visible_price
        rows.append(
            {
                "localized_name": visit_type.name_ar if language == "ar" else visit_type.name_en,
                "duration_minutes": visit_type.duration_minutes,
                "public_instructions": (
                    visit_type.instructions_ar if language == "ar" else visit_type.instructions_en
                ),
                "show_price": visible_price is not None,
                "visible_price": format(visible_price, "f") if visible_price is not None else "",
            }
        )
    if rows:
        return rows

    return [
        {
            "localized_name": item[0] if language == "ar" else item[1],
            "duration_minutes": item[2],
            "public_instructions": "",
            "show_price": False,
            "visible_price": "",
        }
        for item in FALLBACK_VISIT_TYPES
    ]


def _public_case_media_queryset():
    return (
        RecordMedia.objects.filter(
            visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
            consent_confirmed=True,
            is_active=True,
        )
        .exclude(file="")
        .order_by("-uploaded_at", "-public_id")
    )


def _public_case_media_url(media, language):
    route_name = "public_case_media_en" if _normalize_language(language) == "en" else "public_case_media"
    return reverse(route_name, kwargs={"public_id": media.public_id})


def _public_case_media_type_label(media, language):
    labels = PUBLIC_CASE_LABELS[_normalize_language(language)]
    if media.media_type == RecordMedia.MediaType.SHORT_VIDEO:
        return labels["short_video"]
    return labels["image"]


def _public_case_download_filename(media):
    source_name = PurePosixPath(str(media.download_filename or "").replace("\\", "/")).name
    extension = PurePosixPath(source_name).suffix.lower()
    return f"public-case-{media.public_id}{extension}"


def _public_case_media_items(language, limit=None):
    language = _normalize_language(language)
    queryset = _public_case_media_queryset()
    if limit is not None:
        queryset = queryset[:limit]

    return [
        {
            "title": media.title,
            "description": media.description,
            "media_type": media.media_type,
            "media_type_label": _public_case_media_type_label(media, language),
            "uploaded_at": media.uploaded_at,
            "url": _public_case_media_url(media, language),
        }
        for media in queryset
    ]


def _base_context(
    request,
    page_key,
    language,
    *,
    use_public_shell=False,
    show_mobile_booking_cta=False,
):
    language = _normalize_language(language)
    alternate_language = "en" if language == "ar" else "ar"
    page = PAGE_COPY[language][page_key]
    clinic = _clinic_context()
    page_title = f"{page['title']} | {clinic['name_ar'] if language == 'ar' else clinic['name_en']}"
    canonical_path = _route_url(page_key, language)

    return {
        "language": language,
        "is_arabic": language == "ar",
        "direction": "rtl" if language == "ar" else "ltr",
        "page_key": page_key,
        "page": page,
        "use_public_shell": use_public_shell,
        "show_mobile_booking_cta": show_mobile_booking_cta,
        "page_title": page_title,
        "meta_description": page["description"],
        "clinic": clinic,
        "doctor": _doctor_context(),
        "labels": LABELS[language],
        "nav_items": [
            ("home", LABELS[language]["home"], _route_url("home", language)),
            ("doctor", LABELS[language]["doctor"], _route_url("doctor", language)),
            ("services", LABELS[language]["services"], _route_url("services", language)),
            ("cases", LABELS[language]["cases"], _route_url("cases", language)),
            ("contact", LABELS[language]["contact"], _route_url("contact", language)),
            (
                "patient_portal",
                LABELS[language]["patient_portal"],
                reverse("login" if language == "ar" else "login_en"),
            ),
        ],
        "legal_links": [
            (LABELS[language]["privacy"], _route_url("privacy", language)),
            (LABELS[language]["terms"], _route_url("terms", language)),
            (LABELS[language]["medical_disclaimer"], _route_url("medical_disclaimer", language)),
            (LABELS[language]["whatsapp_policy"], _route_url("whatsapp_policy", language)),
        ],
        "language_switch": {
            "label": "English" if language == "ar" else "العربية",
            "url": _route_url(page_key, alternate_language),
        },
        "canonical_url": request.build_absolute_uri(canonical_path),
        "og_image_url": request.build_absolute_uri(static("img/clinic/clinic-interior-1.png")),
        "booking_placeholder_url": _route_url("booking", language),
        "booking_url": _route_url("booking", language),
        "whatsapp_placeholder_url": clinic["whatsapp_url"],
        "whatsapp_is_configured": True,
        "whatsapp_url": clinic["whatsapp_url"],
        "contact_url": _route_url("contact", language),
        "services_url": _route_url("services", language),
        "cases_url": _route_url("cases", language),
        "doctor_url": _route_url("doctor", language),
        "home_url": _route_url("home", language),
    }


def _render_public(
    request,
    template_name,
    page_key,
    language=DEFAULT_LANGUAGE,
    extra_context=None,
    *,
    show_mobile_booking_cta=False,
):
    context = _base_context(
        request,
        page_key,
        language,
        use_public_shell=True,
        show_mobile_booking_cta=show_mobile_booking_cta,
    )
    if extra_context:
        context.update(extra_context)
    return render(request, template_name, context)


def home(request, language=DEFAULT_LANGUAGE):
    language = _normalize_language(language)
    return _render_public(
        request,
        "core/home.html",
        "home",
        language,
        {
            "public_case_teasers": _public_case_media_items(language, limit=3),
            "case_labels": PUBLIC_CASE_LABELS[language],
            "public_reviews": (),
            "review_summary": None,
        },
        show_mobile_booking_cta=True,
    )


def doctor_profile(request, language=DEFAULT_LANGUAGE):
    language = _normalize_language(language)
    return _render_public(
        request,
        "core/doctor.html",
        "doctor",
        language,
        {
            "doctor_profile": {
                **DOCTOR_PUBLIC_PROFILE[language],
                "conditions": DOCTOR_CONDITIONS[language],
            },
        },
        show_mobile_booking_cta=True,
    )


def services(request, language=DEFAULT_LANGUAGE):
    language = _normalize_language(language)
    return _render_public(
        request,
        "core/services.html",
        "services",
        language,
        {
            "service_groups": SERVICE_GROUPS[language],
            "visit_types": _visit_types(language),
        },
        show_mobile_booking_cta=True,
    )


@require_GET
@never_cache
def public_cases(request, language=DEFAULT_LANGUAGE):
    language = _normalize_language(language)
    return _render_public(
        request,
        "core/cases.html",
        "cases",
        language,
        {
            "case_items": _public_case_media_items(language),
            "case_labels": PUBLIC_CASE_LABELS[language],
        },
        show_mobile_booking_cta=True,
    )


@require_GET
@never_cache
def public_case_media(request, public_id, language=DEFAULT_LANGUAGE):
    try:
        media = _public_case_media_queryset().get(public_id=public_id)
    except RecordMedia.DoesNotExist as exc:
        raise Http404("Media unavailable.") from exc

    if not media.file:
        raise Http404("Media unavailable.")

    try:
        if not media.file.storage.exists(media.file.name):
            raise Http404("Media unavailable.")
        response = FileResponse(
            media.file.open("rb"),
            as_attachment=False,
            filename=_public_case_download_filename(media),
            content_type=media.content_type or "application/octet-stream",
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise Http404("Media unavailable.") from exc

    response["X-Content-Type-Options"] = "nosniff"
    return response


def contact(request, language=DEFAULT_LANGUAGE):
    language = _normalize_language(language)
    return _render_public(
        request,
        "core/contact.html",
        "contact",
        language,
        {"clinic_gallery": _clinic_gallery(language)},
        show_mobile_booking_cta=True,
    )


def privacy(request, language=DEFAULT_LANGUAGE):
    return _render_public(request, "legal/privacy.html", "privacy", language)


def terms(request, language=DEFAULT_LANGUAGE):
    return _render_public(request, "legal/terms.html", "terms", language)


def medical_disclaimer(request, language=DEFAULT_LANGUAGE):
    return _render_public(
        request,
        "legal/medical_disclaimer.html",
        "medical_disclaimer",
        language,
    )


def whatsapp_policy(request, language=DEFAULT_LANGUAGE):
    return _render_public(
        request,
        "legal/whatsapp_policy.html",
        "whatsapp_policy",
        language,
    )


def public_404(request, exception=None):
    language = "en" if request.path.startswith("/en/") else DEFAULT_LANGUAGE
    context = _base_context(request, "home", language, use_public_shell=True)
    context.update(
        {
            "page_key": "not_found",
            "page_title": (
                f"Page Not Found | {context['clinic']['name_en']}"
                if language == "en"
                else f"الصفحة غير موجودة | {context['clinic']['name_ar']}"
            ),
            "meta_description": (
                "The requested clinic page could not be found."
                if language == "en"
                else "تعذر العثور على صفحة العيادة المطلوبة."
            ),
            "canonical_url": request.build_absolute_uri(request.path),
        }
    )
    return render(request, "404.html", context, status=404)


def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse("sitemap_xml"))
    content = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            f"Sitemap: {sitemap_url}",
            "",
        ]
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


def sitemap_xml(request):
    urls = []
    for page_routes in ROUTE_NAMES.values():
        for language in ("ar", "en"):
            urls.append(request.build_absolute_uri(reverse(page_routes[language])))

    xml_urls = "\n".join(
        f"  <url><loc>{url}</loc><changefreq>weekly</changefreq><priority>0.7</priority></url>"
        for url in urls
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{xml_urls}\n"
        "</urlset>\n"
    )
    return HttpResponse(content, content_type="application/xml; charset=utf-8")
