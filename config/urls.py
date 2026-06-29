"""Root URL configuration for Dr. Khaled Badran Clinic."""

from django.contrib import admin
from django.urls import path

from apps.booking import views as booking_views
from apps.core import views
from apps.patients import views as patient_views


urlpatterns = [
    path("", views.home, {"language": "ar"}, name="home"),
    path("doctor/", views.doctor_profile, {"language": "ar"}, name="doctor"),
    path("services/", views.services, {"language": "ar"}, name="services"),
    path("contact/", views.contact, {"language": "ar"}, name="contact"),
    path("book/", booking_views.book_start, {"language": "ar"}, name="book"),
    path(
        "book/visit-type/",
        booking_views.select_visit_type,
        {"language": "ar"},
        name="booking_visit_type",
    ),
    path("book/slots/", booking_views.select_slot, {"language": "ar"}, name="booking_slots"),
    path(
        "book/confirm/",
        booking_views.confirm_booking,
        {"language": "ar"},
        name="booking_confirm",
    ),
    path(
        "book/success/<uuid:public_token>/",
        booking_views.booking_success,
        {"language": "ar"},
        name="booking_success",
    ),
    path("privacy/", views.privacy, {"language": "ar"}, name="privacy"),
    path("terms/", views.terms, {"language": "ar"}, name="terms"),
    path(
        "medical-disclaimer/",
        views.medical_disclaimer,
        {"language": "ar"},
        name="medical_disclaimer",
    ),
    path(
        "whatsapp-policy/",
        views.whatsapp_policy,
        {"language": "ar"},
        name="whatsapp_policy",
    ),
    path("en/", views.home, {"language": "en"}, name="home_en"),
    path("en/doctor/", views.doctor_profile, {"language": "en"}, name="doctor_en"),
    path("en/services/", views.services, {"language": "en"}, name="services_en"),
    path("en/contact/", views.contact, {"language": "en"}, name="contact_en"),
    path("en/book/", booking_views.book_start, {"language": "en"}, name="book_en"),
    path(
        "en/book/visit-type/",
        booking_views.select_visit_type,
        {"language": "en"},
        name="booking_visit_type_en",
    ),
    path(
        "en/book/slots/",
        booking_views.select_slot,
        {"language": "en"},
        name="booking_slots_en",
    ),
    path(
        "en/book/confirm/",
        booking_views.confirm_booking,
        {"language": "en"},
        name="booking_confirm_en",
    ),
    path(
        "en/book/success/<uuid:public_token>/",
        booking_views.booking_success,
        {"language": "en"},
        name="booking_success_en",
    ),
    path("staff/appointments/", booking_views.staff_appointment_list, name="staff_appointment_list"),
    path(
        "staff/appointments/<int:appointment_id>/",
        booking_views.staff_appointment_detail,
        name="staff_appointment_detail",
    ),
    path(
        "staff/appointments/<int:appointment_id>/cancel/",
        booking_views.staff_appointment_cancel,
        name="staff_appointment_cancel",
    ),
    path(
        "staff/appointments/<int:appointment_id>/reschedule/",
        booking_views.staff_appointment_reschedule,
        name="staff_appointment_reschedule",
    ),
    path(
        "staff/appointments/<int:appointment_id>/arrived/",
        booking_views.staff_appointment_arrived,
        name="staff_appointment_arrived",
    ),
    path(
        "staff/appointments/<int:appointment_id>/complete/",
        booking_views.staff_appointment_complete,
        name="staff_appointment_complete",
    ),
    path(
        "staff/appointments/<int:appointment_id>/no-show/",
        booking_views.staff_appointment_no_show,
        name="staff_appointment_no_show",
    ),
    path("en/privacy/", views.privacy, {"language": "en"}, name="privacy_en"),
    path("en/terms/", views.terms, {"language": "en"}, name="terms_en"),
    path(
        "en/medical-disclaimer/",
        views.medical_disclaimer,
        {"language": "en"},
        name="medical_disclaimer_en",
    ),
    path(
        "en/whatsapp-policy/",
        views.whatsapp_policy,
        {"language": "en"},
        name="whatsapp_policy_en",
    ),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("sitemap.xml", views.sitemap_xml, name="sitemap_xml"),
    path("health/", views.health_check, name="health"),
    path("health/ready/", views.readiness_check, name="health_ready"),
    path("portal/", patient_views.portal_dashboard, {"language": "ar"}, name="patient_portal_dashboard"),
    path("portal/login/", patient_views.portal_login, {"language": "ar"}, name="patient_portal_login"),
    path("portal/logout/", patient_views.portal_logout, {"language": "ar"}, name="patient_portal_logout"),
    path("portal/register/", patient_views.portal_register, {"language": "ar"}, name="patient_portal_register"),
    path(
        "portal/link-appointment/",
        patient_views.portal_link_appointment,
        {"language": "ar"},
        name="patient_portal_link_appointment",
    ),
    path(
        "portal/appointments/",
        patient_views.portal_appointment_list,
        {"language": "ar"},
        name="patient_portal_appointment_list",
    ),
    path(
        "portal/appointments/<uuid:public_token>/",
        patient_views.portal_appointment_detail,
        {"language": "ar"},
        name="patient_portal_appointment_detail",
    ),
    path("en/portal/", patient_views.portal_dashboard, {"language": "en"}, name="patient_portal_dashboard_en"),
    path("en/portal/login/", patient_views.portal_login, {"language": "en"}, name="patient_portal_login_en"),
    path("en/portal/logout/", patient_views.portal_logout, {"language": "en"}, name="patient_portal_logout_en"),
    path("en/portal/register/", patient_views.portal_register, {"language": "en"}, name="patient_portal_register_en"),
    path(
        "en/portal/link-appointment/",
        patient_views.portal_link_appointment,
        {"language": "en"},
        name="patient_portal_link_appointment_en",
    ),
    path(
        "en/portal/appointments/",
        patient_views.portal_appointment_list,
        {"language": "en"},
        name="patient_portal_appointment_list_en",
    ),
    path(
        "en/portal/appointments/<uuid:public_token>/",
        patient_views.portal_appointment_detail,
        {"language": "en"},
        name="patient_portal_appointment_detail_en",
    ),
    path("admin/", admin.site.urls),
]
