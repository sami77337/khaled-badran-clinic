import json
import os
import shutil
import subprocess
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from .durability import check_media_storage


class MediaDurabilityTests(SimpleTestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.mount = self.base / "disk"
        self.private = self.mount / "private"
        self.public_cases = self.mount / "public-cases"
        self.private.mkdir(parents=True)
        self.public_cases.mkdir()
        self.settings_override = self.settings(
            PRIVATE_MEDIA_ROOT=self.private,
            PUBLIC_CASE_MEDIA_ROOT=self.public_cases,
            MEDIA_ROOT=self.base / "media",
            STATIC_ROOT=self.base / "staticfiles",
            STATICFILES_DIRS=[self.base / "static"],
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def run_check(self, *, write_probe=False, mounted=True):
        with patch("apps.records.durability.os.path.ismount", return_value=mounted):
            return check_media_storage(mount_root=self.mount, write_probe=write_probe)

    def assert_failed(self, report, name):
        self.assertEqual(report["status"], "failed")
        self.assertIn({"name": name, "status": "fail"}, report["checks"])

    def test_directory_named_like_a_disk_does_not_prove_mount(self):
        report = check_media_storage(mount_root=self.mount, write_probe=True)
        self.assert_failed(report, "persistent_mount_present")
        self.assertEqual(list(self.private.iterdir()), [])
        self.assertEqual(list(self.public_cases.iterdir()), [])

    def test_rejects_root_filesystem_even_when_it_is_a_mount(self):
        with patch("apps.records.durability.os.path.ismount", return_value=True):
            report = check_media_storage(mount_root=Path(self.mount.anchor))
        self.assert_failed(report, "persistent_mount_present")

    def test_rejects_missing_relative_blank_and_file_mounts(self):
        file_path = self.base / "ordinary-file"
        file_path.write_bytes(b"synthetic")
        for value in (self.base / "missing", "relative/disk", "", None, file_path):
            with self.subTest(value=value):
                report = check_media_storage(mount_root=value)
                self.assert_failed(report, "persistent_mount_present")

    def test_read_only_check_preserves_existing_files_without_opening_them(self):
        existing = self.private / "synthetic-existing-file"
        existing.write_bytes(b"untouched synthetic bytes")
        with patch("apps.records.durability.tempfile.NamedTemporaryFile") as probe:
            report = self.run_check()
        self.assertEqual(report["status"], "passed")
        probe.assert_not_called()
        self.assertEqual(existing.read_bytes(), b"untouched synthetic bytes")
        self.assertEqual(list(self.private.iterdir()), [existing])

    def test_probe_round_trips_and_removes_only_its_own_files(self):
        existing = self.private / ".kbc-storage-probe-owner-file"
        existing.write_bytes(b"keep")
        report = self.run_check(write_probe=True)
        self.assertEqual(report["status"], "passed")
        for label in ("private", "public_cases"):
            self.assertIn(
                {"name": f"{label}_write_read_cleanup", "status": "pass"}, report["checks"]
            )
        self.assertEqual(list(self.private.iterdir()), [existing])
        self.assertEqual(existing.read_bytes(), b"keep")
        self.assertEqual(list(self.public_cases.iterdir()), [])

    def test_ephemeral_sibling_missing_and_mount_root_media_paths_fail(self):
        sibling = self.base / "disk-ephemeral"
        sibling.mkdir()
        for root in (sibling, self.mount / "missing", self.mount):
            for setting, label in (
                ("PRIVATE_MEDIA_ROOT", "private"),
                ("PUBLIC_CASE_MEDIA_ROOT", "public_cases"),
            ):
                with self.subTest(root=root, setting=setting), self.settings(**{setting: root}):
                    with patch("apps.records.durability._probe") as probe:
                        report = self.run_check(write_probe=True)
                    self.assert_failed(report, f"{label}_on_persistent_mount")
                    probe.assert_not_called()

    def test_dot_dot_cannot_escape_disk(self):
        with self.settings(PRIVATE_MEDIA_ROOT=self.private / ".." / ".."):
            self.assert_failed(self.run_check(), "private_on_persistent_mount")

    def test_media_roots_cannot_alias_or_contain_each_other(self):
        child = self.private / "cases"
        child.mkdir()
        for root in (self.private, child):
            with self.subTest(root=root), self.settings(PUBLIC_CASE_MEDIA_ROOT=root):
                with patch("apps.records.durability._probe") as probe:
                    report = self.run_check(write_probe=True)
                self.assert_failed(report, "media_roots_separate")
                probe.assert_not_called()

    def test_rejects_symlink_escape_from_media_directory(self):
        escaped = self.base / "ephemeral"
        escaped.mkdir()
        link = self.mount / "linked-private"
        try:
            link.symlink_to(escaped, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks requires OS permission.")
        with self.settings(PRIVATE_MEDIA_ROOT=link):
            self.assert_failed(self.run_check(), "private_on_persistent_mount")

    def test_nested_other_device_does_not_pass_as_persistent_disk(self):
        original_stat = Path.stat

        def stat(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if path == self.private:
                return SimpleNamespace(st_dev=result.st_dev + 1, st_mode=result.st_mode)
            return result

        with patch.object(Path, "stat", stat):
            self.assert_failed(self.run_check(), "private_on_persistent_mount")

    def test_static_and_public_media_aliases_are_rejected(self):
        for overrides in (
            {"MEDIA_ROOT": self.mount},
            {"STATIC_ROOT": self.private},
            {"STATICFILES_DIRS": [self.public_cases]},
            {"STATICFILES_DIRS": [("prefix", self.private)]},
            {"MEDIA_ROOT": self.private / "public-child"},
        ):
            with self.subTest(overrides=overrides), self.settings(**overrides):
                with patch("apps.records.durability._probe") as probe:
                    report = self.run_check(write_probe=True)
                self.assert_failed(report, "media_roots_outside_public_directories")
                probe.assert_not_called()

    def test_write_failure_is_sanitized_and_cleans_up_the_probe(self):
        with patch("apps.records.durability.os.fsync", side_effect=OSError("private-path-secret")):
            report = self.run_check(write_probe=True)
        self.assert_failed(report, "private_write_read_cleanup")
        self.assert_failed(report, "public_cases_write_read_cleanup")
        self.assertNotIn("private-path-secret", json.dumps(report))
        self.assertNotIn(str(self.base), json.dumps(report))
        self.assertEqual(list(self.private.iterdir()), [])
        self.assertEqual(list(self.public_cases.iterdir()), [])

    def test_unreadable_mount_returns_sanitized_failure(self):
        with patch("apps.records.durability.os.path.ismount", side_effect=OSError("private-path-secret")):
            report = check_media_storage(mount_root=self.mount)
        self.assert_failed(report, "persistent_mount_present")
        self.assertNotIn("private-path-secret", json.dumps(report))

    def test_command_success_and_json_failure_exit_without_database_access(self):
        output = StringIO()
        with patch("apps.records.durability.os.path.ismount", return_value=True):
            call_command("check_media_storage", mount_root=str(self.mount), stdout=output)
        self.assertIn("Media storage check: passed", output.getvalue())
        output = StringIO()
        with self.assertRaisesMessage(CommandError, "Media storage check failed"):
            call_command("check_media_storage", mount_root=str(self.mount), json_output=True, stdout=output)
        self.assert_failed(json.loads(output.getvalue()), "persistent_mount_present")
        self.assertNotIn(str(self.base), output.getvalue())


class ProductionStartGateTests(SimpleTestCase):
    def run_script(self, probe_exit):
        shell = shutil.which("sh")
        if not shell and Path("C:/Program Files/Git/bin/bash.exe").is_file():
            shell = "C:/Program Files/Git/bin/bash.exe"
        if not shell:
            self.skipTest("A POSIX shell is needed to exercise the production start script.")
        with TemporaryDirectory() as directory:
            for name, body in (
                ("python", 'printf "probe:%s\\n" "$*"\nexit "$KBC_TEST_PROBE_EXIT"\n'),
                ("gunicorn", 'printf "server:%s\\n" "$*"\n'),
            ):
                stub = Path(directory) / name
                stub.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
                stub.chmod(0o755)
            environment = {
                **os.environ,
                "PATH": directory + os.pathsep + os.environ.get("PATH", ""),
                "KBC_TEST_PROBE_EXIT": str(probe_exit),
                "PORT": "12345",
            }
            return subprocess.run(
                [shell, "scripts/start_production.sh", "--workers", "3", "--timeout", "60"],
                cwd=settings.BASE_DIR, env=environment, capture_output=True, text=True, timeout=15,
            )

    def test_failed_storage_probe_prevents_server_start(self):
        result = self.run_script(23)
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertIn("probe:manage.py check_media_storage --write-probe", result.stdout)
        self.assertNotIn("server:", result.stdout)

    def test_passing_probe_preserves_port_and_additional_gunicorn_arguments(self):
        result = self.run_script(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("server:config.wsgi:application --bind 0.0.0.0:12345", result.stdout)
        self.assertIn("--access-logfile - --error-logfile - --workers 3 --timeout 60", result.stdout)
