from django.db import migrations


OLD_DEFAULTS = {
    "arrived": {
        "text_ar": "تم تسجيل وصولك إلى العيادة. شكرًا لك.",
        "text_en": "Your arrival at the clinic has been recorded. Thank you.",
    },
    "no_show": {
        "text_ar": "لم يتم تسجيل حضورك للموعد. إذا كنت بحاجة إلى إعادة الجدولة، يرجى التواصل مع العيادة.",
        "text_en": "Your attendance was not recorded for this appointment. Please contact the clinic if you need to reschedule.",
    },
}

NEW_DEFAULTS = {
    "arrived": {
        "text_ar": "مرحبًا {patient_name}، تم تسجيل وصولك لموعدك بتاريخ {appointment_date} الساعة {appointment_time}. شكرًا لك.",
        "text_en": "Hello {patient_name}, your arrival for your appointment on {appointment_date} at {appointment_time} has been recorded. Thank you.",
    },
    "no_show": {
        "text_ar": "مرحبًا {patient_name}، لم يتم تسجيل حضورك لموعدك بتاريخ {appointment_date} الساعة {appointment_time}. إذا كنت بحاجة إلى إعادة الجدولة، يرجى التواصل مع العيادة.",
        "text_en": "Hello {patient_name}, your attendance was not recorded for your appointment on {appointment_date} at {appointment_time}. Please contact the clinic if you need to reschedule.",
    },
}


def upgrade_untouched_defaults(apps, schema_editor):
    template = apps.get_model("booking", "AppointmentMessageTemplate")
    manager = template.objects.using(schema_editor.connection.alias)

    for event, old in OLD_DEFAULTS.items():
        manager.filter(
            event=event,
            is_active=True,
            updated_by__isnull=True,
            text_ar=old["text_ar"],
            text_en=old["text_en"],
        ).update(
            text_ar=NEW_DEFAULTS[event]["text_ar"],
            text_en=NEW_DEFAULTS[event]["text_en"],
        )


class Migration(migrations.Migration):
    dependencies = [("booking", "0007_appointmentstaffnotification")]

    operations = [
        migrations.RunPython(upgrade_untouched_defaults, migrations.RunPython.noop),
    ]
