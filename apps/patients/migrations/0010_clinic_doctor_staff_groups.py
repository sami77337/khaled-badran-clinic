from django.db import migrations


DOCTOR_GROUP = "KBC Doctor"
STAFF_GROUP = "KBC Clinic Staff"


def setup_clinic_groups(apps, schema_editor):
    """Provision role definitions, never reclassify real existing users."""
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    db = schema_editor.connection.alias

    doctor, _created = Group.objects.using(db).get_or_create(name=DOCTOR_GROUP)
    Group.objects.using(db).get_or_create(name=STAFF_GROUP)

    # New test databases may not yet have default permissions; Django normally
    # creates them at post_migrate, after all migration operations finish.
    for model_name in ("consultation", "transientconsultation"):
        content_type, _created = ContentType.objects.using(db).get_or_create(
            app_label="patients", model=model_name,
        )
        codename = f"change_{model_name}"
        permission, _created = Permission.objects.using(db).get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": f"Can change {model_name}"},
        )
        doctor.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0009_backfill_verified_account_patient_profiles"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        # No reverse deletion: account-group assignments must not be erased
        # by an unrelated migration rollback.
        migrations.RunPython(setup_clinic_groups, migrations.RunPython.noop),
    ]
