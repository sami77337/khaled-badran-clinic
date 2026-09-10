from django.urls import path

from apps.whatsapp import views


urlpatterns = [
    path("webhook/", views.meta_webhook, name="whatsapp_meta_webhook"),
]
