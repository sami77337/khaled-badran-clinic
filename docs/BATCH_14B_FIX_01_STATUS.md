# Batch 14B-FIX-01 Status - PostgreSQL Locking Validation Fix

## Scope

Batch 14B-FIX-01 fixed the local Docker PostgreSQL validation blocker found in
Batch 14B and reran the repository-approved local Docker PostgreSQL/Redis
validation path with synthetic local-only data.

This was a narrow bugfix and evidence batch. It did not add product features,
dashboard features, visual design, Figma work, Docker changes, dependency
changes, CI changes, deployment changes, external infrastructure, secrets, or
real patient data.

## Branch and Base

- Working branch: `codex/batch-14b-fix-01-postgresql-locking`
- Base branch: `main`
- Verified base HEAD: `66bccda682b315dc056966be1f449e574f4ac331`
- Verified base short HEAD: `66bccda`
- Verified base subject:
  `BATCH-14B: add local Docker PostgreSQL Redis validation evidence (#21)`

The preserved local branch `feat/security-operations-release-evidence` was not
used, modified, rebased, merged, deleted, pushed, or included.

## Root Cause

PostgreSQL rejected two locked query shapes that combined `select_for_update()`
with `select_related()` across nullable appointment data:

- `apps.booking.operations.get_staff_appointment` built
  `Appointment.objects.select_related("doctor", "patient", "visit_type")`
  and then applied `select_for_update()` for staff status operations.
- `apps.patients.services.link_appointment_to_user` built
  `Appointment.objects.select_for_update().select_related("patient", "doctor", "visit_type")`
  for portal appointment linking.

`Appointment.visit_type` is nullable, so `select_related("visit_type")` uses a
nullable outer join. PostgreSQL does not allow a plain `FOR UPDATE` lock to be
applied to the nullable side of that outer join.

Pre-fix reproduction:

- `python manage.py test apps.patients` with local Docker PostgreSQL:
  46 tests ran, 7 errors.
- `python manage.py test apps.booking.tests.AppointmentOperationServiceTests.test_staff_can_cancel_confirmed_appointment`
  with local Docker PostgreSQL: failed with the same PostgreSQL error.

Failure signature:

```text
django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join
```

## Files Changed

Code/test files:

- `apps/booking/operations.py`
- `apps/patients/services.py`
- `apps/core/tests.py`

Documentation files:

- `docs/BATCH_14B_FIX_01_STATUS.md`
- `docs/LOCAL_DOCKER_POSTGRES_REDIS_VALIDATION_EVIDENCE.md`
- `docs/POSTGRESQL_REDIS_VALIDATION_EVIDENCE.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/NEXT_BATCH.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`

No models, migrations, templates, CSS, JavaScript, settings, dependencies, CI,
Docker, or deployment files were changed.

## Exact Fix Summary

- Staff appointment operations now keep row locking but limit the PostgreSQL
  lock target to the base appointment row:
  `select_for_update(of=("self",))`.
- Patient portal appointment linking now keeps row locking and locks both the
  base appointment row and the non-null related patient row:
  `select_for_update(of=("self", "patient"))`.
- The nullable `visit_type` relation can still be selected for display and
  validation, but it is no longer included in the PostgreSQL `FOR UPDATE` lock
  target.
- The local default-cache test now keeps asserting LocMemCache when `CACHE_URL`
  is absent, while allowing the documented Redis override used for service
  validation. This preserves default local settings coverage and removes the
  Batch 14B Redis full-suite environment-only failure.

The fix preserves:

- staff-only appointment permissions;
- appointment row locking during staff status operations;
- patient row locking during portal appointment linking;
- appointment conflict protection;
- UUID public success behavior;
- no-account-required booking;
- portal ownership filtering;
- no-cache behavior;
- privacy boundaries.

## Commands Run

Preflight:

| Command | Result |
| --- | --- |
| `git status --short --branch` | Clean `main` tracking `origin/main`. |
| `git fetch origin` | Exit 0. |
| `git checkout main` | Already on `main`; up to date. |
| `git pull --ff-only origin main` | Already up to date. |
| `git log -1 --oneline` | `66bccda BATCH-14B: add local Docker PostgreSQL Redis validation evidence (#21)` |
| `git rev-parse HEAD` | `66bccda682b315dc056966be1f449e574f4ac331` |
| `git branch --show-current` | `main` before creating the work branch. |
| `docker --version` | `Docker version 29.6.1, build 8900f1d` |
| `docker compose version` | `Docker Compose version v5.1.4` |
| `docker info` | Exit 0; Docker Desktop daemon running on WSL2. |

Targeted reproduction and fix confirmation:

| Command | Result |
| --- | --- |
| `python manage.py test apps.patients` with local Docker PostgreSQL, before fix | Failed; 46 tests ran, 7 PostgreSQL outer-join lock errors. |
| `python manage.py test apps.booking.tests.AppointmentOperationServiceTests.test_staff_can_cancel_confirmed_appointment` with local Docker PostgreSQL, before fix | Failed with the same PostgreSQL outer-join lock error. |
| `python manage.py test apps.patients.tests.PatientPortalLinkingTests.test_matching_phone_links_appointment_patient_to_user` with local Docker PostgreSQL, after fix | Passed. |
| `python manage.py test apps.booking.tests.AppointmentOperationServiceTests.test_staff_can_cancel_confirmed_appointment` with local Docker PostgreSQL, after fix | Passed. |

## Local SQLite and LocMem Result

Default local validation used `config.settings.dev`, SQLite, and LocMemCache.

| Command | Result |
| --- | --- |
| `python --version` | `Python 3.14.2` |
| `python manage.py check` | Exit 0; no issues. |
| `python manage.py makemigrations --check --dry-run` | Exit 0; no changes detected. |
| `python manage.py migrate --check` | Exit 0. |
| `python manage.py test apps.booking` | 130 tests ran, OK. |
| `python manage.py test apps.patients` | 46 tests ran, OK. |
| `python manage.py test` | 246 tests ran, OK. |
| `python manage.py deployment_smoke` | Exit 0; `WARNING`, 16 pass, 4 expected local warnings. |
| `python manage.py deployment_smoke --json` | Exit 0; JSON `database_engine=sqlite`, `cache_backend=locmem`, 16 pass, 4 warnings. |
| `python manage.py deployment_smoke --strict` | Exit 0 under dev settings; warning-only result. |

## PostgreSQL Result

PostgreSQL validation used the documented local Docker service with
`config.settings.dev`, PostgreSQL, and LocMemCache.

| Command | Result |
| --- | --- |
| `python manage.py check` | Exit 0. |
| `python manage.py makemigrations --check --dry-run` | Exit 0; no changes detected. |
| `python manage.py migrate` | Exit 0; no migrations to apply. |
| `python manage.py migrate --check` | Exit 0. |
| `python manage.py test apps.booking` | 130 tests ran, OK. |
| `python manage.py test apps.patients` | 46 tests ran, OK. |
| `python manage.py test` | 246 tests ran, OK. |
| `python manage.py deployment_smoke` | Exit 0; `database=postgresql`, `cache=locmem`, 16 pass, 3 expected local warnings. |
| `python manage.py deployment_smoke --json` | Exit 0; safe JSON showed PostgreSQL and LocMem. |
| `python manage.py deployment_smoke --strict` | Exit 0 under dev settings; warning-only result. |
| `python manage.py production_settings_report` | Exit 0; safe report showed `database=postgresql`, `cache=locmem`. |
| `python manage.py production_settings_report --json` | Exit 0; safe JSON only. |
| `python manage.py project_status_report` | Exit 0; 0 patients and 0 appointments. |
| `python manage.py project_status_report --json` | Exit 0; safe JSON only. |

PostgreSQL conclusion: the Batch 14B nullable outer-join `select_for_update()`
blocker is fixed for the local Docker validation path.

## Redis Result

Redis validation used `config.settings.dev`, SQLite, and the documented local
Docker Redis cache URL.

| Command | Result |
| --- | --- |
| `python -c "import redis; print(redis.__version__)"` | `5.3.1` |
| `python manage.py check` | Exit 0. |
| `python manage.py test apps.booking` | 130 tests ran, OK. |
| `python manage.py test apps.patients` | 46 tests ran, OK. |
| `python manage.py test` | 246 tests ran, OK. |
| `python manage.py deployment_smoke` | Exit 0; `database=sqlite`, `cache=redis`, 16 pass, 3 expected local warnings. |
| `python manage.py deployment_smoke --json` | Exit 0; safe JSON showed Redis. |
| `python manage.py deployment_smoke --strict` | Exit 0 under dev settings; warning-only result. |

Redis conclusion: Redis-backed local app suites and the full suite pass with the
documented cache override. Multi-process shared quota behavior and Redis outage
behavior remain untested.

## Combined PostgreSQL and Redis Result

Combined validation used `config.settings.dev`, local Docker PostgreSQL, and
local Docker Redis.

| Command | Result |
| --- | --- |
| `python manage.py check` | Exit 0. |
| `python manage.py test apps.booking` | 130 tests ran, OK. |
| `python manage.py test apps.patients` | 46 tests ran, OK. |
| `python manage.py test` | 246 tests ran, OK. |
| `python manage.py deployment_smoke` | Exit 0; `database=postgresql`, `cache=redis`, 16 pass, 2 expected local warnings. |
| `python manage.py deployment_smoke --json` | Exit 0; safe JSON showed PostgreSQL and Redis. |
| `python manage.py deployment_smoke --strict` | Exit 0 under dev settings; warning-only result. |
| `python manage.py production_settings_report` | Exit 0; safe report showed `database=postgresql`, `cache=redis`. |
| `python manage.py production_settings_report --json` | Exit 0; safe JSON only. |
| `python manage.py project_status_report` | Exit 0; 0 patients and 0 appointments. |
| `python manage.py project_status_report --json` | Exit 0; safe JSON only. |

Combined conclusion: local Docker PostgreSQL+Redis validation now passes for
the current bounded test/smoke/report scope.

## Cleanup Result

| Command | Result |
| --- | --- |
| `docker compose -f docker-compose.staging-validation.yml down` | Exit 0; stopped and removed the local validation containers and compose network. |
| `docker compose -f docker-compose.staging-validation.yml ps` | No services listed. |

Docker Desktop, WSL2, images, volumes, and unrelated Docker resources were not
removed.

## Remaining Blockers

Still blocked or incomplete:

- Real restricted staging infrastructure has not been provided or validated.
- Real HTTPS/reverse proxy/exact host/CSRF-origin/browser secure-cookie
  validation remains missing.
- Real staging PostgreSQL and Redis/shared-cache services have not been
  validated under `config.settings.prod`.
- PostgreSQL load/concurrency validation remains unrun.
- Redis multi-process shared quota behavior remains unproven.
- Redis outage behavior remains undecided and untested.
- No PostgreSQL backup/restore drill evidence exists.
- No monitoring/alerting setup evidence exists.
- No formal legal/privacy approval is recorded.
- No load/concurrency test evidence exists.

## Explicit No-Feature Statement

Batch 14B-FIX-01 did not add product features, dashboard implementation,
visual design, Figma work, WhatsApp integration, uploads, medical records,
payments, deployment, or external infrastructure.

## Explicit No-Real-Patient-Data Statement

All validation used local synthetic test data and safe seed/report behavior.
No real patient names, phone numbers, emails, appointments, medical records,
reports, media, WhatsApp messages, payment data, secrets, credentials, or real
external infrastructure were used or committed.
