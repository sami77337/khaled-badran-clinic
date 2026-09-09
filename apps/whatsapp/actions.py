"""Localized website destinations, ready for a future provider menu adapter."""

from dataclasses import dataclass

from django.urls import reverse


@dataclass(frozen=True)
class WebsiteAction:
    key: str
    label: str
    url: str
    group: str = ""


def localized_url(route, language="ar", **kwargs):
    return reverse(route + ("_en" if language == "en" else ""), kwargs=kwargs or None)


def entry_actions(language="ar"):
    definitions = (
        ("book", "حجز موعد", "Book Appointment", "book", ""),
        ("consult_patient", "استشارة لمريض مسجل", "Registered Patient Consultation", "patient_portal_consultation_new", "consult"),
        ("consult_guest", "استشارة كزائر", "Guest Consultation", "guest_consultation_entry", "consult"),
        ("appointments", "مواعيدي", "Existing Appointments", "patient_portal_appointment_list", "appointments"),
        ("link_appointment", "ربط موعد", "Link Appointment", "patient_portal_link_appointment", "appointments"),
        ("recover_appointment", "استعادة ربط موعد", "Recover Appointment Link", "patient_portal_link_appointment_recovery", "appointments"),
        ("location", "موقع العيادة", "Clinic Location", "contact", ""),
        ("doctor", "عن الطبيب", "About the Doctor", "doctor", ""),
        ("services", "الخدمات", "Services", "services", ""),
    )
    return tuple(WebsiteAction(key, en if language == "en" else ar,
                              localized_url(route, language), group)
                 for key, ar, en, route, group in definitions)
