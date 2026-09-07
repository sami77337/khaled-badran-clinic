"""Compile the services' actual locking queries with the installed PG backend.

SQLite executes the behavioral test; PostgreSQL compilation independently proves
the lock scope. No PostgreSQL connection or additional package is required.
"""
from contextlib import contextmanager
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.backends.postgresql.base import DatabaseWrapper
from django.db.models.sql.compiler import SQLCompiler
from django.test import TestCase

from apps.patients import consultation_services
from apps.patients.models import (
    Consultation, ConsultationAttachment, ConsultationAudioReply, Patient,
)


class ConsultationPostgreSQLLockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="synthetic-lock-owner")
        cls.staff = get_user_model().objects.create_user(username="synthetic-lock-staff", is_staff=True)
        cls.patient = Patient.objects.create(user=cls.user, full_name="Synthetic lock patient")

    @contextmanager
    def postgres_lock_sql(self):
        backend = DatabaseWrapper({}, alias="lock-compilation-only")
        queries = []
        original_execute = SQLCompiler.execute_sql

        def capture(compiler, *args, **kwargs):
            if compiler.query.select_for_update:
                sql, _ = compiler.query.clone().get_compiler(connection=backend).as_sql()
                queries.append((compiler.query.model, sql))
            return original_execute(compiler, *args, **kwargs)

        with patch.object(backend, "get_autocommit", return_value=False):
            with patch.object(backend, "ensure_connection", side_effect=AssertionError("No PG connection allowed")):
                with patch.object(SQLCompiler, "execute_sql", capture):
                    yield queries

    def assert_consultation_lock(self, queries, nullable_table):
        sql = next(sql for model, sql in queries if model is Consultation)
        self.assertIn(f'LEFT OUTER JOIN "{nullable_table}"', sql)
        self.assertEqual(sql.rsplit("FOR UPDATE", 1)[1].strip(), 'OF "patients_consultation"')

    def test_delete_locks_consultation_and_attachments_without_locking_optional_audio(self):
        consultation = Consultation.objects.create(patient=self.patient, question="Synthetic question")
        attachment = ConsultationAttachment.objects.create(
            consultation=consultation, file="synthetic-lock-only.jpg", content_type="image/jpeg", file_size=1,
            original_filename="synthetic-lock-only.jpg", file_category="image",
        )
        with self.postgres_lock_sql() as queries:
            consultation_services.delete_unhandled_consultation(user=self.user, public_id=consultation.public_id)
        self.assert_consultation_lock(queries, "patients_consultationaudioreply")
        self.assertTrue(any(model is ConsultationAttachment and "FOR UPDATE" in sql for model, sql in queries))
        self.assertFalse(Consultation.objects.filter(pk=consultation.pk).exists())
        self.assertFalse(ConsultationAttachment.objects.filter(pk=attachment.pk).exists())

    def test_reply_locks_consultation_and_explicit_audio_row_with_nullable_patient_user(self):
        for existing_audio in (False, True):
            with self.subTest(existing_audio=existing_audio):
                patient = Patient.objects.create(full_name="Synthetic unlinked patient")
                consultation = Consultation.objects.create(patient=patient, question="Synthetic question")
                if existing_audio:
                    ConsultationAudioReply.objects.create(
                        consultation=consultation, file="synthetic-lock-only.webm",
                        content_type="audio/webm", file_size=1, created_by=self.staff,
                    )
                with self.postgres_lock_sql() as queries:
                    updated = consultation_services.update_consultation_reply(
                        consultation=consultation, staff_user=self.staff,
                        reply="Synthetic reply", status=Consultation.Status.ANSWERED,
                    )
                self.assert_consultation_lock(queries, "auth_user")
                self.assertTrue(any(model is ConsultationAudioReply and "FOR UPDATE" in sql for model, sql in queries))
                self.assertEqual(updated.staff_reply, "Synthetic reply")
                self.assertIsNotNone(updated.staff_handled_at)
