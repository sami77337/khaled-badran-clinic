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
CONSULT_ROWS = (
    ("kbc_consult_registered", "لدي حساب", "I Have an Account"),
    ("kbc_consult_guest", "المتابعة كزائر", "Continue as Guest"),
)
DESTINATIONS = {
    "kbc_book": ("book", "احجز موعدك", "Book Appointment"),
    "kbc_consult_registered": (
        "consult_patient",
        "ابدأ الاستشارة",
        "Start Consultation",
    ),
    "kbc_consult_guest": ("consult_guest", "ابدأ الاستشارة", "Start Consultation"),
    "kbc_portal": ("portal", "دخول حساب المريض", "Patient Sign In"),
    "kbc_location": ("location", "افتح الموقع على الخريطة", "Open Map"),
}


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
                    {"rows": [{"id": row[0], "title": row[index]} for row in MAIN_ROWS]}
                ],
            },
        },
    }


def consultation_menu(language):
    index = 2 if language == "en" else 1
    return {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": "How would you like to continue?"
                if language == "en"
                else "كيف ترغب بالمتابعة؟"
            },
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": row[0], "title": row[index]}}
                    for row in CONSULT_ROWS
                ]
            },
        },
    }


def destination_message(selection, language):
    key, arabic, english = DESTINATIONS[selection]
    label = english if language == "en" else arabic
    if selection == "kbc_location":
        if language == "ar":
            # Preserve the 23-character label with a template URL button.
            # Its approved Google Maps URL is static: no runtime URL parameter.
            from .meta import template_content

            return template_content("LOCATION", language, [])
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
