from django.urls import path

from . import views


urlpatterns = [
    path("patients/", views.dashboard_patient_list, name="dashboard_patient_list"),
    path(
        "patients/<int:patient_id>/records/",
        views.dashboard_patient_record_detail,
        name="dashboard_patient_record_detail",
    ),
    path(
        "patients/<int:patient_id>/records/visits/new/",
        views.dashboard_visit_create,
        name="dashboard_visit_create",
    ),
    path(
        "patients/<int:patient_id>/records/notes/new/",
        views.dashboard_note_create,
        name="dashboard_note_create",
    ),
    path(
        "patients/<int:patient_id>/records/media/new/",
        views.dashboard_media_create,
        name="dashboard_media_create",
    ),
    path(
        "patients/<int:patient_id>/records/media/<uuid:public_id>/edit/",
        views.dashboard_media_update,
        name="dashboard_media_update",
    ),
]
