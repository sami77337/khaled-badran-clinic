# PostgreSQL Readiness

Batch 11 PostgreSQL readiness plan for Dr. Khaled Badran Clinic.

This document explains what must be validated before launch. It does not
provision PostgreSQL, create credentials, store database URLs, or run a real
staging database.

## Why SQLite Passing Is Not Sufficient

SQLite is useful for local development and fast CI checks, but it is not
production proof for this project.

SQLite does not prove:

- production PostgreSQL connection settings,
- provider SSL behavior,
- least-privilege database permissions,
- production migration behavior,
- concurrent transaction behavior under real isolation,
- conditional uniqueness behavior under production load,
- backup and restore operations,
- connection pooling limits,
- query behavior under production data volume.

Local SQLite tests can catch many application regressions. They cannot replace
restricted staging validation on PostgreSQL.

## Required PostgreSQL Staging Checks

Before launch, staging must prove:

- `DATABASE_URL` points to PostgreSQL.
- The app database exists.
- The app user is staging-only and least privilege.
- SSL requirements match the provider.
- `python manage.py migrate` completes.
- `python manage.py makemigrations --check --dry-run` reports no model drift.
- `python manage.py check` passes.
- `python manage.py check --deploy` is reviewed.
- `python manage.py deployment_smoke --strict` passes.
- `python manage.py production_settings_report` reports
  `database=postgresql` or JSON `database_backend=postgresql`.
- `python manage.py test` passes when using a disposable test database or an
  isolated CI clone.
- No real patient data is present.

## Migration Validation

Recommended staging sequence:

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py migrate
python manage.py check
python manage.py check --deploy
python manage.py deployment_smoke --strict
```

If `migrate --check` reports unapplied migrations, do not treat staging as
validated until migrations run successfully and smoke checks pass afterward.

Production migrations must be controlled deployment steps with a backup and
rollback plan.

## Appointment Slot Constraints

The `Appointment` model must preserve:

- `appointment_ends_after_start`
- `unique_appointment_doctor_start_status`
- `unique_active_appointment_doctor_start`

The active-slot uniqueness constraint applies to:

- `confirmed`
- `arrived`
- `rescheduled`

This protects exact duplicate active starts for the same doctor. Application
logic also rejects overlapping intervals, not only exact starts.

## Concurrent Public Booking Simulation Plan

Staging must simulate duplicate public booking attempts for the same doctor and
start time.

Plan:

1. Seed only synthetic public content and booking demo schedules.
2. Select one active visit type and one available future slot.
3. Submit two public booking confirmations for the same slot concurrently.
4. Confirm at most one active appointment exists for the doctor/start time.
5. Confirm the losing request receives a patient-safe unavailable-slot error.
6. Confirm no internal exception details, database errors, or stack traces are
   shown to patients.
7. Confirm public success remains UUID public-token based.

No real patient names, phone numbers, or emails may be used.

## Staff Reschedule Collision Plan

Staging must simulate staff reschedule collisions:

1. Create two synthetic active appointments for the same doctor on different
   future slots.
2. As staff, attempt to reschedule appointment A into appointment B's active
   slot.
3. Confirm the operation is rejected.
4. Confirm appointment A keeps its original `public_token`.
5. Confirm status history and audit logs remain staff-only.
6. Confirm terminal appointments cannot be silently restored or reused.

## Transaction and Isolation Concerns

Current code uses `transaction.atomic()` for public appointment creation and
staff appointment operations. PostgreSQL validation must still verify real
transaction behavior because race timing and constraint enforcement can differ
from SQLite.

Operators should watch for:

- late `IntegrityError` handling,
- duplicate active appointment rows,
- stale slot submissions,
- reschedule races,
- transaction rollback behavior after validation errors,
- database lock waits or deadlocks under repeated concurrent attempts.

Do not add custom isolation-level changes until a measured staging issue
requires it and the fix is reviewed.

## Backup and Restore Expectations

PostgreSQL readiness is incomplete until backup and restore are proven with
synthetic data.

Before launch:

- Take a staging backup.
- Restore into an isolated restore-test database.
- Point a staging clone or local validation shell at the restored database.
- Run migrations if needed.
- Run:
  - `python manage.py check`
  - `python manage.py check --deploy`
  - `python manage.py deployment_smoke --strict`
  - `python manage.py production_settings_report`
- Record restore duration, app revision, migration state, and validation
  result outside Git.

Do not store database dumps or restore logs containing secrets or patient data
in Git.

## Manual Staging Concurrency Commands

Use a future reviewed script, Django shell, or test harness against restricted
staging. Keep all data synthetic.

Useful safe starting commands:

```bash
python manage.py seed_public_content
python manage.py seed_booking_demo
python manage.py deployment_smoke --strict
python manage.py project_status_report --json
```

For concurrency tests, prefer an isolated staging test database or a disposable
staging clone. Do not run destructive or high-volume concurrency tests against
production.

## Local Docker Harness

If Docker is available, `docker-compose.staging-validation.yml` can provide
local PostgreSQL for rehearsal. See `docs/LOCAL_STAGING_SIMULATION.md`.

Passing the local harness does not replace real staging validation.

## Current Batch 11 Status

Batch 11 adds documentation and local regression coverage for model constraints
and collision logic where feasible.

PostgreSQL readiness remains partial until an actual PostgreSQL staging
validation cycle runs successfully.

Design status: No design work performed by Codex.
