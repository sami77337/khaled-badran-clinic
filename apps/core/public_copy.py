"""Explicit editable-copy allowlist. Legal, consent, auth and system copy are excluded."""

PAGE_LABELS = {
    "home": ("الرئيسية", "Home"),
    "doctor": ("الطبيب", "Doctor"),
    "services": ("الخدمات", "Services"),
    "contact": ("التواصل", "Contact"),
}

STATIC_COPY = {
    "home.explore_services": ("استكشف الخدمات", "Explore Services"),
    "home.meet_doctor": ("التعرّف على الدكتور", "Meet the Doctor"),
    "home.reviews_label": ("آراء معتمدة", "Approved Feedback"),
    "home.reviews_title": ("آراء المرضى", "Patient Reviews"),
    "home.reviews_link": ("عرض المزيد", "View all reviews"),
    "home.reviews_empty": (
        "ستظهر تقييمات المرضى المعتمدة هنا.",
        "Approved patient reviews will appear here.",
    ),
    "home.contact_title": ("نحن هنا لمساعدتك", "We’re here to help"),
    "home.location_label": ("موقع العيادة", "Clinic Location"),
    "home.phone_label": ("الهاتف", "Phone"),
    "home.directions": ("الحصول على الاتجاهات", "Get Directions"),
    "home.map_link": ("فتح الموقع على Google Maps", "Open in Google Maps"),
    "home.faq_label": ("معلومات مهمة", "Useful Information"),
    "home.faq_title": ("أسئلة شائعة", "Frequently Asked Questions"),
    "home.faq_intro": (
        "إجابات مختصرة حول الحجز ونطاق الموقع.",
        "Short answers about booking and the website scope.",
    ),
    "home.faq_adults_question": (
        "هل يعالج الدكتور الكبار والأطفال؟",
        "Does the doctor see adults and children?",
    ),
    "home.faq_adults_answer": (
        "نعم، تشمل الرعاية المعتمدة أمراض وجراحة الأنف والأذن والحنجرة للكبار "
        "والأطفال.",
        "Yes. The approved profile covers adult and pediatric ear, nose and "
        "throat medicine and surgery.",
    ),
    "doctor.profile_label": ("الملف التعريفي", "Doctor Profile"),
    "doctor.bio_label": ("نبذة مهنية", "Professional Profile"),
    "doctor.bio_title": (
        "خبرة متخصصة ورعاية واضحة",
        "Specialist experience, clearly presented",
    ),
    "doctor.booking_label": ("الزيارة والحجز", "Visit & Booking"),
    "doctor.booking_title": ("احجز دون تسجيل دخول", "Book without signing in"),
    "doctor.booking_intro": (
        "اختر نوع الزيارة والموعد المتاح، ثم أكّد بيانات التواصل.",
        "Choose a visit type and an available time, then confirm your contact details.",
    ),
    "doctor.directions": ("الاتجاهات إلى العيادة", "Directions to the clinic"),
    "doctor.path_label": ("المسار المهني", "Professional Path"),
    "doctor.path_title": (
        "الخبرة والتعليم والمؤهلات",
        "Experience, education, and credentials",
    ),
    "doctor.clinical_label": ("الرعاية السريرية", "Clinical Care"),
    "doctor.clinical_title": (
        "التخصصات والحالات التي يعالجها الدكتور",
        "Specialties and conditions treated",
    ),
    "doctor.cta_title": (
        "هل ترغب في حجز استشارة؟",
        "Ready to schedule a consultation?",
    ),
    "doctor.cta_directions": ("الاتجاهات", "Get Directions"),
    "services.groups_label": ("التصنيفات الطبية", "Service Groups"),
    "services.groups_title": ("تصنيف واضح للخدمات", "Clear service categories"),
    "services.visits_label": ("أنواع الزيارات", "Visit Types"),
    "services.visits_title": (
        "اختر نوع الزيارة المناسب",
        "Choose the appropriate visit type",
    ),
    "services.visits_intro": (
        "اختر نوع الزيارة ثم انتقل إلى المواعيد المتاحة. لا يلزم تسجيل الدخول للحجز.",
        "Choose a visit type, then continue to the available appointment times. "
        "Sign-in is not required to book.",
    ),
    "contact.map_link": ("فتح الموقع على Google Maps", "Open in Google Maps"),
    "contact.location_label": ("موقع العيادة", "Clinic Location"),
    "contact.phone_label": ("الهاتف", "Phone"),
    "contact.directions": ("الحصول على الاتجاهات", "Get Directions"),
    "contact.gallery_label": ("داخل العيادة", "Inside the Clinic"),
    "contact.gallery_title": (
        "مساحة هادئة ومجهزة بعناية",
        "A calm, thoughtfully equipped clinic",
    ),
}

HOME_VISIBILITY = {
    "home.section_doctor": ("إظهار نبذة الطبيب", "Show doctor preview"),
    "home.section_cases": ("إظهار الحالات العامة", "Show public cases"),
    "home.section_reviews": ("إظهار التقييمات", "Show reviews"),
    "home.section_faq": ("إظهار الأسئلة الشائعة", "Show FAQ"),
}


def copy_definitions():
    from .views import DOCTOR_DEFAULT, PAGE_COPY, SERVICE_GROUPS

    definitions = {}
    for field in ("hero_summary", "credential_label", "bio"):
        definitions[f"home.{field}"] = tuple(
            DOCTOR_DEFAULT[f"{field}_{lang}"] for lang in ("ar", "en")
        )
    for page in ("services", "contact"):
        for field in ("headline", "subtitle"):
            definitions[f"{page}.{field}"] = tuple(
                PAGE_COPY[lang][page][field] for lang in ("ar", "en")
            )
    definitions.update(STATIC_COPY)
    for index in range(len(SERVICE_GROUPS["ar"])):
        definitions[f"services.group_{index}_title"] = tuple(
            SERVICE_GROUPS[lang][index]["title"] for lang in ("ar", "en")
        )
        definitions[f"services.group_{index}_items"] = tuple(
            "\n".join(SERVICE_GROUPS[lang][index]["bullet_items"])
            for lang in ("ar", "en")
        )
    return definitions
