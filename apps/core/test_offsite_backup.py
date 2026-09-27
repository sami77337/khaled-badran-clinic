import base64
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from django.test import TestCase, override_settings
from django.urls import reverse

from . import offsite_backup


class BackupCryptoTests(TestCase):
    def test_stream_encryption_uses_aes_256_gcm_and_authenticates(self):
        key = bytes(range(32))
        destination = tempfile.SpooledTemporaryFile()
        writer = offsite_backup._EncryptingWriter(destination, key)
        plaintext = b"synthetic-backup-payload"
        writer.write(plaintext)
        writer.finalize()

        destination.seek(0)
        artifact = destination.read()
        self.assertTrue(artifact.startswith(offsite_backup.FORMAT_MAGIC))
        nonce_start = len(offsite_backup.FORMAT_MAGIC)
        nonce_end = nonce_start + offsite_backup.NONCE_SIZE
        nonce = artifact[nonce_start:nonce_end]
        ciphertext = artifact[nonce_end:-16]
        tag = artifact[-16:]

        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        self.assertEqual(decryptor.update(ciphertext) + decryptor.finalize(), plaintext)

    def test_encryption_key_requires_exactly_32_bytes(self):
        with patch.dict(
            os.environ,
            {"KBC_BACKUP_ENCRYPTION_KEY_B64": base64.b64encode(b"x" * 31).decode("ascii")},
            clear=False,
        ):
            with self.assertRaises(offsite_backup.BackupError):
                offsite_backup._encryption_key()

    def test_r2_endpoint_must_be_cloudflare_https(self):
        env = {
            "KBC_R2_ENDPOINT_URL": "http://example.test",
            "KBC_R2_BUCKET": "synthetic-bucket",
            "KBC_R2_ACCESS_KEY_ID": "synthetic-access",
            "KBC_R2_SECRET_ACCESS_KEY": "synthetic-secret",
            "KBC_BACKUP_KEY_ID": "synthetic-key-id",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(offsite_backup.BackupError):
                offsite_backup._r2_config()


    def test_r2_endpoint_requires_eu_jurisdiction(self):
        env = {
            "KBC_R2_ENDPOINT_URL": "https://account-id.r2.cloudflarestorage.com",
            "KBC_R2_BUCKET": "synthetic-bucket",
            "KBC_R2_ACCESS_KEY_ID": "synthetic-access",
            "KBC_R2_SECRET_ACCESS_KEY": "synthetic-secret",
            "KBC_BACKUP_KEY_ID": "synthetic-key-id",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(offsite_backup.BackupError):
                offsite_backup._r2_config()

        env["KBC_R2_ENDPOINT_URL"] = "https://account-id.eu.r2.cloudflarestorage.com"
        with patch.dict(os.environ, env, clear=False):
            config = offsite_backup._r2_config()
        self.assertEqual(config["bucket"], "synthetic-bucket")


class BackupWorkspaceTests(TestCase):
    def test_stale_snapshot_cleanup_removes_only_backup_workspace_children(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stale = root / "stale-run"
            stale.mkdir()
            (stale / "synthetic.bin").write_bytes(b"synthetic")
            with patch.object(offsite_backup, "SNAPSHOT_DIR", root):
                offsite_backup._cleanup_stale_snapshots()
            self.assertEqual(list(root.iterdir()), [])


class BackupStatusTests(TestCase):
    def test_status_file_contains_only_sanitized_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(offsite_backup, "STATUS_DIR", Path(temp_dir)):
                offsite_backup.write_status("synthetic-run-1", "success")
                raw = (Path(temp_dir) / "synthetic-run-1.json").read_text(encoding="utf-8")
                payload = json.loads(raw)

        self.assertEqual(payload["run_id"], "synthetic-run-1")
        self.assertEqual(payload["status"], "success")
        self.assertEqual(set(payload), {"run_id", "status", "updated_at"})


@override_settings(PRODUCTION=True)
class BackupDispatchTests(TestCase):
    def setUp(self):
        self.token = "synthetic-backup-cron-token"

    def test_trigger_hides_route_without_token(self):
        with patch.dict(os.environ, {"KBC_BACKUP_CRON_TOKEN": self.token}, clear=False):
            response = self.client.post(reverse("backup_trigger"))
        self.assertEqual(response.status_code, 404)

    def test_trigger_spawns_detached_management_command(self):
        with (
            patch.dict(os.environ, {"KBC_BACKUP_CRON_TOKEN": self.token}, clear=False),
            patch("apps.core.backup_dispatch.write_status") as write_status,
            patch("apps.core.backup_dispatch.subprocess.Popen") as popen,
        ):
            response = self.client.post(
                reverse("backup_trigger"),
                HTTP_X_KBC_BACKUP_TOKEN=self.token,
            )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["status"], "accepted")
        self.assertTrue(payload["run_id"])
        write_status.assert_called_once_with(payload["run_id"], "queued")
        args, kwargs = popen.call_args
        self.assertIn("offsite_backup", args[0])
        self.assertEqual(kwargs["env"]["DJANGO_SETTINGS_MODULE"], "config.settings.prod")
        self.assertTrue(kwargs["start_new_session"])
        self.assertTrue(kwargs["close_fds"])

    def test_status_returns_only_sanitized_fields(self):
        expected = {
            "run_id": "synthetic-run-2",
            "status": "running",
            "updated_at": "2026-09-27T00:00:00+00:00",
        }
        with (
            patch.dict(os.environ, {"KBC_BACKUP_CRON_TOKEN": self.token}, clear=False),
            patch("apps.core.backup_dispatch.read_status", return_value=expected),
        ):
            response = self.client.post(
                reverse("backup_status"),
                data=json.dumps({"run_id": "synthetic-run-2"}),
                content_type="application/json",
                HTTP_X_KBC_BACKUP_TOKEN=self.token,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
