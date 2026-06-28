"""Root URL configuration for Dr. Khaled Badran Clinic."""

from django.contrib import admin
from django.urls import path

from apps.booking import views as booking_views
from apps.core import views


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
    path("admin/", admin.site.urls),
]
