# Permanent encrypted offsite backup — Cloudflare R2

## Scope

Issue #111 covers a production backup independent of Render's short recovery
window. The backup contains:

- PostgreSQL production data as a custom-format logical dump;
- protected media under `/var/data/private`;
- public-case media under `/var/data/public-cases`;
- the auto-provisioned Web Push VAPID private key at
  `/var/data/webpush/vapid-private.key` when that runtime key exists.

It does not change application business logic and does not define a legal
retention period.

## Architecture

```text
Render cron
  -> authenticated private-network trigger
  -> detached backup process on the production web instance
  -> PostgreSQL exported snapshot
  -> hard-link media snapshot on /var/data
  -> database/media reference consistency check
  -> pg_dump custom-format dump
  -> tar stream
  -> AES-256-GCM encryption on Render
  -> multipart upload to private Cloudflare R2
  -> full encrypted-object readback SHA-256 verification
  -> private .sha256 sidecar
  -> sanitized success/failure status
```

The backup process runs on the production web instance because Render cron and
one-off jobs cannot access the web service's persistent disk. The cron is only
the trigger and status waiter.

## Required Render environment names

Production web service:

- `KBC_R2_ENDPOINT_URL`
- `KBC_R2_BUCKET`
- `KBC_R2_ACCESS_KEY_ID`
- `KBC_R2_SECRET_ACCESS_KEY`
- `KBC_BACKUP_ENCRYPTION_KEY_B64`
- `KBC_BACKUP_KEY_ID`
- `KBC_BACKUP_CRON_TOKEN`

Backup cron:

- `KBC_BACKUP_INTERNAL_ORIGIN`
- `KBC_BACKUP_CRON_TOKEN`

Do not place values in Git, issues, screenshots, chat or shell transcripts.

`KBC_BACKUP_ENCRYPTION_KEY_B64` is the standard Base64 representation of
exactly 32 random bytes. Keep the recovery copy outside both Render and R2.
`KBC_BACKUP_KEY_ID` is a non-secret identifier only.

The R2 token must remain restricted to the single backup bucket with only the
object permissions required for this job. Public bucket access and `r2.dev`
must remain disabled.

## Consistency boundary

The backup command opens a PostgreSQL read-only repeatable-read transaction and
exports its snapshot. While that snapshot remains open, it:

1. records FileField references whose storage is one of the two protected roots;
2. creates hard links for both media trees on the same persistent filesystem;
3. verifies every referenced protected file exists in the hard-link snapshot;
4. executes `pg_dump --snapshot=<exported-snapshot>`.

A missing referenced file fails the run. New files created after the exported
database snapshot can appear only as harmless extra filesystem content; they do
not create database references in that dump.

Media must remain immutable after upload. Existing application workflows replace
or delete files rather than editing medical media in place.

## Encryption format

The R2 object is never uploaded in plaintext.

Artifact layout:

```text
KBCBKP01 | 12-byte random GCM nonce | AES-256-GCM ciphertext | 16-byte GCM tag
```

The encrypted plaintext is a tar stream containing:

- `manifest.json`;
- `database.dump`;
- `media/private/`;
- `media/public-cases/`;
- optional `runtime/webpush/vapid-private.key`.

The manifest contains only aggregate counts/sizes, database dump digest,
encryption key identifier, timestamp and presence/absence of the runtime key.
It does not contain patient names, phone numbers, appointment identifiers,
database URLs or secret values.

## Integrity verification

Each multipart upload part is sent with `Content-MD5`. After multipart
completion the job:

1. checks the uploaded object length with `HeadObject`;
2. reads the complete encrypted object back from R2;
3. recomputes SHA-256 and compares it with the locally streamed ciphertext hash;
4. uploads a private `.sha256` sidecar and verifies its length.

A run is not successful unless all checks pass. During restore, AES-GCM tag
validation provides an additional cryptographic integrity/authenticity check.

## Logging and status

Allowed output:

```text
Offsite backup status=running.
Offsite backup status=success.
Offsite backup status=failed.
```

The status endpoint returns only:

- random backup run ID;
- `queued`, `running`, `success` or `failed`;
- status update timestamp.

No exception string, filename, patient identifier, object key, database
connection string, token or encryption material is logged by the backup code.

## Scheduling and alerting

Run `scripts/trigger_offsite_backup.py` from a Render cron in Frankfurt. The
cron calls the production service's Render private-network origin, waits for the
sanitized terminal state and exits non-zero on failure or timeout.

Render cron failure notifications must remain enabled and routed through the
already approved production alert destinations. The cron must not contain R2
credentials or the encryption key.

No lifecycle deletion is configured by this implementation. Retention remains
owner-controlled until a separate retention/privacy decision is approved.

## Restore verification plan

Issue #111 is not recovery-ready merely because an object exists. Use this plan
for an isolated verification; never overwrite active production.

1. Select a successful backup object and matching `.sha256` sidecar.
2. Download both to a restricted isolated recovery environment.
3. Compute SHA-256 of the encrypted `.kbc` object and compare to the sidecar.
4. Obtain the matching encryption key by `KBC_BACKUP_KEY_ID` from the separate
   recovery secret store.
5. Parse `KBCBKP01`, nonce and trailing GCM tag; decrypt with AES-256-GCM.
   Abort on any authentication failure.
6. Extract into a new restricted temporary directory. Do not expose media by a
   public web server.
7. Verify `manifest.json` and compare the SHA-256 of `database.dump`.
8. Run `pg_restore --list database.dump`; abort on format/read errors.
9. Restore `database.dump` into a new isolated PostgreSQL target.
10. Place the two media directories into isolated protected filesystem roots and,
    if present, place the VAPID key into the isolated runtime-key path with
    owner-only permissions.
11. Configure an isolated application instance to use only the recovered
    database/media. Do not connect it to production WhatsApp, email, push or
    patient-facing origins.
12. Run:
    - `python manage.py makemigrations --check --dry-run`
    - `python manage.py migrate --check`
    - `python manage.py check`
    - `python manage.py check --deploy`
    - `python manage.py deployment_smoke --strict`
    - `python manage.py check_media_storage --write-probe --json`
13. Perform a protected-media consistency check against database references.
14. Record only sanitized PASS/FAIL, timestamps, backup age and RPO/RTO
    observations outside Git.
15. Destroy the isolated recovery target and plaintext extraction after owner
    approval.

The first real production restore remains issue #104 and requires an explicit
isolated recovery target because the backup contains real patient data.
