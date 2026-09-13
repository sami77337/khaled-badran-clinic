# Production media durability — issue #62

Issue: [uploaded media lost on Render redeploy](https://github.com/sami77337/khaled-badran-clinic/issues/62).

Private records, consultation attachments/audio and approved public-case media
use two protected filesystem stores. Database rows do not contain the files.
Both stores must be on the production service's attached persistent disk.

## Required production configuration

| Render configuration | Required value for the existing service |
| --- | --- |
| Service | `khaled-badran-clinic-production` |
| Disk mount | `/var/data` |
| `MEDIA_PRIVATE_ROOT` | `/var/data/private` |
| `PUBLIC_CASE_MEDIA_PRIVATE_ROOT` | `/var/data/public-cases` |
| Runtime start command after this change is deployed | `sh scripts/start_production.sh` |

Keep the existing environment values, migration procedure, build command,
Gunicorn worker settings and service port. If the current Gunicorn command has
additional reviewed options, pass those same options after the script name.
The script uses the existing `PORT`, with `10000` as fallback, and replaces its
shell process with Gunicorn so shutdown signals reach the server.

The script explicitly exports `DJANGO_SETTINGS_MODULE=config.settings.prod`
before running either the storage check or Gunicorn. Both child processes use
production settings even if the inherited variable is absent, blank or points
to development settings. Production environment prerequisites still apply;
the script does not fall back to `manage.py`'s development default.

The check runs on the actual service instance before Gunicorn starts. It is
intentionally absent from Django startup/system checks: Render's build and
pre-deploy commands do not have access to the disk. Run it from the service's
runtime shell or start command, never a one-off job. A disk-backed deployment
briefly stops the old instance before starting the replacement. See
[Render's persistent disk documentation](https://render.com/docs/disks).

Changing an environment path does not attach a disk or recover old uploads.
Confirm the disk in Render first. Create the two empty media-root directories
on that disk if necessary; do not move or replace populated directories as an
incidental deployment step. Restore missing files only from the owner's
approved originals through the existing consent-gated manager.

## Runtime checks

Read-only inspection, without opening or listing patient files or querying the
database:

```sh
python manage.py check_media_storage --settings=config.settings.prod --json
```

Check actual write/read access as well:

```sh
python manage.py check_media_storage --settings=config.settings.prod --write-probe --json
```

Each invocation exits nonzero on failure. Output contains fixed check names and
pass/fail values only, without root paths, filenames, patient identifiers,
file hashes, environment values or exception details.

The check requires all of the following:

- `/var/data` exists as a real non-root mount point. A directory with that name
  on the ephemeral root filesystem fails.
- Both configured storage directories already exist strictly below the mount.
  Resolved paths must remain on the same filesystem device; `..`, symlink
  escapes, similar-looking sibling paths and nested different-device mounts fail.
- The two stores do not share or contain each other's roots.
- Neither store overlaps `MEDIA_ROOT`, `STATIC_ROOT` or `STATICFILES_DIRS`.
- With `--write-probe`, both roots allow an exclusive temporary synthetic file
  to be written, synced, read back and removed. No application record is created
  and no notification is sent. Existing files are not opened or removed. Failed
  validation prevents any probe write.

For a different provider-approved mount path, the command supports
`--mount-root /actual/mount`. The bundled Render start script deliberately checks
the existing `/var/data` contract. Do not bypass a failure by naming the container
root or an arbitrary filesystem mount. OS mount detection cannot establish that
an operator-selected mount is a durable paid provider disk; verify that identity
in the provider dashboard. The command does not recursively audit symlinks or
existing files inside the roots.

A passing immediate probe is evidence of current mount placement and access.
It does not prove persistence across a restart, restore capability, backup
coverage or database/file consistency. Use the drill below for that evidence.

## Controlled private-media redeploy drill

Perform this on the identified production service only during an owner-approved
deployment window. Use an explicitly identified synthetic patient and synthetic
image/video content; do not inspect or modify real patient records.

1. Record the current live commit/deploy ID, disk attachment, media-root settings
   and current start command in private operator notes. Run the runtime check
   with `--write-probe`. Stop on any failure.
2. Through the existing staff patient-record workflow, upload a small synthetic
   image to that synthetic patient's record with private-only visibility.
   Keep public-case approval and patient visibility disabled. This exercises
   the real upload validation, database row and protected storage backend.
3. Download that exact synthetic file through its authorized staff route. Record
   its UUID, byte count and SHA-256 only in private operator notes. Verify that
   an anonymous session and an unrelated synthetic patient session cannot obtain
   it through staff or patient routes. Do not put media URLs or record identifiers
   in Git or issue comments.
4. Record bounded AR/EN Home and Cases page/media availability. Check an approved
   image, lightbox navigation, video cover/poster and before/after presentation
   in both languages using existing approved public content.
5. Apply the reviewed application revision and runtime start command through one
   controlled deploy. Keep OTP outage settings, disk attachment, media roots,
   provider credentials and other service settings unchanged. Wait until Render
   reports that exact revision live; record the deploy ID and time.
6. Run the write/read check again. Through a fresh authenticated staff request,
   download the same synthetic private file and compare its bytes/hash to step
   3. Recheck the denied sessions and AR/EN public media/lightbox/poster behavior.
   Refresh from the server so a browser cache cannot stand in for persistent
   storage evidence. Media routes may reject HEAD; use controlled GETs.
7. Record only sanitized pass/fail results and deployment identifiers in the
   closeout evidence. Retain or remove the exact synthetic fixture through the
   existing supported workflow according to the agreed test-data policy. Do not
   bulk-delete patients, files or media directories.

If the private file is missing after deploy, keep issue #62 open and stop
further uploads until the storage target is corrected. A missing public case
must be restored from its approved original to the existing case record, with
both case and asset publication consent retained. A new synthetic probe must
not be substituted for the file created before redeploy.

## Backup and rollback boundaries

Persistent storage prevents the known ephemeral-filesystem deployment loss; it
does not replace backups. The backup procedure must cover both protected roots,
the matching database metadata and the separately stored Web Push key when
auto-provisioning is in use. Keep secrets and patient files outside Git.

Do not use a whole-disk snapshot restore as a deployment test: it replaces disk
state and can discard later files. Test restore on an isolated target and check
database/file consistency before any real recovery. Retention, restore evidence
and recovery objectives remain separate operations work.

If the start gate fails, inspect the named check and correct the disk/root/access
configuration in the runtime instance. Do not remove the check simply to accept
uploads on an ephemeral directory. Preserve the disk and uploaded files when
rolling application code back; changing code does not restore lost media.

## Review and deployment status

This PR implements the runtime safeguard and operator procedure for issue #62.
It does not change Render settings, enable the new start command, redeploy the
service or run a production upload test. The incident remains open until the
operator verifies the disk and approved public media, enables the reviewed start
gate and records a successful private-upload redeploy drill.

Review the existing live startup options before adopting the script. The
repository default is still the existing WSGI entry point until the operator
explicitly changes the Render start command. Build and pre-deploy commands
remain unchanged.

## Local and CI validation

Run the focused regression selection with synthetic data and development
settings (the continuations below use POSIX shell syntax):

```sh
python manage.py test apps.records \
  apps.core.tests.ProductionReadinessCheckTests \
  apps.core.tests.DeploymentSmokeCommandTests \
  apps.core.tests.ProductionSettingsReportCommandTests \
  apps.patients.test_consultation_upload_cleanup \
  apps.patients.test_consultation_audio_reply --noinput --verbosity 1
```

The 18 durability/start-gate tests cover command exit status, safe reporting,
probe cleanup, resolved path containment, root separation, public-directory
exclusion and actual shell execution with stubbed Python/Gunicorn executables.
The startup tests verify that a failed probe prevents launch and that a passing
probe preserves the configured port and additional worker/timeout arguments.
They also inspect both child processes' environments to verify production
settings selection with unset, blank and inherited development values.

Positive mount fixtures mock OS mount detection. A real ordinary unmounted
folder is also tested without mocking and must fail. The symlink regression
runs on systems that permit symlink creation; Windows can skip it when the
required OS permission is unavailable. These tests do not establish that any
provider disk is durable.

Also run the repository's full Django suite, migration-drift and Django checks,
local deployment smoke/status reports, dependency audit, Python lint on the
new modules, shell syntax validation and Git whitespace checks. The PR records
the executed commands, exact results and platform limitations. GitHub Actions
runs the full suite and dependency audit on Linux.
