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
            "items": ["التقييم السريري", "التهابات الأذن والأنف والحنجرة", "متابعة الحالات المزمنة"],
        },
        {
            "title": "أنف وأذن وحنجرة للأطفال",
            "items": ["التهابات الأذن المتكررة", "مشاكل اللوز واللحمية", "صعوبات التنفس الأنفي"],
        },
        {
            "title": "الأنف والجيوب الأنفية",
            "items": ["انسداد الأنف", "التهاب الجيوب", "الحساسية الأنفية"],
        },
        {
            "title": "الأذن والسمع والتوازن",
            "items": ["ألم الأذن", "ضعف السمع", "الدوخة ومشاكل التوازن"],
        },
        {
            "title": "الحنجرة والصوت",
            "items": ["بحة الصوت", "آلام الحلق", "مشاكل البلع الأولية"],
        },
        {
            "title": "إجراءات عيادية",
            "items": ["إجراءات بسيطة داخل العيادة", "تفاصيل الإجراءات تحدد بعد التقييم الطبي"],
        },
    ],
    "en": [
        {
            "title": "Adult ENT",
            "items": ["Clinical assessment", "Ear, nose, and throat infections", "Ongoing ENT follow-up"],
        },
        {
            "title": "Pediatric ENT",
            "items": ["Recurrent ear infections", "Tonsil and adenoid concerns", "Nasal breathing concerns"],
        },
        {
            "title": "Nose and Sinus",
            "items": ["Nasal obstruction", "Sinus concerns", "Allergic rhinitis"],
        },
        {
            "title": "Ear, Hearing, and Balance",
            "items": ["Ear pain", "Hearing concerns", "Dizziness and balance symptoms"],
        },
        {
            "title": "Throat and Voice",
            "items": ["Hoarseness", "Sore throat", "Initial swallowing concerns"],
        },
        {
            "title": "Clinic Procedures",
            "items": ["Simple in-clinic procedures", "Procedure details are confirmed after medical assessment"],
        },
    ],
}

PAGE_COPY = {
    "ar": {
        "home": {
            "title": "الرئيسية",
            "description": "موقع عيادة الدكتور خالد بدران، استشاري الأنف والأذن والحنجرة.",
            "hero_label": "عيادة أنف وأذن وحنجرة",
            "headline": "رعاية أنف وأذن وحنجرة بهدوء واهتمام بالتفاصيل",
            "subtitle": "رعاية متخصصة للكبار والأطفال، مع اهتمام خاص بجراحة الأنف الوظيفية والتجميلية.",
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
            "subtitle": "هذه الصفحة تعرض وسائط تم اعتمادها صراحة للعرض العام مع تأكيد الموافقة، ولا تعرض هوية المرضى أو تفاصيل السجلات الخاصة.",
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
            "subtitle": "Specialized adult and pediatric ENT care, with a particular focus on functional and cosmetic rhinoplasty.",
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
            "subtitle": "This page shows only media explicitly approved for public display with confirmed consent, without patient identity or private record details.",
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
        "whatsapp_note": "رابط واتساب السريع غير مفعّل حتى اعتماد رقم العيادة المخصص له.",
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
        "verify_profile": "تحتاج تفاصيل المؤهلات والعضويات والخبرة إلى تدقيق نهائي قبل النشر العام.",
    },
    "en": {
        "book": "Book an Appointment",
        "book_note": "Your appointment is confirmed after choosing a time and submitting the confirmation step.",
        "whatsapp": "Clinic WhatsApp",
        "whatsapp_note": "The WhatsApp quick link stays inactive until the clinic approves its dedicated number.",
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
        "approved_only": "محتوى معتمد وموافق عليه فقط",
        "approved_only_body": (
            "الوسائط هنا مخصصة للعرض العام بعد موافقة صريحة وتأكيد موافقة. "
            "لا تمثل تشخيصاً أو خطة علاج أو ضمان نتيجة، ولا تغني عن التقييم الطبي."
        ),
        "empty_title": "لا توجد وسائط عامة معتمدة حالياً",
        "empty_body": "ستظهر هنا فقط الوسائط التي تحمل موافقة عامة مؤكدة وتبقى نشطة.",
        "view_media": "عرض الوسيط",
        "view_all": "عرض الحالات",
        "image": "صورة",
        "short_video": "فيديو قصير",
        "untitled": "وسيط معتمد",
        "safety_note": (
            "لا تعرض هذه الصفحة أسماء المرضى أو أرقام الهواتف أو تواريخ الميلاد أو الملاحظات الطبية الخاصة. "
            "وسائط بوابة المريض لا تصبح عامة تلقائياً."
        ),
    },
    "en": {
        "approved_only": "Approved and consented content only",
        "approved_only_body": (
            "Media here is public showcase content only after explicit approval and confirmed consent. "
            "It is not a diagnosis, treatment plan, outcome guarantee, or substitute for medical assessment."
        ),
        "empty_title": "No approved public showcase media yet",
        "empty_body": "Only active media with explicit public-case approval and confirmed consent will appear here.",
        "view_media": "View media",
        "view_all": "View cases",
        "image": "Image",
        "short_video": "Short video",
        "untitled": "Approved media",
        "safety_note": (
            "This page does not show patient names, phone numbers, dates of birth, or private clinical notes. "
            "Patient-visible portal media is not automatically public."
        ),
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


def _public_phone(value):
    normalized = (value or "").strip()
    if _is_placeholder_value(normalized) or "x" in normalized.casefold():
        return ""
    digits = "".join(character for character in normalized if character.isdigit())
    return normalized if len(digits) >= 7 else ""


def _clinic_context():
    clinic = _active_clinic()
    address_ar = clinic.address_ar if clinic and not _is_placeholder_value(clinic.address_ar) else ""
    address_en = clinic.address_en if clinic and not _is_placeholder_value(clinic.address_en) else ""
    return {
        "object": clinic,
        "name_ar": clinic.official_name_ar if clinic else CLINIC_OFFICIAL_NAME_AR,
        "name_en": clinic.official_name_en if clinic else CLINIC_OFFICIAL_NAME_EN,
        "phone_raw": _public_phone(clinic.phone_raw if clinic else ""),
        "address_ar": address_ar or APPROVED_CLINIC_LOCATION["address_ar"],
        "address_en": address_en or APPROVED_CLINIC_LOCATION["address_en"],
        "coordinates": APPROVED_CLINIC_LOCATION["coordinates"],
        "map_url": APPROVED_CLINIC_LOCATION["map_url"],
        "map_embed_url": APPROVED_CLINIC_LOCATION["map_embed_url"],
    }


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
    }


def _visit_types(language):
    language = _normalize_language(language)
    rows = []
    for visit_type in VisitType.objects.filter(is_active=True).order_by("display_order", "name_en"):
        rows.append(
            {
                "name": visit_type.name_ar if language == "ar" else visit_type.name_en,
                "name_ar": visit_type.name_ar,
                "name_en": visit_type.name_en,
                "duration_minutes": visit_type.duration_minutes,
                "instructions": visit_type.instructions_ar if language == "ar" else visit_type.instructions_en,
                "price": visit_type.patient_visible_price,
            }
        )
    if rows:
        return rows

    return [
        {
            "name": item[0] if language == "ar" else item[1],
            "name_ar": item[0],
            "name_en": item[1],
            "duration_minutes": item[2],
            "instructions": "",
            "price": None,
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


def _base_context(request, page_key, language):
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
            ("patient_portal", LABELS[language]["patient_portal"], _route_url("patient_portal", language)),
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
        "whatsapp_placeholder_url": _route_url("contact", language) + "#whatsapp-placeholder",
        "whatsapp_is_configured": False,
        "whatsapp_url": "",
        "contact_url": _route_url("contact", language),
        "services_url": _route_url("services", language),
        "cases_url": _route_url("cases", language),
        "doctor_url": _route_url("doctor", language),
        "home_url": _route_url("home", language),
    }


def _render_public(request, template_name, page_key, language=DEFAULT_LANGUAGE, extra_context=None):
    context = _base_context(request, page_key, language)
    if extra_context:
        context.update(extra_context)
    return render(request, template_name, context)


def home(request, language=DEFAULT_LANGUAGE):
    language = _normalize_language(language)
    services = _visit_types(language)
    return _render_public(
        request,
        "core/home.html",
        "home",
        language,
        {
            "service_highlights": services[:4],
            "service_groups": SERVICE_GROUPS[language][:3],
            "public_case_teasers": _public_case_media_items(language, limit=3),
            "case_labels": PUBLIC_CASE_LABELS[language],
        },
    )


def doctor_profile(request, language=DEFAULT_LANGUAGE):
    language = _normalize_language(language)
    return _render_public(
        request,
        "core/doctor.html",
        "doctor",
        language,
        {
            "areas_of_care": SERVICE_GROUPS[language],
        },
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
    return _render_public(request, "core/contact.html", "contact", language)


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
    context = _base_context(request, "home", language)
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
