from django.db.models import Q

from apps.clinic.models import Doctor, VisitType


def get_active_doctor():
    return Doctor.objects.filter(is_active=True).order_by("display_order", "id").first()


def get_active_visit_types(doctor=None):
    queryset = VisitType.objects.filter(is_active=True).order_by("display_order", "name_en")
    if doctor is not None:
        queryset = queryset.filter(Q(doctor=doctor) | Q(doctor__isnull=True))
    return queryset


def get_active_visit_type(visit_type_id, doctor=None):
    queryset = get_active_visit_types(doctor=doctor)
    return queryset.filter(id=visit_type_id).first()
