# Local Docker PostgreSQL and Redis Validation Evidence

## Evidence Classification

This document records Batch 14B local Docker PostgreSQL/Redis validation and
the Batch 14B-FIX-01 local Docker PostgreSQL/Redis rerun.

Correct label:

```text
local Docker PostgreSQL/Redis validation
```

Incorrect labels:

- real restricted staging validation;
- production readiness;
- launch readiness;
- HTTPS/proxy/CSRF-origin validation.

## Docker and WSL Environment Summary

- Docker CLI: `Docker version 29.6.1, build 8900f1d`
- Docker Compose: `Docker Compose version v5.1.4`
- Docker context: `desktop-linux`
- Docker daemon: running
- Docker server: `Docker Desktop`
- Kernel: `6.18.33.2-microsoft-standard-WSL2`
- Operating system from Docker server: `Docker Desktop`
- CPU count reported by Docker: 28
- Memory reported by Docker: 7.667 GiB

## Harness Used

Repository-approved harness:

- `docs/LOCAL_STAGING_SIMULATION.md`
- `docker-compose.staging-validation.yml`

Services:

- PostgreSQL: `postgres:16-alpine`
- Redis: `redis:7-alpine`

Local-only bindings:

- PostgreSQL on localhost port `54329`
- Redis on localhost port `63790`

The harness is service-only. It does not define a Django app container, reverse
proxy, TLS certificate, DNS, public hosting, or production deployment.

## Batch 14B-FIX-01 Corrected Rerun

Batch 14B-FIX-01 fixed the PostgreSQL nullable outer-join
`select_for_update()` blocker and reran the local Docker service-backed
validation path on 2026-07-02.

Root cause fixed:

- `apps.booking.operations.get_staff_appointment` used
  `select_for_update()` after `select_related("doctor", "patient", "visit_type")`.
- `apps.patients.services.link_appointment_to_user` used
  `select_for_update()` with `select_related("patient", "doctor", "visit_type")`.
- `Appointment.visit_type` is nullable, so PostgreSQL rejected the plain
  `FOR UPDATE` query shape because it included the nullable side of an outer
  join.

Corrected lock behavior:

- staff appointment operations now lock only the base appointment row with
  `select_for_update(of=("self",))`;
- patient portal appointment linking now locks the appointment and non-null
  patient rows with `select_for_update(of=("self", "patient"))`;
- nullable `visit_type` data can still be selected, but it is not included in
  the PostgreSQL lock target.

Batch 14B-FIX-01 local Docker results:

| Validation shape | Result |
| --- | --- |
| Default local SQLite/LocMem | Passed: `apps.booking`, `apps.patients`, full 246-test suite, and smoke commands. |
| Local Docker PostgreSQL + LocMem | Passed: check, migration checks, migration command, `apps.booking`, `apps.patients`, full 246-test suite, smoke commands, settings report, and project status report. |
| SQLite + local Docker Redis | Passed: Redis import `5.3.1`, check, `apps.booking`, `apps.patients`, full 246-test suite, and smoke commands. |
| Local Docker PostgreSQL + Redis | Passed: check, `apps.booking`, `apps.patients`, full 246-test suite, smoke commands, settings report, and project status report. |

Corrected conclusion:

- local Docker PostgreSQL-backed tests now pass;
- local Docker Redis-backed tests now pass;
- combined local Docker PostgreSQL+Redis full-suite validation now passes;
- the Batch 14B historical failure below remains preserved as prior evidence;
- this remains local Docker validation only, not real restricted staging,
  HTTPS/proxy/CSRF-origin validation, production readiness, or launch evidence.

## Environment Shape Used

Default baseline:

- `DJANGO_SETTINGS_MODULE=config.settings.dev`
- Empty `DATABASE_URL`: SQLite local database.
- Empty `CACHE_URL`: LocMemCache.

PostgreSQL validation:

- `DJANGO_SETTINGS_MODULE=config.settings.dev`
- `DATABASE_URL` pointed to the documented local Docker PostgreSQL service.
- `CACHE_URL` unset, so cache stayed LocMem.
- `DJANGO_CACHE_KEY_PREFIX=kbc-local-staging-validation`

Redis validation:

- `DJANGO_SETTINGS_MODULE=config.settings.dev`
- `DATABASE_URL` unset, so database stayed SQLite.
- `CACHE_URL` pointed to the documented local Docker Redis service.
- `DJANGO_CACHE_KEY_PREFIX=kbc-local-staging-validation`

Combined validation:

- `DJANGO_SETTINGS_MODULE=config.settings.dev`
- `DATABASE_URL` pointed to the documented local Docker PostgreSQL service.
- `CACHE_URL` pointed to the documented local Docker Redis service.
- `DJANGO_CACHE_KEY_PREFIX=kbc-local-staging-validation`

The documented local placeholder service values were used. No real staging or
production values were used. No `.env` file was created or modified.

## Commands and Summarized Outputs

### Preflight

| Command | Summarized output |
| --- | --- |
| `git status --short --branch` | Clean `main` tracking `origin/main`. |
| `git fetch origin` | Exit 0. |
| `git checkout main` | Already on `main`; up to date. |
| `git pull --ff-only origin main` | Already up to date. |
| `git log -1 --oneline` | `edca384 BATCH-14: add restricted staging validation evidence (#20)` |
| `git rev-parse HEAD` | `edca384c4d5fcd5c0fcdcba304a2bf63c17cf56b` |
| `git branch --show-current` | `main` before branch creation. |
| `docker --version` | `Docker version 29.6.1, build 8900f1d` |
| `docker compose version` | `Docker Compose version v5.1.4` |
| `docker info` | Exit 0; Docker Desktop daemon running on WSL2. |

### Baseline Local Development

| Command | Summarized output |
| --- | --- |
| `python --version` | `Python 3.14.2` |
| `python manage.py check` | Exit 0; no issues. |
| `python manage.py makemigrations --check --dry-run` | Exit 0; no changes detected. |
| `python manage.py migrate --check` | Exit 0. |
| `python manage.py deployment_smoke` | Exit 0; `WARNING`, 16 pass, 4 warnings, 0 failures. |
| `python manage.py deployment_smoke --json` | Exit 0; JSON `database_engine=sqlite`, `cache_backend=locmem`, 16 pass, 4 warnings. |
| `python manage.py deployment_smoke --strict` | Exit 0 under dev settings; same warning-only result. |
| `python manage.py production_settings_report` | Exit 0; dev settings, SQLite, LocMem. |
| `python manage.py production_settings_report --json` | Exit 0; safe JSON only. |
| `python manage.py project_status_report` | Exit 0; 0 patients, 0 appointments. |
| `python manage.py project_status_report --json` | Exit 0; safe counts/booleans/categories only. |
| `python manage.py check --deploy` | Exit 0 with 6 expected local security warnings. |

### Docker Service Commands

| Command | Summarized output |
| --- | --- |
| `docker compose -f docker-compose.staging-validation.yml up -d` | Exit 0; pulled images, created local network/volumes, started PostgreSQL and Redis. |
| `docker compose -f docker-compose.staging-validation.yml ps` | Initial health starting. |
| `docker compose -f docker-compose.staging-validation.yml ps` after wait | PostgreSQL and Redis both healthy. |

### PostgreSQL Commands

| Command | Summarized output |
| --- | --- |
| `python manage.py check` with local PostgreSQL | Exit 0; no issues. |
| `python manage.py makemigrations --check --dry-run` with local PostgreSQL | Exit 0; no changes detected. |
| `python manage.py migrate` with local PostgreSQL | Exit 0; all migrations applied to local Docker PostgreSQL. |
| `python manage.py migrate --check` with local PostgreSQL | Exit 0. |
| `python manage.py seed_public_content` with local PostgreSQL | Exit 0; public content created only. |
| `python manage.py seed_booking_demo` with local PostgreSQL | Exit 0; settings/schedules created; 0 patients and 0 appointments. |
| `python manage.py deployment_smoke` with local PostgreSQL | Exit 0; `database=postgresql`, `cache=locmem`, 16 pass, 3 local warnings. |
| `python manage.py production_settings_report` with local PostgreSQL | Exit 0; safe report showed `database=postgresql`, `cache=locmem`. |
| `python manage.py project_status_report` with local PostgreSQL | Exit 0; 0 patients and 0 appointments. |
| `python manage.py test apps.booking` with local PostgreSQL | Exit 1; 130 tests ran, 24 errors. |
| `python manage.py test apps.patients` with local PostgreSQL | Exit 1; 46 tests ran, 7 errors. |
| `python manage.py test` with local PostgreSQL | Exit 1; 246 tests ran, 31 errors. |

PostgreSQL failure signature:

```text
FOR UPDATE cannot be applied to the nullable side of an outer join
```

PostgreSQL evidence conclusion:

- Connection, migration, and smoke readiness against local Docker PostgreSQL
  are proven.
- Booking/staff/patient portal tests do not pass under PostgreSQL.
- PostgreSQL readiness remains blocked.

### Redis Commands

| Command | Summarized output |
| --- | --- |
| `python manage.py check` with local Redis | Exit 0; no issues. |
| `python manage.py deployment_smoke` with local Redis before dependency install | Exit 1; default cache check failed with `ModuleNotFoundError`. |
| `python -c "import redis; print(redis.__version__)"` before install | Exit 1; `ModuleNotFoundError`. |
| `python -m pip install -r requirements.txt` | Exit 0; installed already-declared `redis 5.3.1` locally. |
| `python -c "import redis; print(redis.__version__)"` after install | Exit 0; `5.3.1`. |
| `python manage.py deployment_smoke` with local Redis after install | Exit 0; `cache=redis`, cache set/get/delete passed, 16 pass, 3 local warnings. |
| `python manage.py deployment_smoke --json` with local Redis | Exit 0; safe JSON showed `cache_backend=redis`. |
| `python manage.py production_settings_report` with local Redis | Exit 0; safe report showed `database=sqlite`, `cache=redis`. |
| `python manage.py production_settings_report --json` with local Redis | Exit 0; safe JSON only. |
| `python manage.py project_status_report` with local Redis | Exit 0; 0 patients and 0 appointments. |
| `python manage.py test apps.booking` with local Redis | Exit 0; 130 tests ran, OK. |
| `python manage.py test apps.patients` with local Redis | Exit 0; 46 tests ran, OK. |
| `python manage.py test` with local Redis | Exit 1; 246 tests ran, 1 failure. |

The full Redis-enabled suite failure was an environment-default assertion:

```text
LocalSettingsDefaultTests expected LocMemCache, but CACHE_URL intentionally enabled Redis.
```

Redis evidence conclusion:

- Redis cache connectivity passed through Django after installing the existing
  repository-declared dependency locally.
- Booking and patient portal tests passed with Redis enabled.
- Existing cache-key privacy tests ran through those app test suites.
- Full-suite Redis validation is not clean because one core test intentionally
  asserts local default LocMem behavior.
- Multi-process shared quota behavior and Redis outage behavior remain
  unproven.

### Combined PostgreSQL and Redis Commands

| Command | Summarized output |
| --- | --- |
| `python manage.py check` with PostgreSQL+Redis | Exit 0; no issues. |
| `python manage.py makemigrations --check --dry-run` with PostgreSQL+Redis | Exit 0; no changes detected. |
| `python manage.py migrate --check` with PostgreSQL+Redis | Exit 0. |
| `python manage.py deployment_smoke` with PostgreSQL+Redis | Exit 0; `database=postgresql`, `cache=redis`, 16 pass, 2 local warnings. |
| `python manage.py deployment_smoke --json` with PostgreSQL+Redis | Exit 0; safe JSON showed PostgreSQL and Redis categories. |
| `python manage.py deployment_smoke --strict` with PostgreSQL+Redis | Exit 0 under dev settings; 16 pass, 2 warnings, 0 strict blockers. |
| `python manage.py production_settings_report` with PostgreSQL+Redis | Exit 0; safe report showed `database=postgresql`, `cache=redis`, `production_like=False`. |
| `python manage.py production_settings_report --json` with PostgreSQL+Redis | Exit 0; safe JSON only. |
| `python manage.py project_status_report --json` with PostgreSQL+Redis | Exit 0; 0 patients and 0 appointments. |
| `python manage.py check --deploy` with PostgreSQL+Redis | Exit 0 with 6 expected local-development Django security warnings. |
| `python manage.py test` with PostgreSQL+Redis | Exit 1; 246 tests ran, 31 errors and 1 failure. |

Combined evidence conclusion:

- Django can reach local Docker PostgreSQL and Redis together.
- Combined smoke/report commands pass with local-development warnings.
- Combined full test suite fails and cannot support readiness claims.

## What Cannot Be Claimed

Batch 14B cannot claim:

- PostgreSQL readiness;
- Redis/shared-cache production readiness;
- combined PostgreSQL+Redis full-suite readiness;
- real restricted staging readiness;
- production launch readiness;
- HTTPS/proxy/CSRF-origin readiness;
- browser secure-cookie behavior;
- multi-process rate-limit correctness;
- Redis outage behavior;
- backup/restore readiness;
- monitoring readiness;
- legal/privacy approval;
- load/concurrency readiness.

## Cleanup

| Command | Summarized output |
| --- | --- |
| `docker compose -f docker-compose.staging-validation.yml down` | Exit 0; stopped and removed the local validation containers and network. |
| `docker compose -f docker-compose.staging-validation.yml ps` | No services listed. |

No Docker Desktop, WSL2, image, or unrelated Docker resource removal was
performed.

## Evidence Summary

Pass:

- Docker Desktop and WSL2 are available.
- Repository-approved local service harness exists and starts.
- PostgreSQL service is reachable for checks, migrations, smoke, and safe
  reports.
- Redis service is reachable for Django cache set/get/delete after installing
  existing declared requirements locally.
- Booking and patient portal tests pass with Redis enabled on SQLite.
- Combined PostgreSQL+Redis smoke/report commands pass under dev settings.

Warning:

- All service-backed validation used `config.settings.dev`, not real staging or
  production settings.
- `check --deploy` still reports local HTTPS/security-cookie/HSTS/debug
  warnings.
- Full Redis-enabled suite fails one test that asserts LocMem local defaults.
- Multi-process shared Redis quotas remain unproven.

Fail:

- PostgreSQL-backed booking tests fail.
- PostgreSQL-backed patient portal tests fail.
- PostgreSQL-backed full suite fails.
- Combined PostgreSQL+Redis full suite fails.

Batch 14B historical blocker:

- PostgreSQL rejected the Batch 14B `select_for_update()` query shape involving
  nullable outer joins. This prior blocker was fixed and rerun in
  Batch 14B-FIX-01.

## Batch 14B-FIX-01 Evidence Summary

Pass:

- The local Docker PostgreSQL nullable outer-join locking blocker is fixed.
- PostgreSQL-backed `apps.booking` passed: 130 tests, OK.
- PostgreSQL-backed `apps.patients` passed: 46 tests, OK.
- PostgreSQL-backed full suite passed: 246 tests, OK.
- Redis-backed `apps.booking` passed: 130 tests, OK.
- Redis-backed `apps.patients` passed: 46 tests, OK.
- Redis-backed full suite passed: 246 tests, OK.
- Combined PostgreSQL+Redis `apps.booking` passed: 130 tests, OK.
- Combined PostgreSQL+Redis `apps.patients` passed: 46 tests, OK.
- Combined PostgreSQL+Redis full suite passed: 246 tests, OK.
- Combined PostgreSQL+Redis smoke/report commands passed under dev settings
  with expected local-development warnings only.
- Cleanup stopped and removed the local validation containers and compose
  network; no services remained listed afterward.

Warning:

- All service-backed validation still used `config.settings.dev`, not real
  staging or production settings.
- Local smoke under combined PostgreSQL+Redis still reports expected local
  warnings for `DEBUG=True` and HTTPS redirect disabled.
- Redis multi-process shared quota behavior remains unproven.
- Redis outage behavior remains untested.
- Real restricted staging, HTTPS/proxy/CSRF-origin, backup/restore,
  monitoring, legal/privacy, and load/concurrency validation remain blocked.

Fail:

- No Batch 14B-FIX-01 local Docker PostgreSQL, Redis, or combined full-suite
  failures remain for the current bounded test/smoke/report scope.

Blocker:

- Real restricted staging validation remains blocked because no real restricted
  staging host, HTTPS/proxy path, production-like environment, staging
  PostgreSQL service, or staging Redis/shared-cache service has been provided.
