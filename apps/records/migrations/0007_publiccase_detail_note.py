from django.db import migrations, models


SHORT_NOTE_MAX_LENGTH = 180


def classify_existing_public_case_notes(apps, schema_editor):
    PublicCase = apps.get_model("records", "PublicCase")
    for public_case in PublicCase.objects.all().only("pk", "note", "detail_note").iterator():
        original_note = public_case.note or ""
        if len(original_note.strip()) <= SHORT_NOTE_MAX_LENGTH:
            continue
        PublicCase.objects.filter(pk=public_case.pk).update(
            note="",
            detail_note=original_note,
        )


def restore_long_notes(apps, schema_editor):
    PublicCase = apps.get_model("records", "PublicCase")
    for public_case in PublicCase.objects.all().only("pk", "note", "detail_note").iterator():
        detail_note = public_case.detail_note or ""
        if public_case.note or len(detail_note.strip()) <= SHORT_NOTE_MAX_LENGTH:
            continue
        PublicCase.objects.filter(pk=public_case.pk).update(
            note=detail_note,
            detail_note="",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0006_recordmedia_trashed_at_recordmedia_trashed_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="publiccase",
            name="detail_note",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(
            classify_existing_public_case_notes,
            restore_long_notes,
        ),
    ]
