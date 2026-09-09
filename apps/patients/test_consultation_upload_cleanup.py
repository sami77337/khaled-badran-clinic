from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import OperationalError, connection
from django.test import TransactionTestCase, override_settings

from apps.patients.consultation_services import create_consultation
from apps.patients.models import Consultation, ConsultationAttachment, ConsultationNotification, Patient
from apps.patients.storage import consultation_attachment_storage


class ConsultationUploadCleanupTests(TransactionTestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix="kbc-upload-cleanup-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        settings = override_settings(PRIVATE_MEDIA_ROOT=self.root)
        settings.enable()
        self.addCleanup(settings.disable)
        self.user = get_user_model().objects.create_user(username="synthetic-upload-patient")
        Patient.objects.create(user=self.user, full_name="Synthetic upload patient")
        get_user_model().objects.create_user(username="synthetic-upload-staff", is_staff=True)
        self.existing = create_consultation(
            user=self.user, question="Existing synthetic consultation", uploaded_files=[self.upload()],
        )
        self.original_files = self.files()
        self.original_rows = self.rows()

    def upload(self):
        return SimpleUploadedFile("synthetic.pdf", b"%PDF-1.4\nSynthetic fixture", content_type="application/pdf")

    def files(self):
        return {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}

    def rows(self):
        return tuple(model.objects.count() for model in (Consultation, ConsultationAttachment, ConsultationNotification))

    def create(self):
        return create_consultation(
            user=self.user, question="Synthetic failed submission", uploaded_files=[self.upload(), self.upload()],
        )

    def assert_original_state(self):
        self.assertEqual(self.rows(), self.original_rows)
        self.assertEqual(self.files(), self.original_files)

    def test_attachment_insert_failure_removes_current_and_previous_uploads(self):
        for fail_at in (1, 2):
            with self.subTest(fail_at=fail_at):
                inserts = 0

                def fail_insert(execute, sql, params, many, context):
                    nonlocal inserts
                    if sql.lstrip().upper().startswith('INSERT INTO "PATIENTS_CONSULTATIONATTACHMENT"'):
                        inserts += 1
                        if inserts == fail_at:
                            # FileField.pre_save has already written this upload.
                            self.assertEqual(len(self.files()), len(self.original_files) + fail_at)
                            raise OperationalError("Synthetic attachment insert failure")
                    return execute(sql, params, many, context)

                with connection.execute_wrapper(fail_insert), self.assertRaises(OperationalError):
                    self.create()
                self.assertEqual(inserts, fail_at)
                self.assert_original_state()

    def test_notification_insert_failure_removes_all_new_uploads(self):
        def fail_insert(execute, sql, params, many, context):
            if sql.lstrip().upper().startswith('INSERT INTO "PATIENTS_CONSULTATIONNOTIFICATION"'):
                self.assertEqual(len(self.files()), len(self.original_files) + 2)
                raise OperationalError("Synthetic notification insert failure")
            return execute(sql, params, many, context)

        with connection.execute_wrapper(fail_insert), self.assertRaises(OperationalError):
            self.create()
        self.assert_original_state()

    def test_storage_failure_removes_previous_upload_and_preserves_existing_files(self):
        original_save = consultation_attachment_storage.save
        saves = 0

        def fail_save(*args, **kwargs):
            nonlocal saves
            saves += 1
            if saves == 2:
                raise OSError("Synthetic storage failure")
            return original_save(*args, **kwargs)

        with patch.object(consultation_attachment_storage, "save", side_effect=fail_save), self.assertRaises(OSError):
            self.create()
        self.assertEqual(saves, 2)
        self.assert_original_state()

    def test_commit_failure_removes_all_new_uploads(self):
        with patch.object(connection, "commit", side_effect=OperationalError("Synthetic commit failure")) as commit:
            with self.assertRaises(OperationalError):
                self.create()
            commit.assert_called_once()
        self.assert_original_state()
