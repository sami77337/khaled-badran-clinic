# PostgreSQL and Redis Validation Evidence

## Summary

Batch 14 could not complete real PostgreSQL or Redis/shared-cache validation
because Docker and real restricted staging services were unavailable.

Batch 14B used the repository-approved local-only Docker service harness after
Docker Desktop and WSL2 became available locally. This improved the evidence,
but it did not prove real restricted staging readiness.

Batch 14B result:

- local Docker PostgreSQL service started and accepted migrations;
- local Docker Redis service started and passed Django cache set/get/delete
  after installing the already-declared Redis dependency locally;
- Redis-backed booking and patient portal app tests passed on SQLite;
- PostgreSQL-backed booking, patient portal, and full-suite tests failed;
- combined PostgreSQL+Redis smoke/report commands passed under dev settings;
- combined PostgreSQL+Redis full-suite tests failed.

Correct Batch 14B classification:

```text
local Docker PostgreSQL/Redis validation
```

Do not classify Batch 14B as real restricted staging validation.

## Batch 14B Local Docker PostgreSQL Result

Status: failed for local Docker PostgreSQL validation.

Harness:

- `docker-compose.staging-validation.yml`
- `docs/LOCAL_STAGING_SIMULATION.md`
- PostgreSQL `postgres:16-alpine`
- localhost-only service binding on port `54329`

Passed:

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py migrate`
- `python manage.py migrate --check`
- `python manage.py seed_public_content`
- `python manage.py seed_booking_demo`
- `python manage.py deployment_smoke`
- `python manage.py production_settings_report`
- `python manage.py project_status_report`

The PostgreSQL local validation database reported 0 patients and 0
appointments after the documented synthetic seed commands.

Failed:

- `python manage.py test apps.booking`: 130 tests ran, 24 errors.
- `python manage.py test apps.patients`: 46 tests ran, 7 errors.
- `python manage.py test`: 246 tests ran, 31 errors.

Failure signature:

```text
FOR UPDATE cannot be applied to the nullable side of an outer join
```

Observed affected areas:

- Staff appointment operations using `select_for_update()` on a queryset that
  also selects related nullable appointment data.
- Patient portal appointment linking using `select_for_update()` with related
  appointment data.

Conclusion:

- PostgreSQL connectivity and migrations are locally proven.
- Booking/staff/patient portal behavior is not PostgreSQL-ready.
- PostgreSQL readiness remains blocked until a code-fix batch addresses the
  nullable outer-join `select_for_update()` issue and reruns local Docker
  PostgreSQL validation.

## Batch 14B Local Docker Redis Result

Status: partial pass for Redis/shared-cache rehearsal.

Harness:

- `docker-compose.staging-validation.yml`
- `docs/LOCAL_STAGING_SIMULATION.md`
- Redis `redis:7-alpine`
- localhost-only service binding on port `63790`

Initial blocker and resolution:

- The active local Python environment was missing the repository-declared
  `redis` package.
- `python manage.py deployment_smoke` with Redis initially failed with
  `ModuleNotFoundError`.
- `python -c "import redis; print(redis.__version__)"` initially failed with
  `ModuleNotFoundError`.
- `requirements.txt` already declared `redis>=5.0,<6.0`.
- `python -m pip install -r requirements.txt` installed the existing declared
  dependency locally.
- The import check then reported `5.3.1`.
- No dependency files were changed.

Passed after installing existing requirements locally:

- `python manage.py deployment_smoke`: cache set/get/delete passed with
  `cache=redis`.
- `python manage.py deployment_smoke --json`: safe JSON showed
  `cache_backend=redis`.
- `python manage.py production_settings_report` and `--json`: safe reports
  showed `cache=redis`.
- `python manage.py test apps.booking`: 130 tests ran, OK.
- `python manage.py test apps.patients`: 46 tests ran, OK.

Full-suite limitation:

- `python manage.py test` with Redis and SQLite ran 246 tests and failed with 1
  failure.
- The failing test was an environment-default assertion that local settings use
  LocMemCache. That assertion is expected to fail when `CACHE_URL` is
  intentionally set for Redis validation.

Conclusion:

- Django can reach local Docker Redis for cache operations.
- Booking and patient portal Redis-backed app tests pass.
- Existing tests cover hashed cache-key behavior for booking and portal
  rate-limit identities where implemented.
- Multi-process shared quota behavior remains unproven.
- Redis outage behavior remains untested because no existing documented safe
  outage test was provided.

## Batch 14B Combined PostgreSQL and Redis Result

Status: failed.

Passed with local Docker PostgreSQL and Redis together:

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py migrate --check`
- `python manage.py deployment_smoke`
- `python manage.py deployment_smoke --json`
- `python manage.py deployment_smoke --strict`
- `python manage.py production_settings_report`
- `python manage.py production_settings_report --json`
- `python manage.py project_status_report --json`
- `python manage.py check --deploy`

Combined smoke/report result:

- safe reports showed `database=postgresql` and `cache=redis`;
- `deployment_smoke` reported 16 pass, 2 expected local-development warnings,
  0 failures, and 0 strict blockers;
- `check --deploy` still reported 6 expected local HTTPS/security-cookie/HSTS
  and debug warnings.

Failed:

- `python manage.py test`: 246 tests ran, 31 PostgreSQL errors and 1 Redis
  environment-default failure.

Conclusion:

- Combined local Docker service connectivity is proven.
- Combined full-suite validation failed.
- The PostgreSQL blocker must be fixed before combined local Docker
  PostgreSQL/Redis validation can pass.

## Batch 14 PostgreSQL Result

Status: blocked for real staging and blocked for local service-backed
validation at the time Batch 14 ran.

Validated locally without PostgreSQL:

- `python manage.py makemigrations --check --dry-run`: exit 0; no model drift.
- `python manage.py migrate --check`: exit 0; no unapplied migrations reported
  in the local SQLite environment.
- `python manage.py check`: exit 0.
- `python manage.py test apps.booking`: 130 tests ran, OK.
- `python manage.py test apps.patients`: 46 tests ran, OK.
- `python manage.py test`: 246 tests ran, OK.
- Existing booking tests include local model constraint and collision behavior
  coverage where feasible.
- Synthetic production-settings `python manage.py check` rejected SQLite with
  `clinic.E006`.

Not validated:

- PostgreSQL connection through `DATABASE_URL`.
- Migration apply/check against PostgreSQL.
- PostgreSQL-specific constraint behavior.
- PostgreSQL transaction/isolation behavior.
- Concurrent duplicate public booking attempts against PostgreSQL.
- Staff reschedule collision behavior against PostgreSQL.
- Database SSL mode.
- Least-privilege staging database user.
- PostgreSQL backup/restore.
- Provider connection pooling or health checks.

## Batch 14 Redis Result

Status: blocked for real staging and blocked for local service-backed
validation at the time Batch 14 ran.

Validated locally without Redis:

- `python manage.py deployment_smoke`: local LocMemCache set/get/delete passed.
- Existing booking and patient portal tests passed under local cache settings.
- Existing tests cover hashed identity behavior for booking and portal
  rate-limit cache keys where implemented.
- Synthetic production-settings `python manage.py check` rejected LocMemCache
  with `clinic.E005`.

Not validated:

- Redis connection through `CACHE_URL`.
- Shared rate-limit counters across processes.
- Redis expiration behavior.
- Redis key-prefix isolation.
- Redis authentication/TLS provider configuration.
- Redis outage behavior.
- Production rate-limit tuning.
- Cache monitoring and alerting.

## Batch 14 Service Availability Checks

| Command | Result |
| --- | --- |
| `docker --version` | Failed; `docker` was not recognized in PATH. |
| `docker compose version` | Failed; `docker` was not recognized in PATH. |
| `psql --version` | Failed; `psql` was not recognized in PATH. |
| `redis-cli --version` | Failed; `redis-cli` was not recognized in PATH. |

## Documented Harness Inspected

The following repository files were inspected:

- `docs/LOCAL_STAGING_SIMULATION.md`
- `docker-compose.staging-validation.yml`
- `scripts/validate_local_release.ps1`
- `scripts/validate_staging_env.ps1`
- `scripts/validate_local_release.sh`
- `scripts/validate_staging_env.sh`
- `config/settings/base.py`
- `config/settings/dev.py`
- `config/settings/prod.py`
- `config/settings/helpers.py`

The compose harness is service-only and binds to localhost:

- PostgreSQL expected local port: `127.0.0.1:54329`
- Redis expected local port: `127.0.0.1:63790`

Because Docker was unavailable in Batch 14, these services were not started in
that batch. Batch 14B later started the same harness successfully.

## Batch 14 Commands Run

PostgreSQL-adjacent local validation:

| Command | Result |
| --- | --- |
| `python manage.py makemigrations --check --dry-run` | Exit 0; no changes detected. |
| `python manage.py migrate --check` | Exit 0. |
| `python manage.py check` | Exit 0; no issues. |
| `python manage.py test apps.booking` | 130 tests ran, OK. |
| `python manage.py test apps.patients` | 46 tests ran, OK. |
| `python manage.py test` | 246 tests ran, OK. |

Redis-adjacent local validation:

| Command | Result |
| --- | --- |
| `python manage.py deployment_smoke` | Exit 0; cache set/get/delete passed using LocMemCache; local warning recorded. |
| `python manage.py deployment_smoke --json` | Exit 0; cache backend category `locmem`; local warning recorded. |
| `python manage.py test apps.booking` | 130 tests ran, OK. |
| `python manage.py test apps.patients` | 46 tests ran, OK. |

Production-settings negative validation:

| Command | Result |
| --- | --- |
| Synthetic local `config.settings.prod` environment, then `python manage.py production_settings_report` | Exit 1; production checks rejected LocMemCache and SQLite before report output. |
| Synthetic local `config.settings.prod` environment, then `python manage.py check` | Exit 1; `clinic.E005` LocMemCache and `clinic.E006` SQLite. |

Strict staging environment validation:

| Command | Result |
| --- | --- |
| `powershell -ExecutionPolicy Bypass -File scripts/validate_staging_env.ps1 -Strict -Json` | Exit 1; required staging variables missing; no values printed. |

## Test Results Relevant to PostgreSQL and Redis

Batch 14 local SQLite/LocMem test suite passed:

- `apps.booking`: 130 tests.
- `apps.patients`: 46 tests.
- Full suite: 246 tests.

Relevant coverage includes:

- appointment model constraint declarations;
- exact duplicate slot protection in local test database behavior;
- public booking final confirmation behavior;
- staff reschedule validation and collision handling;
- staff operation authorization;
- UUID public success behavior;
- no-cache booking success and portal pages;
- hashed booking and portal rate-limit identities;
- prohibited upload, records, WhatsApp, payment, and automation routes absent.

Limit: those Batch 14 tests ran on SQLite/LocMem, not PostgreSQL/Redis. They
remain useful regression evidence but not production-like database/cache proof.

Batch 14B updated the service-backed status:

- PostgreSQL service-backed tests do not pass.
- Redis-backed booking and patient portal app tests pass.
- Combined PostgreSQL+Redis full suite does not pass.

## Blockers

Current blockers after Batch 14B:

- Real restricted staging infrastructure not provided/validated.
- Local Docker PostgreSQL-backed booking, staff operation, and patient portal
  tests fail on the nullable outer-join `select_for_update()` issue.
- Combined local Docker PostgreSQL+Redis full suite fails.
- Full Redis-enabled suite has one environment-default assertion failure when
  `CACHE_URL` intentionally overrides local LocMem defaults.
- Required real staging environment variables remain absent.
- No real staging PostgreSQL credentials or service endpoint provided.
- No real staging Redis/shared-cache credentials or service endpoint provided.
- Real PostgreSQL concurrency behavior remains unproven until the PostgreSQL
  blocker is fixed and a reviewed concurrency validation runs.
- Redis multi-process shared quota behavior remains unproven.
- Redis outage behavior remains untested.

## Required Future Evidence

Before PostgreSQL and Redis readiness can be claimed, a future fix/evidence
batch must first pass the approved local service harness:

- fix the PostgreSQL nullable outer-join `select_for_update()` blocker;
- rerun PostgreSQL-backed booking, patient portal, and full-suite tests;
- rerun combined PostgreSQL+Redis smoke/report/full-suite checks;
- document whether the full Redis-enabled suite should exclude local-default
  setting assertions or use a dedicated service-backed test profile.

After local Docker validation passes, real restricted staging must still run:

- `python manage.py makemigrations --check --dry-run`
- `python manage.py migrate --check`
- `python manage.py migrate` against a fresh synthetic PostgreSQL database when
  permitted by the staging plan
- `python manage.py check`
- `python manage.py check --deploy`
- `python manage.py deployment_smoke --strict`
- `python manage.py deployment_smoke --json`
- `python manage.py production_settings_report`
- `python manage.py production_settings_report --json`
- `python manage.py test apps.booking`
- `python manage.py test apps.patients`
- `python manage.py test` when the database is disposable or isolated
- documented duplicate booking and staff reschedule collision checks on
  PostgreSQL
- documented shared Redis rate-limit checks across processes
- Redis outage behavior decision and safe test, if approved

Use synthetic data only. Do not use production services or real patient data.
