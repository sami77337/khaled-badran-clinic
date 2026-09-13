"""Runtime checks for the clinic's two protected filesystem stores.

This checks the operator-selected mount, not a provider's backup policy. Results
contain fixed labels only; never include uploaded filenames or exception text.
"""

import os
from pathlib import Path
import tempfile

from django.conf import settings

from .storage import private_record_media_storage, public_case_media_storage


def _overlap(first, second):
    return first.is_relative_to(second) or second.is_relative_to(first)


def _resolved_absolute_directory(value):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("An absolute directory is required.")
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise ValueError("An existing directory is required.")
    return path


def _probe(directory):
    """Write, sync, read and remove only our exclusively created synthetic file."""
    payload = b"KBC synthetic media storage write/read probe v1\n"
    with tempfile.NamedTemporaryFile(
        mode="w+b", prefix=".kbc-storage-probe-", dir=directory
    ) as probe:
        probe.write(payload)
        probe.flush()
        os.fsync(probe.fileno())
        probe.seek(0)
        if probe.read() != payload:
            raise OSError("Synthetic probe did not round trip.")


def check_media_storage(*, mount_root, write_probe=False):
    checks = []

    def add(name, passed):
        checks.append({"name": name, "status": "pass" if passed else "fail"})

    def report():
        return {
            "command": "check_media_storage",
            "status": "passed" if all(row["status"] == "pass" for row in checks) else "failed",
            "write_probe_requested": bool(write_probe),
            "checks": checks,
        }

    try:
        mount = _resolved_absolute_directory(mount_root)
        # The container's root filesystem is itself a mount, but is ephemeral.
        mounted = mount != Path(mount.anchor) and os.path.ismount(mount)
        add("persistent_mount_present", mounted)
        if not mounted:
            return report()
        mount_device = mount.stat().st_dev
    except (OSError, RuntimeError, TypeError, ValueError):
        if not checks:
            add("persistent_mount_present", False)
        else:
            add("persistent_mount_readable", False)
        return report()

    roots = {}
    for label, storage in (
        ("private", private_record_media_storage),
        ("public_cases", public_case_media_storage),
    ):
        try:
            root = _resolved_absolute_directory(storage.base_location)
            contained = root != mount and root.is_relative_to(mount)
            # A nested different-device mount must not masquerade as this disk.
            contained = contained and root.stat().st_dev == mount_device
            add(f"{label}_on_persistent_mount", contained)
            if contained:
                roots[label] = root
        except (OSError, RuntimeError, TypeError, ValueError):
            add(f"{label}_on_persistent_mount", False)

    if len(roots) != 2:
        return report()

    add("media_roots_separate", not _overlap(roots["private"], roots["public_cases"]))
    try:
        public_paths = [settings.MEDIA_ROOT, settings.STATIC_ROOT]
        for entry in settings.STATICFILES_DIRS:
            public_paths.append(entry[1] if isinstance(entry, (tuple, list)) else entry)
        public_roots = [Path(value).resolve() for value in public_paths if value]
        add(
            "media_roots_outside_public_directories",
            all(not _overlap(root, public) for root in roots.values() for public in public_roots),
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        add("media_roots_outside_public_directories", False)

    # Do not write anything if any mount, containment or privacy check failed.
    if write_probe and all(row["status"] == "pass" for row in checks):
        for label, root in roots.items():
            try:
                _probe(root)
                add(f"{label}_write_read_cleanup", True)
            except (OSError, RuntimeError, ValueError):
                add(f"{label}_write_read_cleanup", False)

    return report()
