from django.urls import path

from . import views


urlpatterns = [
    path("config/", views.configuration, name="staff_push_config"),
    path("subscribe/", views.subscribe, name="staff_push_subscribe"),
    path("unsubscribe/", views.subscription_state, {"remove": True}, name="staff_push_unsubscribe"),
    path("status/", views.subscription_state, name="staff_push_status"),
]
