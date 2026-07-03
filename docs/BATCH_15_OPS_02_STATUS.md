# Batch 15 OPS 02 Status - Synthetic Restore Drill Evidence

## Scope

BATCH-15-OPS-02 executed and documented a non-destructive synthetic
backup/restore drill in an isolated local environment only.

This batch did not change application features, routes, models, migrations,
templates, settings, dependencies, Render settings, monitoring accounts, alert
routes, dashboards, uploads, medical records, payments, WhatsApp behavior, or
medical automation.

Production-ready status:

```text
no
```

## Branch and Base

- Working branch:
  `codex/batch-15-ops-02-synthetic-restore-drill`
- Base branch: `main`
- Verified base commit:
  `a367d017354aedff1434998025c0fb44efb088b1`
- Base subject:
  `Merge PR #26: add backup and monitoring readiness plans`
- Repository remote:
  `sami77337/khaled-badran-clinic`
- Drill date:
  `2026-07-03`

The preserved local branch `feat/security-operations-release-evidence` was not
checked out, modified, rebased, merged, deleted, pushed, or used.

## Documentation Inspected

This batch read the required operations, release, staging, PostgreSQL, Redis,
and Render documents before running the drill:

- `docs/BATCH_15_OPS_01_STATUS.md`
- `docs/OPERATIONS_BACKUP_RESTORE_PLAN.md`
- `docs/OPERATIONS_MONITORING_ALERTING_PLAN.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/POSTGRESQL_READINESS.md`
- `docs/POSTGRESQL_REDIS_VALIDATION_EVIDENCE.md`
- `docs/LOCAL_DOCKER_POSTGRES_REDIS_VALIDATION_EVIDENCE.md`
- `docs/RENDER_STAGING_SETUP.md`
- `docs/STAGING_ENVIRONMENT_CONTRACT.md`

Related local runbooks and tooling were also inspected:

- `docs/LOCAL_STAGING_SIMULATION.md`
- `docs/BACKUP_RESTORE_RUNBOOK.md`
- `docs/BACKUP_RESTORE_DRILL.md`
- `docker-compose.staging-validation.yml`
- `apps/clinic/management/commands/seed_public_content.py`
- `apps/booking/management/commands/seed_booking_demo.py`

## Repository State Commands

| Command | Result |
| --- | --- |
| `git fetch origin main` | Exit 0. |
| `git status --short --branch` before branching | Clean `main` tracking `origin/main`. |
| `git rev-parse HEAD` before branching | `a367d017354aedff1434998025c0fb44efb088b1`. |
| `git rev-parse origin/main` | `a367d017354aedff1434998025c0fb44efb088b1`. |
| `git merge-base --is-ancestor a367d01 origin/main` | Exit 0; `origin/main` contains `a367d01`. |
| `git branch --list feat/security-operations-release-evidence` | Branch exists locally and was left untouched. |
| `git switch -c codex/batch-15-ops-02-synthetic-restore-drill origin/main` | Exit 0. |
| `gh --version` | Exit 0; GitHub CLI available. |
| `gh auth status` | Exit 0; authenticated for repository operations. |

## Safe Local Baseline Commands

These commands ran locally with staging database/cache connection values absent
from the process environment:

| Command | Result |
| --- | --- |
| `python manage.py check` | Exit 0; no system check issues. |
| `python manage.py test` | Exit 0; 246 tests ran, OK. |
| `python manage.py deployment_smoke` | Exit 0; warning-only local result: 16 pass, 4 expected local warnings, 0 failures, 0 strict blockers. |
| `python manage.py production_settings_report` | Exit 0; safe local report only; development settings, SQLite, LocMemCache, and disabled local HTTPS/security flags were reported without sensitive values. |
| `python manage.py project_status_report` | Exit 0; safe counts and feature flags only; 0 patients and 0 appointments in the local report. |

The four local smoke warnings were expected for `config.settings.dev`:

- `DEBUG=True`;
- SQLite instead of PostgreSQL;
- LocMemCache instead of Redis/shared cache;
- HTTPS redirect disabled locally.

## Tooling Inspection

Available local drill tooling:

- Docker CLI and Docker Compose are installed.
- Docker Desktop was initially not running; it was started locally for this
  drill.
- Docker daemon then reported server version `29.6.1`.
- `docker-compose.staging-validation.yml` defines localhost-bound PostgreSQL
  and Redis services only.
- `docs/LOCAL_STAGING_SIMULATION.md` documents the local-only harness and
  confirms it is not launch evidence.
- `seed_public_content` creates public clinic, doctor, and visit type content
  only.
- `seed_booking_demo` creates booking settings and doctor schedules only.
- No repository management command exists for provider backup, export, import,
  or restore. The drill used PostgreSQL logical tooling inside the local Docker
  PostgreSQL container.

## Synthetic Restore Drill Result

Local synthetic restore drill:

```text
passed
```

The drill used only local Docker PostgreSQL and Redis. It did not connect to
Render, did not inspect staging contents, did not change staging or production
resources, and did not use real patient data.

Drill shape:

- started local Docker PostgreSQL and Redis via the repository compose harness;
- created one isolated local synthetic source database;
- created one separate isolated local restore-test database;
- applied migrations to the source database;
- ran `seed_public_content`;
- ran `seed_booking_demo`;
- confirmed source counts contained only public/demo setup data;
- created a custom-format PostgreSQL logical dump inside the local PostgreSQL
  container;
- restored that dump into the separate restore-test database;
- ran post-restore verification against the restored local database;
- removed the generated dump file;
- dropped the source and restore-test databases;
- stopped the local compose services.

Generated local dump artifact:

- location during the drill: local PostgreSQL container `/tmp`;
- observed size: `67.3K`;
- committed to Git: `no`;
- retained after cleanup: `no`.

## Source and Restored Counts

Safe source counts before dump:

| Category | Count |
| --- | ---: |
| clinic profiles | 1 |
| doctors | 1 |
| visit types | 9 |
| doctor schedules | 5 |
| system settings | 7 |
| patients | 0 |
| appointments | 0 |

Safe restored counts after restore:

| Category | Count |
| --- | ---: |
| clinic profiles | 1 |
| doctors | 1 |
| visit types | 9 |
| doctor schedules | 5 |
| system settings | 7 |
| patients | 0 |
| appointments | 0 |

The restored counts matched the source counts. No patient or appointment rows
were present.

## Restore Verification Commands

The restored database was verified with local development settings, local
PostgreSQL, and local Redis:

| Command | Result |
| --- | --- |
| `python manage.py makemigrations --check --dry-run` | Exit 0; no changes detected. |
| `python manage.py migrate --check` | Exit 0; no unapplied migrations. |
| `python manage.py check` | Exit 0; no system check issues. |
| `python manage.py check --deploy` | Exit 0 with 6 expected local-development deployment warnings. |
| `python manage.py deployment_smoke --strict` | Exit 0; database category PostgreSQL, cache category Redis, 16 pass, 2 expected local warnings, 0 failures, 0 strict blockers. |
| `python manage.py deployment_smoke --json` | Exit 0; safe JSON only, 16 pass, 2 warnings, 0 failures, 0 strict blockers. |
| `python manage.py production_settings_report` | Exit 0; safe report showed development settings with PostgreSQL and Redis categories. |
| `python manage.py production_settings_report --json` | Exit 0; safe JSON only. |
| `python manage.py project_status_report` | Exit 0; safe counts showed 0 patients and 0 appointments. |
| `python manage.py project_status_report --json` | Exit 0; safe JSON only. |
| `python manage.py test` | Exit 0; 246 tests ran, OK, using the disposable local restored PostgreSQL-backed test database. |

The two local warnings from `deployment_smoke --strict` were expected because
this drill intentionally used `config.settings.dev` rather than a real
production-like Render runtime:

- `DEBUG=True`;
- HTTPS redirect disabled locally.

## Cleanup

Cleanup commands completed successfully:

- removed the generated local dump artifact from the PostgreSQL container;
- dropped the isolated local source database;
- dropped the isolated local restore-test database;
- stopped and removed the local compose containers and network;
- did not remove Docker Desktop, Docker images, or unrelated Docker resources.

## Conclusions

Local synthetic restore drill:

```text
passed
```

Real Render managed PostgreSQL restore drill:

```text
incomplete
```

Real patient-data restore:

```text
not performed and not allowed
```

Backup retention, RPO, and RTO approval:

```text
blocked
```

Monitoring provider and alert routing:

```text
blocked
```

Legal/privacy approval:

```text
blocked
```

Production-ready:

```text
no
```

## Secret and Data Handling

No active Render staging resource was modified. No Render settings were
changed. No real staging database contents were accessed. No production
resource was accessed.

No real patient names, phone numbers, emails, appointment histories, medical
notes, reports, images, audio, video, WhatsApp messages, payment data, or
private files were created, dumped, restored, exposed, or committed.

No database/cache connection values, credentials, generated dumps, backup
files, operational logs, provider output, or key material were committed.

## Remaining Blockers

Production launch remains blocked by at least:

- real Render managed PostgreSQL restore drill not executed;
- backup retention, RPO, and RTO not approved;
- backup job monitoring not configured;
- monitoring provider not configured;
- alert routing not configured or tested;
- privacy-safe error reporting not configured;
- legal/privacy approval not recorded;
- load/concurrency validation not completed;
- direct managed PostgreSQL runtime evidence still incomplete;
- direct managed Redis/shared-cache runtime evidence still incomplete;
- Redis multi-process quota and outage behavior still incomplete;
- dependency vulnerability scan evidence and response ownership still
  incomplete;
- production hosting, DNS/custom domain/TLS, and production reverse proxy not
  configured by this repository.
