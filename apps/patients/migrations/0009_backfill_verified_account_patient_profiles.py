import re

from django.conf import settings
from django.db import migrations


PLUS_NUMBER_RE = re.compile(r"^\+[1-9]\d{7,14}$")
JORDAN_LOCAL_MOBILE_RE = re.compile(r"^07\d{8}$")
JORDAN_PICKER_MOBILE_RE = re.compile(r"^7\d{8}$")
JORDAN_INTERNATIONAL_RE = re.compile(r"^\+9627\d{8}$")
UNVERIFIED_GROUP = "patient_phone_unverified_temporary"


def normalize_phone(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return ""

    compact = re.sub(r"[\s\-().]", "", value)
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    elif compact.startswith("962"):
        compact = "+" + compact

    if JORDAN_LOCAL_MOBILE_RE.match(compact):
        return "+962" + compact[1:]
    if JORDAN_PICKER_MOBILE_RE.match(compact):
        return "+962" + compact
    if JORDAN_INTERNATIONAL_RE.match(compact):
        return compact
    if compact.startswith("+") and PLUS_NUMBER_RE.match(compact):
        return compact
    return ""


def backfill_missing_profiles(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".", 1)
    User = apps.get_model(app_label, model_name)
    Patient = apps.get_model("patients", "Patient")

    candidates = (
        User.objects.filter(
            is_active=True,
            is_staff=False,
            is_superuser=False,
            patient_profile__isnull=True,
        )
        .exclude(groups__name=UNVERIFIED_GROUP)
        .distinct()
        .order_by("pk")
    )

    raw_only_rows = list(
        Patient.objects.filter(phone_e164="").values_list("phone_raw", flat=True)
    )
    normalized_raw_phones = {
        normalized
        for raw_phone in raw_only_rows
        if (normalized := normalize_phone(raw_phone))
    }

    for user in candidates.iterator():
        phone = normalize_phone(user.username)
        if not phone:
            continue

        # Never claim or duplicate an existing medical record. Historical
        # same-phone records remain linkable only through the secure link flow.
        if Patient.objects.filter(phone_e164=phone).exists():
            continue
        if phone in normalized_raw_phones:
            continue

        display_name = (user.first_name or "").strip() or "Patient"
        Patient.objects.create(
            user_id=user.pk,
            full_name=display_name,
            phone_raw=(user.username or "").strip(),
            phone_e164=phone,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0008_accountotpchallenge"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(backfill_missing_profiles, migrations.RunPython.noop),
    ]
