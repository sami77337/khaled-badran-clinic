"""Approved AR/EN menu copy, website routes and direct clinic map destination."""

from apps.core.views import APPROVED_CLINIC_LOCATION

from .actions import entry_actions
from .configuration import website_origin


WELCOME = {
    "ar": "أهلاً بك في عيادة الدكتور خالد بدران.\nكيف يمكننا مساعدتك؟",
    "en": "Welcome to Dr. Khaled Badran Clinic.\nHow can we help you?",
}
HANDOFF = {
    "ar": "يمكنك كتابة رسالتك هنا وسيقوم فريق العيادة بالرد عليك.",
    "en": "You can write your message here and the clinic team will reply.",
}
MAIN_ROWS = (
    ("kbc_book", "حجز موعد", "Book an Appointment"),
    ("kbc_consult", "استشارة طبية", "Medical Consultation"),
    ("kbc_portal", "حساب المريض", "Patient Account"),
    ("kbc_location", "موقع العيادة", "Clinic Location"),
    ("kbc_staff", "التحدث مع العيادة", "Talk to the Clinic"),
)
MAIN_LANGUAGE_ROW = ("kbc_language", "اللغة / Language", "Language / اللغة")
BOOKING_ROWS = (
    ("kbc_book_new", "مريض جديد", "New Patient"),
    ("kbc_book_existing", "لدي سجل في العيادة", "Existing Patient"),
    ("kbc_main_menu", "القائمة الرئيسية", "Main Menu"),
)
CONSULT_ROWS = (
    ("kbc_consult_registered", "لدي حساب", "I Have an Account"),
    ("kbc_consult_guest", "المتابعة كزائر", "Continue as Guest"),
    ("kbc_main_menu", "القائمة الرئيسية", "Main Menu"),
)
LANGUAGE_ROWS = (
    ("kbc_language_ar", "العربية", "Arabic"),
    ("kbc_language_en", "English", "English"),
    ("kbc_main_menu", "القائمة الرئيسية", "Main Menu"),
)
LANGUAGE_PROMPT_ROWS = (
    ("kbc_language_ar", "العربية", "العربية"),
    ("kbc_language_en", "English", "English"),
)
DESTINATIONS = {
    "kbc_book_new": ("book", "احجز موعدك", "Book Appointment"),
    "kbc_book_existing": (
        "book_existing",
        "حجز موعد",
        "Book Appointment",
    ),
    "kbc_consult_registered": (
        "consult_patient",
        "ابدأ الاستشارة",
        "Start Consultation",
    ),
    "kbc_consult_guest": ("consult_guest", "ابدأ الاستشارة", "Start Consultation"),
    "kbc_portal": ("portal", "دخول حساب المريض", "Patient Sign In"),
    "kbc_location": ("location", "فتح الموقع", "Open Map"),
}
ICE_BREAKER_SELECTIONS = {
    "حجز موعد": "kbc_book",
    "book an appointment": "kbc_book",
    "استشارة طبية": "kbc_consult",
    "medical consultation": "kbc_consult",
    "حساب المريض": "kbc_portal",
    "patient account": "kbc_portal",
    "التحدث مع العيادة": "kbc_staff",
    "talk to the clinic": "kbc_staff",
    "موقع العيادة": "kbc_location",
    "clinic location": "kbc_location",
}
ICE_BREAKER_LANGUAGES = {
    "حجز موعد": "ar",
    "استشارة طبية": "ar",
    "حساب المريض": "ar",
    "التحدث مع العيادة": "ar",
    "موقع العيادة": "ar",
    "book an appointment": "en",
    "medical consultation": "en",
    "patient account": "en",
    "talk to the clinic": "en",
    "clinic location": "en",
}


def _reply_buttons(rows, language):
    index = 2 if language == "en" else 1
    return [
        {"type": "reply", "reply": {"id": row[0], "title": row[index]}}
        for row in rows
    ]


def main_menu(language):
    index = 2 if language == "en" else 1
    return {
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": WELCOME[language]},
            "action": {
                "button": "Choose an option" if language == "en" else "اختر الخدمة",
                "sections": [
                    {
                        "title": "Services" if language == "en" else "الخدمات",
                        "rows": [
                            {"id": row[0], "title": row[index]} for row in MAIN_ROWS
                        ],
                    },
                    {
                        "title": "Language" if language == "en" else "اللغة",
                        "rows": [
                            {
                                "id": MAIN_LANGUAGE_ROW[0],
                                "title": MAIN_LANGUAGE_ROW[index],
                            }
                        ],
                    },
                ],
            },
        },
    }


def booking_menu(language):
    return {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": (
                    "Are you a new patient, or do you already have a patient record at the clinic?"
                    if language == "en"
                    else "هل أنت مريض جديد أم لديك سجل مريض في العيادة؟"
                )
            },
            "action": {"buttons": _reply_buttons(BOOKING_ROWS, language)},
        },
    }


def consultation_menu(language):
    return {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": "How would you like to continue?"
                if language == "en"
                else "كيف ترغب بالمتابعة؟"
            },
            "action": {"buttons": _reply_buttons(CONSULT_ROWS, language)},
        },
    }


def language_menu(language):
    return {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": "Choose your preferred language."
                if language == "en"
                else "اختر اللغة التي تفضلها."
            },
            "action": {"buttons": _reply_buttons(LANGUAGE_ROWS, language)},
        },
    }


def language_prompt():
    """Bilingual two-button fallback for unrecognized inbound text."""
    return {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "اختر اللغة / Choose language"},
            "action": {"buttons": _reply_buttons(LANGUAGE_PROMPT_ROWS, "ar")},
        },
    }


def handoff_message(language):
    return {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": HANDOFF[language]},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "kbc_main_menu",
                            "title": "Main Menu" if language == "en" else "القائمة الرئيسية",
                        },
                    }
                ]
            },
        },
    }


def destination_message(selection, language):
    key, arabic, english = DESTINATIONS[selection]
    label = english if language == "en" else arabic
    if selection == "kbc_location":
        url = APPROVED_CLINIC_LOCATION["map_url"]
    else:
        action = next(action for action in entry_actions(language) if action.key == key)
        url = website_origin() + action.url
    return {
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {"text": label},
            "action": {
                "name": "cta_url",
                "parameters": {
                    "display_text": label,
                    "url": url,
                },
            },
        },
    }
