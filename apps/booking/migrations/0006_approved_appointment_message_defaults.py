from django.db import migrations


def seed_approved_messages(apps, schema_editor):
    template = apps.get_model("booking", "AppointmentMessageTemplate")
    defaults = {
        "arrived": {
            "text_ar": "تم تسجيل وصولك إلى العيادة. شكرًا لك.",
            "text_en": "Your arrival at the clinic has been recorded. Thank you.",
        },
        "no_show": {
            "text_ar": "لم يتم تسجيل حضورك للموعد. إذا كنت بحاجة إلى إعادة الجدولة، يرجى التواصل مع العيادة.",
            "text_en": "Your attendance was not recorded for this appointment. Please contact the clinic if you need to reschedule.",
        },
    }
    for event, texts in defaults.items():
        # Preserve every saved row, including deliberately disabled settings.
        template.objects.using(schema_editor.connection.alias).get_or_create(
            event=event,
            defaults={"is_active": True, **texts},
        )


class Migration(migrations.Migration):
    dependencies = [("booking", "0005_appointmentmessagetemplate")]

    operations = [
        # Rollback must not delete settings that staff may already have edited.
        migrations.RunPython(seed_approved_messages, migrations.RunPython.noop),
    ]
