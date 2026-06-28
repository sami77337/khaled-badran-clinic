from django.http import HttpResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse

from apps.clinic.models import (
    CLINIC_OFFICIAL_NAME_AR,
    CLINIC_OFFICIAL_NAME_EN,
    ClinicProfile,
    Doctor,
    VisitType,
)


SUPPORTED_LANGUAGES = {"ar", "en"}
DEFAULT_LANGUAGE = "ar"

DOCTOR_DEFAULT = {
    "full_name_ar": "خالد حسان بدران",
    "full_name_en": "Khaled Hassan Badran",
    "display_name_ar": "د. خالد حسان بدران",
    "display_name_en": "Dr. Khaled Hassan Badran",
    "specialty_ar": "استشاري الأنف والأذن والحنجرة",
    "specialty_en": "ENT consultant",
    "bio_ar": (
        "صفحة تعريفية أولية للدكتور خالد بدران ضمن موقع العيادة. "
        "يجب تدقيق تفاصيل المؤهلات والخبرة قبل النشر النهائي."
    ),
    "bio_en": (
        "Initial public profile for Dr. Khaled Badran. Credentials and "
        "experience details should be verified before final publication."
    ),
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
            "subtitle": "تجربة عيادية دافئة ومنظمة للدكتور خالد حسان بدران، مع تجهيز الموقع للانتقال لاحقاً إلى الحجز الإلكتروني.",
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
        "contact": {
            "title": "التواصل",
            "description": "معلومات التواصل والموقع وساعات العمل لعيادة الدكتور خالد بدران.",
            "headline": "تواصل مع العيادة",
            "subtitle": "بيانات التواصل الحالية placeholders آمنة لحين اعتماد الأرقام والعنوان النهائي.",
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
    },
    "en": {
        "home": {
            "title": "Home",
            "description": "Public website for Dr. Khaled Badran Clinic, ENT consultant care.",
            "hero_label": "ENT Clinic",
            "headline": "Warm, focused ENT care in a calm clinic setting",
            "subtitle": "A polished public foundation for Dr. Khaled Hassan Badran Clinic, prepared for a later online booking workflow.",
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
        "contact": {
            "title": "Contact",
            "description": "Contact, location, and clinic hours for Dr. Khaled Badran Clinic.",
            "headline": "Contact the Clinic",
            "subtitle": "Current contact details are safe placeholders until final approval.",
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
    },
}

LABELS = {
    "ar": {
        "book": "طلب حجز مبدئي",
        "book_note": "يتم تأكيد الموعد بعد اختيار الوقت وإرسال بيانات التواصل في خطوة التأكيد.",
        "whatsapp": "واتساب العيادة",
        "whatsapp_note": "زر واتساب placeholder ولا يرسل رسائل حالياً.",
        "contact": "معلومات التواصل",
        "services": "الخدمات",
        "doctor": "الدكتور",
        "home": "الرئيسية",
        "privacy": "الخصوصية",
        "terms": "الشروط",
        "medical_disclaimer": "إخلاء طبي",
        "whatsapp_policy": "سياسة واتساب",
        "not_emergency": "الموقع وواتساب غير مخصصين للطوارئ. في الحالات الطارئة اتصل بخدمات الطوارئ المحلية فوراً.",
        "verify_profile": "تحتاج تفاصيل المؤهلات والعضويات والخبرة إلى تدقيق نهائي قبل النشر العام.",
    },
    "en": {
        "book": "Request booking",
        "book_note": "Your appointment is confirmed after choosing a time and submitting the confirmation step.",
        "whatsapp": "Clinic WhatsApp",
        "whatsapp_note": "WhatsApp is a placeholder button and does not send messages yet.",
        "contact": "Contact Details",
        "services": "Services",
        "doctor": "Doctor",
        "home": "Home",
        "privacy": "Privacy",
        "terms": "Terms",
        "medical_disclaimer": "Medical Disclaimer",
        "whatsapp_policy": "WhatsApp Policy",
        "not_emergency": "This website and WhatsApp are not for emergencies. For urgent symptoms, contact local emergency services immediately.",
        "verify_profile": "Credentials, memberships, and experience details should be verified before final public publication.",
    },
}

ROUTE_NAMES = {
    "home": {"ar": "home", "en": "home_en"},
    "doctor": {"ar": "doctor", "en": "doctor_en"},
    "services": {"ar": "services", "en": "services_en"},
    "contact": {"ar": "contact", "en": "contact_en"},
    "privacy": {"ar": "privacy", "en": "privacy_en"},
    "terms": {"ar": "terms", "en": "terms_en"},
    "medical_disclaimer": {"ar": "medical_disclaimer", "en": "medical_disclaimer_en"},
    "whatsapp_policy": {"ar": "whatsapp_policy", "en": "whatsapp_policy_en"},
    "booking": {"ar": "book", "en": "book_en"},
}


def health_check(request):
    return HttpResponse(
        "Dr. Khaled Badran Clinic foundation is running.",
        content_type="text/plain; charset=utf-8",
    )


def _normalize_language(language):
    return language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def _route_url(page_key, language):
    return reverse(ROUTE_NAMES[page_key][_normalize_language(language)])


def _active_clinic():
    return ClinicProfile.objects.filter(is_active=True).order_by("id").first()


def _active_doctor():
    return Doctor.objects.filter(is_active=True).order_by("display_order", "id").first()


def _clinic_context():
    clinic = _active_clinic()
    return {
        "object": clinic,
        "name_ar": clinic.official_name_ar if clinic else CLINIC_OFFICIAL_NAME_AR,
        "name_en": clinic.official_name_en if clinic else CLINIC_OFFICIAL_NAME_EN,
        "phone_raw": clinic.phone_raw if clinic and clinic.phone_raw else "+962 7X XXX XXXX",
        "address_ar": clinic.address_ar if clinic and clinic.address_ar else "العنوان سيضاف بعد اعتماده",
        "address_en": clinic.address_en if clinic and clinic.address_en else "Address placeholder pending approval",
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
            ("contact", LABELS[language]["contact"], _route_url("contact", language)),
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
        "og_image_url": request.build_absolute_uri(static("img/placeholders/clinic-placeholder.svg")),
        "booking_placeholder_url": _route_url("booking", language),
        "booking_url": _route_url("booking", language),
        "whatsapp_placeholder_url": _route_url("contact", language) + "#whatsapp-placeholder",
        "contact_url": _route_url("contact", language),
        "services_url": _route_url("services", language),
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
