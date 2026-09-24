from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class AppointmentMessageDefaultMigrationTests(TransactionTestCase):
    previous = [("booking", "0005_appointmentmessagetemplate")]
    current = [("booking", "0006_approved_appointment_message_defaults")]
    latest = [("booking", "0007_appointmentstaffnotification")]

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        return executor.loader.project_state(target).apps.get_model(
            "booking", "AppointmentMessageTemplate"
        )

    def setUp(self):
        self.addCleanup(self.migrate, self.latest)
        self.template = self.migrate(self.previous)
        self.template.objects.all().delete()

    def test_fresh_migration_seeds_exact_active_bilingual_defaults(self):
        template = self.migrate(self.current)
        self.assertEqual(template.objects.count(), 2)
        arrived = template.objects.get(event="arrived")
        no_show = template.objects.get(event="no_show")
        self.assertEqual(arrived.text_ar, "تم تسجيل وصولك إلى العيادة. شكرًا لك.")
        self.assertEqual(
            arrived.text_en, "Your arrival at the clinic has been recorded. Thank you."
        )
        self.assertEqual(
            no_show.text_ar,
            "لم يتم تسجيل حضورك للموعد. إذا كنت بحاجة إلى إعادة الجدولة، يرجى التواصل مع العيادة.",
        )
        self.assertEqual(
            no_show.text_en,
            "Your attendance was not recorded for this appointment. Please contact the clinic if you need to reschedule.",
        )
        for setting in (arrived, no_show):
            self.assertTrue(setting.is_active)
            self.assertIsNone(setting.updated_by_id)

    def test_existing_edits_and_disabled_settings_survive_application_and_reapplication(
        self,
    ):
        self.template.objects.create(
            event="arrived",
            is_active=True,
            text_ar="نص محفوظ",
            text_en="Saved operational text",
        )
        self.template.objects.create(
            event="no_show", is_active=False, text_ar="", text_en=""
        )
        original = list(self.template.objects.order_by("event").values())
        template = self.migrate(self.current)
        self.assertEqual(list(template.objects.order_by("event").values()), original)
        self.migrate(self.previous)
        template = self.migrate(self.current)
        self.assertEqual(list(template.objects.order_by("event").values()), original)
