"""Encrypted offsite backup primitives for production operations only."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from django.apps import apps
from django.conf import settings
from django.db import connection, models, transaction

logger = logging.getLogger(__name__)

FORMAT_MAGIC = b"KBCBKP01"
NONCE_SIZE = 12
PART_SIZE = 8 * 1024 * 1024
STATUS_DIR = Path("/var/data/.backup-status")
SNAPSHOT_DIR = Path("/var/data/.backup-snapshots")
LOCK_FILE = Path("/var/data/.backup.lock")
VAPID_PRIVATE_KEY = Path("/var/data/webpush/vapid-private.key")


class BackupError(RuntimeError):
    """Sanitized backup failure."""


def _utc_now():
    return datetime.now(timezone.utc)


def _required_env(name):
    value = (os.getenv(name) or "").strip()
    if not value:
        raise BackupError("Backup configuration unavailable.")
    return value


def _encryption_key():
    raw = _required_env("KBC_BACKUP_ENCRYPTION_KEY_B64")
    try:
        key = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error):
        raise BackupError("Backup encryption configuration invalid.") from None
    if len(key) != 32:
        raise BackupError("Backup encryption configuration invalid.")
    return key


def _r2_config():
    endpoint = _required_env("KBC_R2_ENDPOINT_URL")
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or not parsed.hostname.endswith(".eu.r2.cloudflarestorage.com")
    ):
        raise BackupError("Backup destination configuration invalid.")
    return {
        "endpoint": endpoint.rstrip("/"),
        "bucket": _required_env("KBC_R2_BUCKET"),
        "access_key": _required_env("KBC_R2_ACCESS_KEY_ID"),
        "secret_key": _required_env("KBC_R2_SECRET_ACCESS_KEY"),
        "key_id": _required_env("KBC_BACKUP_KEY_ID"),
    }


def _media_roots():
    roots = {
        "private": Path(settings.PRIVATE_MEDIA_ROOT).resolve(),
        "public-cases": Path(settings.PUBLIC_CASE_MEDIA_ROOT).resolve(),
    }
    mount = Path("/var/data").resolve()
    if not settings.PRODUCTION:
        raise BackupError("Offsite backup is production-only.")
    for root in roots.values():
        try:
            root.relative_to(mount)
        except ValueError:
            raise BackupError("Production media storage configuration invalid.") from None
        if not root.is_dir():
            raise BackupError("Production media storage unavailable.")
    return roots


def _safe_run_id(run_id):
    if not run_id or len(run_id) > 80:
        raise BackupError("Backup run identifier invalid.")
    if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in run_id):
        raise BackupError("Backup run identifier invalid.")
    return run_id


def write_status(run_id, status):
    run_id = _safe_run_id(run_id)
    if status not in {"queued", "running", "success", "failed"}:
        raise BackupError("Backup status invalid.")
    STATUS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps(
        {"run_id": run_id, "status": status, "updated_at": _utc_now().isoformat()},
        separators=(",", ":"),
    ).encode("utf-8")
    target = STATUS_DIR / f"{run_id}.json"
    temp = STATUS_DIR / f".{run_id}.tmp"
    with temp.open("wb") as handle:
        os.chmod(temp, 0o600)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, target)


def read_status(run_id):
    run_id = _safe_run_id(run_id)
    try:
        payload = json.loads((STATUS_DIR / f"{run_id}.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return None
    if payload.get("run_id") != run_id or payload.get("status") not in {
        "queued",
        "running",
        "success",
        "failed",
    }:
        return None
    return {"run_id": run_id, "status": payload["status"], "updated_at": payload.get("updated_at", "")}


@contextmanager
def _backup_lock():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_FILE.open("a+b")
    os.chmod(LOCK_FILE, 0o600)
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, BlockingIOError, OSError):
            raise BackupError("Another backup is already running.") from None
        yield
    finally:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        handle.close()


def _hardlink_tree(source, destination):
    source = source.resolve()
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    file_count = 0
    byte_count = 0
    for current, dirnames, filenames in os.walk(source, followlinks=False):
        current_path = Path(current)
        relative = current_path.relative_to(source)
        target_dir = destination / relative
        target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        for dirname in tuple(dirnames):
            child = current_path / dirname
            if child.is_symlink():
                raise BackupError("Media snapshot contains unsupported links.")
        for filename in filenames:
            source_file = current_path / filename
            if source_file.is_symlink() or not source_file.is_file():
                raise BackupError("Media snapshot contains unsupported files.")
            target = target_dir / filename
            try:
                os.link(source_file, target, follow_symlinks=False)
                stat = target.stat()
            except OSError:
                raise BackupError("Media snapshot could not be created.") from None
            file_count += 1
            byte_count += stat.st_size
    return file_count, byte_count


def _file_references_for_roots(roots):
    root_lookup = {root: label for label, root in roots.items()}
    refs = {label: set() for label in roots}
    for model in apps.get_models():
        for field in model._meta.local_fields:
            if not isinstance(field, models.FileField):
                continue
            try:
                location = Path(field.storage.location).resolve()
            except (AttributeError, TypeError, ValueError, OSError):
                continue
            label = root_lookup.get(location)
            if label is None:
                continue
            queryset = model._base_manager.using("default").exclude(**{field.name: ""})
            for value in queryset.values_list(field.name, flat=True).iterator(chunk_size=500):
                name = str(value or "").replace("\\", "/").strip("/")
                if not name:
                    continue
                path = Path(name)
                if path.is_absolute() or ".." in path.parts:
                    raise BackupError("Stored media reference is invalid.")
                refs[label].add(path)
    return refs


def _verify_snapshot_references(snapshot_roots, references):
    for label, paths in references.items():
        root = snapshot_roots[label]
        for relative in paths:
            candidate = root / relative
            if candidate.is_symlink() or not candidate.is_file():
                raise BackupError("Database/media backup consistency check failed.")


def _run_pg_dump(target, snapshot_name):
    database_url = _required_env("DATABASE_URL")
    env = {"PGDATABASE": database_url}
    for name in ("PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH"):
        if os.getenv(name):
            env[name] = os.environ[name]
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        f"--snapshot={snapshot_name}",
        f"--file={target}",
    ]
    try:
        result = subprocess.run(
            command,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=1800,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise BackupError("PostgreSQL backup failed.") from None
    if result.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        raise BackupError("PostgreSQL backup failed.")


class _MultipartWriter:
    def __init__(self, client, bucket, key, metadata):
        self.client = client
        self.bucket = bucket
        self.key = key
        self.upload_id = None
        self.parts = []
        self.part_number = 1
        self.buffer = bytearray()
        self.sha256 = hashlib.sha256()
        self.total = 0
        response = self.client.create_multipart_upload(
            Bucket=bucket,
            Key=key,
            ContentType="application/octet-stream",
            Metadata=metadata,
        )
        self.upload_id = response["UploadId"]

    def write(self, data):
        if not data:
            return 0
        data = bytes(data)
        self.sha256.update(data)
        self.total += len(data)
        self.buffer.extend(data)
        while len(self.buffer) >= PART_SIZE:
            part = bytes(self.buffer[:PART_SIZE])
            del self.buffer[:PART_SIZE]
            self._upload_part(part)
        return len(data)

    def _upload_part(self, part):
        md5 = base64.b64encode(hashlib.md5(part, usedforsecurity=False).digest()).decode("ascii")
        response = self.client.upload_part(
            Bucket=self.bucket,
            Key=self.key,
            UploadId=self.upload_id,
            PartNumber=self.part_number,
            Body=part,
            ContentMD5=md5,
        )
        self.parts.append({"PartNumber": self.part_number, "ETag": response["ETag"]})
        self.part_number += 1

    def finalize(self):
        if self.buffer:
            self._upload_part(bytes(self.buffer))
            self.buffer.clear()
        if not self.parts:
            raise BackupError("Encrypted backup artifact is empty.")
        self.client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=self.key,
            UploadId=self.upload_id,
            MultipartUpload={"Parts": self.parts},
        )
        self.upload_id = None
        return self.sha256.hexdigest(), self.total

    def abort(self):
        if not self.upload_id:
            return
        try:
            self.client.abort_multipart_upload(
                Bucket=self.bucket,
                Key=self.key,
                UploadId=self.upload_id,
            )
        except Exception:
            pass
        self.upload_id = None


class _EncryptingWriter:
    def __init__(self, destination, key):
        self.destination = destination
        self.nonce = os.urandom(NONCE_SIZE)
        self.encryptor = Cipher(algorithms.AES(key), modes.GCM(self.nonce)).encryptor()
        self.position = 0
        self._write_raw(FORMAT_MAGIC + self.nonce)

    def writable(self):
        return True

    def tell(self):
        return self.position

    def _write_raw(self, data):
        if data:
            self.destination.write(data)
            self.position += len(data)

    def write(self, data):
        data = bytes(data)
        self._write_raw(self.encryptor.update(data))
        return len(data)

    def flush(self):
        return None

    def finalize(self):
        self._write_raw(self.encryptor.finalize())
        self._write_raw(self.encryptor.tag)


def _r2_client(config):
    return boto3.client(
        "s3",
        endpoint_url=config["endpoint"],
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        region_name="auto",
        config=Config(
            retries={"max_attempts": 4, "mode": "standard"},
            connect_timeout=10,
            read_timeout=120,
        ),
    )


def _verify_uploaded_object(client, bucket, key, expected_sha256, expected_size):
    head = client.head_object(Bucket=bucket, Key=key)
    if int(head.get("ContentLength", -1)) != expected_size:
        raise BackupError("Uploaded backup verification failed.")
    response = client.get_object(Bucket=bucket, Key=key)
    digest = hashlib.sha256()
    observed = 0
    try:
        body = response["Body"]
        while True:
            chunk = body.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            observed += len(chunk)
    finally:
        try:
            response["Body"].close()
        except Exception:
            pass
    if observed != expected_size or digest.hexdigest() != expected_sha256:
        raise BackupError("Uploaded backup verification failed.")


def _manifest(created_at, db_dump, media_stats, key_id, includes_vapid):
    return {
        "format": 1,
        "created_at": created_at.isoformat(),
        "database": {
            "format": "postgresql-custom",
            "sha256": hashlib.sha256(db_dump.read_bytes()).hexdigest(),
            "bytes": db_dump.stat().st_size,
        },
        "media": {
            label: {"files": stats[0], "bytes": stats[1]}
            for label, stats in media_stats.items()
        },
        "runtime_key_material": {"webpush_vapid_private_key": bool(includes_vapid)},
        "encryption_key_id": key_id,
    }


def _add_bytes(tar, name, payload, created_at):
    info = tarfile.TarInfo(name=name)
    info.size = len(payload)
    info.mode = 0o600
    info.mtime = int(created_at.timestamp())
    tar.addfile(info, io.BytesIO(payload))


def _stream_encrypted_archive(writer, encryption_key, db_dump, snapshot_roots, manifest, vapid_snapshot):
    encrypting = _EncryptingWriter(writer, encryption_key)
    with tarfile.open(fileobj=encrypting, mode="w|") as archive:
        manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        _add_bytes(archive, "manifest.json", manifest_bytes, _utc_now())
        archive.add(db_dump, arcname="database.dump", recursive=False)
        archive.add(snapshot_roots["private"], arcname="media/private", recursive=True)
        archive.add(snapshot_roots["public-cases"], arcname="media/public-cases", recursive=True)
        if vapid_snapshot is not None:
            archive.add(vapid_snapshot, arcname="runtime/webpush/vapid-private.key", recursive=False)
    encrypting.finalize()


def _object_key(created_at):
    stamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    return f"production/{created_at:%Y/%m/%d}/{stamp}-{os.urandom(4).hex()}.kbc"


def _cleanup_stale_snapshots():
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    for child in SNAPSHOT_DIR.iterdir():
        try:
            if child.is_symlink() or child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
        except OSError:
            raise BackupError("Stale backup workspace cleanup failed.") from None


def run_offsite_backup(run_id):
    run_id = _safe_run_id(run_id)
    roots = _media_roots()
    config = _r2_config()
    key = _encryption_key()
    created_at = _utc_now()
    object_key = _object_key(created_at)
    snapshot_parent = SNAPSHOT_DIR / run_id
    writer = None

    with _backup_lock():
        _cleanup_stale_snapshots()
        if snapshot_parent.exists():
            raise BackupError("Backup workspace already exists.")
        snapshot_parent.mkdir(parents=True, mode=0o700)
        try:
            snapshot_roots = {label: snapshot_parent / label for label in roots}
            with tempfile.TemporaryDirectory(prefix="kbc-backup-") as temp_dir:
                db_dump = Path(temp_dir) / "database.dump"
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                        cursor.execute("SELECT pg_export_snapshot()")
                        snapshot_name = cursor.fetchone()[0]
                    references = _file_references_for_roots(roots)
                    media_stats = {
                        label: _hardlink_tree(root, snapshot_roots[label])
                        for label, root in roots.items()
                    }
                    _verify_snapshot_references(snapshot_roots, references)
                    _run_pg_dump(db_dump, snapshot_name)

                vapid_snapshot = None
                if VAPID_PRIVATE_KEY.is_file() and not VAPID_PRIVATE_KEY.is_symlink():
                    vapid_dir = snapshot_parent / "runtime-webpush"
                    vapid_dir.mkdir(mode=0o700)
                    vapid_snapshot = vapid_dir / "vapid-private.key"
                    os.link(VAPID_PRIVATE_KEY, vapid_snapshot, follow_symlinks=False)

                manifest = _manifest(
                    created_at,
                    db_dump,
                    media_stats,
                    config["key_id"],
                    vapid_snapshot is not None,
                )
                client = _r2_client(config)
                writer = _MultipartWriter(
                    client,
                    config["bucket"],
                    object_key,
                    {
                        "kbc-format": "1",
                        "key-id": config["key_id"],
                        "created-at": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    },
                )
                try:
                    _stream_encrypted_archive(
                        writer,
                        key,
                        db_dump,
                        snapshot_roots,
                        manifest,
                        vapid_snapshot,
                    )
                    digest, size = writer.finalize()
                    _verify_uploaded_object(client, config["bucket"], object_key, digest, size)
                    checksum_body = f"{digest}  {object_key}\n".encode("ascii")
                    client.put_object(
                        Bucket=config["bucket"],
                        Key=f"{object_key}.sha256",
                        Body=checksum_body,
                        ContentType="text/plain",
                        ContentMD5=base64.b64encode(
                            hashlib.md5(checksum_body, usedforsecurity=False).digest()
                        ).decode("ascii"),
                    )
                    checksum_head = client.head_object(
                        Bucket=config["bucket"],
                        Key=f"{object_key}.sha256",
                    )
                    if int(checksum_head.get("ContentLength", -1)) != len(checksum_body):
                        raise BackupError("Uploaded backup verification failed.")
                except Exception:
                    writer.abort()
                    raise
        finally:
            shutil.rmtree(snapshot_parent, ignore_errors=True)

    return {"status": "success"}
