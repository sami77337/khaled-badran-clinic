# Batch 7 Status - Staging Readiness Validation and Operational Runbooks

## Scope Implemented

Batch 7 adds a staging/infrastructure validation layer before any patient portal, uploads, WhatsApp integration, payments, medical records, or medical automation work.

Implemented:

- Safe `deployment_smoke` Django management command.
- Local/staging/production command guidance.
- Explicit local, staging, and production environment profiles.
- Backup and restore runbook.
- Incident response runbook.
- Release checklist with pre-portal safety gates.
- Load and concurrency test plan.
- Security regression checklist.
- CI smoke-check integration using local SQLite only.
- Tests for smoke output, strict mode, redaction, docs, CI, and pre-portal route safety.

## Management Command

Added:

```bash
python manage.py deployment_smoke
python manage.py deployment_smoke --json
python manage.py deployment_smoke --strict
```

The command checks startup, safe settings summary, database connectivity, migration state, cache reachability, active public content, booking settings, health/readiness imports, readiness DB behavior, production-readiness checks, and public booking safety boundaries.

The command does not print application secret values, database connection strings, cache connection strings, passwords, tokens, cookies, or raw environment dumps.

## Staging Guidance

Staging should use `config.settings.prod` and must be production-like but non-public or restricted.

Staging requirements:

- own generated application secret,
- exact allowed hosts,
- CSRF trusted HTTPS origins,
- PostgreSQL, not SQLite,
- Redis/shared cache, not LocMemCache,
- HTTPS,
- no real patient data,
- seed commands only for public/booking demo setup,
- secure uncommitted admin credentials.

No `config/settings/staging.py` was added in Batch 7 because `config.settings.prod` already provides the safest staging baseline.

## New Operational Documents

- `docs/BACKUP_RESTORE_RUNBOOK.md`
- `docs/INCIDENT_RESPONSE_RUNBOOK.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/LOAD_TEST_PLAN.md`
- `docs/SECURITY_REGRESSION_CHECKLIST.md`

## CI

CI now runs:

- `python manage.py makemigrations --check --dry-run`
- `python manage.py check`
- `python manage.py migrate --noinput`
- `python manage.py deployment_smoke`
- `python manage.py test`

CI still uses SQLite and LocMemCache, requires no real secrets, and does not require PostgreSQL or Redis services.

## Verification

Focused implementation check:

```bash
python manage.py test apps.core
# Found 39 test(s).
# Ran 39 tests.
# OK
```

Required Batch 7 command sequence:

```bash
python manage.py makemigrations --check --dry-run
# No changes detected
```

```bash
python manage.py check
# System check identified no issues (0 silenced).
```

```bash
python manage.py check --deploy
# System check identified 6 issues (0 silenced).
```

`check --deploy` was run with local development settings (`config.settings.dev`). The six warnings are expected for local development and show that local settings are not production settings:

- `security.W004`: `SECURE_HSTS_SECONDS` is not set.
- `security.W008`: `SECURE_SSL_REDIRECT` is not true.
- `security.W009`: the local development secret is not production-strength.
- `security.W012`: `SESSION_COOKIE_SECURE` is not true.
- `security.W016`: `CSRF_COOKIE_SECURE` is not true.
- `security.W018`: `DEBUG=True`.

```bash
python manage.py deployment_smoke
# Result: WARNING (13 pass, 4 warning, 0 failure, 0 strict blocker)
```

Local `deployment_smoke` warnings are expected under `config.settings.dev`:

- `local_debug_enabled`: DEBUG is enabled for local development.
- `local_sqlite_database`: SQLite is active locally; staging/production must use PostgreSQL.
- `local_locmem_cache`: LocMemCache is active locally; staging/production must use Redis/shared cache.
- `local_https_redirect_disabled`: HTTPS redirect is disabled locally.

The smoke command also confirmed database connectivity, applied migrations, cache set/get/delete, active clinic profile, active doctor, active visit types, booking settings, health/readiness imports, readiness database check, and public booking UUID/staff-only safety summary.

```bash
python manage.py deployment_smoke --json
# Valid JSON emitted.
# status=warning, exit_code=0, passes=13, warnings=4, failures=0, strict_blockers=0.
```

```bash
python manage.py test
# Found 170 test(s).
# Ran 170 tests.
# OK
```

```bash
python manage.py seed_public_content
# Seeded public content: clinic=updated, doctor=updated, visit_types_created=0, visit_types_updated=9.
# No patients, appointments, WhatsApp messages, files, prices, or booking slots were created.
```

```bash
python manage.py seed_booking_demo
# Seeded public content: clinic=updated, doctor=updated, visit_types_created=0, visit_types_updated=9.
# No patients, appointments, WhatsApp messages, files, prices, or booking slots were created.
# Seeded booking demo setup: settings_created=0, settings_updated=7, schedules_created=0, schedules_updated=5.
# No patients, appointments, WhatsApp messages, uploads, secrets, or payments were created.
# Current patient_count=0, appointment_count=0.
```

```bash
python manage.py test
# Found 170 test(s).
# Ran 170 tests.
# OK
```

The test output includes expected warning logs from negative route/access tests for 404, 400, and 403 responses.

No real staging environment was used. This batch validates local tooling and documentation only; it does not prove staging or production readiness.

## Intentionally Out of Scope

- Deployment.
- Commits, pushes, or merges.
- Patient portal.
- File uploads.
- WhatsApp API sending.
- WhatsApp webhooks.
- Online payments.
- Medical records.
- Medical AI, diagnosis automation, triage automation, or treatment automation.
- Real secrets.
- Real credentials.
- Real patient data.
- Provider-specific deployment lock-in.

## Remaining Risks

- No real staging infrastructure has been provisioned or validated.
- PostgreSQL and Redis have not been exercised in this local Batch 7 run.
- Reverse proxy headers and HTTPS behavior have not been validated through real infrastructure.
- Backup/restore runbook exists, but no restore drill has been performed.
- Incident response runbook exists, but no live incident exercise has been performed.
- Load/concurrency plan exists, but no load test has been run.
- Legal/privacy review is still required before launch and before patient portal, uploads, WhatsApp, or medical records.

## Recommended Next Batch

Provision restricted staging and use the Batch 7 tooling against real production-like infrastructure before building patient portal, uploads, WhatsApp, or medical records.
