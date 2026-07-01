# PostgreSQL and Redis Validation Evidence

## Summary

Batch 14 could not complete real PostgreSQL or Redis/shared-cache validation.
The repository contains a documented local-only Docker harness, but Docker was
not available in this environment. No real restricted staging database or cache
service was provided.

This document records the exact local evidence gathered and the remaining
blockers.

## PostgreSQL Result

Status: blocked for real staging and blocked for local service-backed
validation.

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

## Redis Result

Status: blocked for real staging and blocked for local service-backed
validation.

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

## Service Availability Checks

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

Because Docker was unavailable, these services were not started.

## Commands Run

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

The local test suite passed:

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

Limit: these tests ran on SQLite/LocMem, not PostgreSQL/Redis. They are useful
regression evidence but not production-like database/cache proof.

## Blockers

Current blockers:

- Real restricted staging infrastructure not provided/validated.
- Docker unavailable, so local PostgreSQL/Redis harness could not run.
- `psql` unavailable.
- `redis-cli` unavailable.
- Required staging environment variables absent.
- No staging PostgreSQL credentials or service endpoint provided.
- No staging Redis/shared-cache credentials or service endpoint provided.

## Required Future Evidence

Before PostgreSQL and Redis readiness can be claimed, a future Batch 14B or
equivalent must run against real restricted staging or an approved local service
harness:

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
