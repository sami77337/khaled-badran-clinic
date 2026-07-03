# Batch 15 OPS 01 Status - Backup/Restore and Monitoring Readiness Plan

## Scope

BATCH-15-OPS-01 created production-oriented operations readiness plans for:

- PostgreSQL backup and restore;
- Redis/shared-cache recovery expectations;
- private media and upload backup boundaries;
- restore drills using synthetic data only;
- uptime checks;
- latency thresholds;
- error-rate monitoring;
- deploy, database, and cache alerting;
- privacy-safe error reporting;
- incident severity, response, and review.

This was a planning and documentation batch only. It did not change application
features, routes, models, migrations, templates, settings, dependencies,
Render service settings, monitoring accounts, backup provider settings, or
dashboard surfaces.

Production-ready status:

```text
no
```

## Branch and Base

- Working branch:
  `codex/batch-15-ops-01-backup-monitoring-readiness-plan`
- Base branch: `main`
- Verified base commit:
  `e9b5169d9d3a59f87069e4ab68e7127707022f7e`
- Base subject:
  `BATCH-14C-VALIDATE-02: deepen Render staging evidence (#25)`
- Repository remote:
  `sami77337/khaled-badran-clinic`
- Render staging URL:
  `https://khaled-badran-clinic-staging.onrender.com`
- Planning date:
  `2026-07-03`

The preserved local branch `feat/security-operations-release-evidence` was not
checked out, modified, rebased, merged, deleted, pushed, or used.

## Documentation Inspected

This batch read the required staging and release documents before editing:

- `docs/BATCH_14C_VALIDATE_01_STATUS.md`
- `docs/BATCH_14C_VALIDATE_02_STATUS.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/RENDER_STAGING_SETUP.md`
- `docs/STAGING_ENVIRONMENT_CONTRACT.md`
- `docs/RESTRICTED_STAGING_VALIDATION_EVIDENCE.md`
- `docs/POSTGRESQL_REDIS_VALIDATION_EVIDENCE.md`
- `docs/LOCAL_DOCKER_POSTGRES_REDIS_VALIDATION_EVIDENCE.md`

Related operations, security, and release documents were also inspected:

- `docs/BACKUP_RESTORE_RUNBOOK.md`
- `docs/BACKUP_RESTORE_DRILL.md`
- `docs/MONITORING_ALERTING_READINESS.md`
- `docs/INCIDENT_RESPONSE_RUNBOOK.md`
- `docs/PRODUCTION_READINESS.md`
- `docs/DEPLOYMENT_CHECKLIST.md`
- `docs/DEPENDENCY_SECURITY_READINESS.md`
- `docs/LEGAL_PRIVACY_OPERATIONS.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/LOAD_TEST_PLAN.md`
- `docs/SECURITY_REGRESSION_CHECKLIST.md`
- `docs/SECURITY_NOTES.md`
- `docs/SECURITY_HARDENING.md`
- `docs/POSTGRESQL_READINESS.md`
- `docs/REDIS_RATE_LIMIT_READINESS.md`
- `docs/STAGING_VALIDATION_PLAN.md`
- `docs/STAGING_GAP_ANALYSIS.md`
- `docs/STAFF_ACCESS_GOVERNANCE.md`

## Repository State Commands

| Command | Result |
| --- | --- |
| `git fetch origin main` | Exit 0. |
| `git status -sb` before branching | Clean `main` tracking `origin/main`. |
| `git rev-parse --abbrev-ref HEAD` before branching | `main` |
| `git rev-parse origin/main` | `e9b5169d9d3a59f87069e4ab68e7127707022f7e` |
| `git merge-base --is-ancestor e9b5169 origin/main` | Exit 0; `origin/main` contains `e9b5169`. |
| `git switch -c codex/batch-15-ops-01-backup-monitoring-readiness-plan origin/main` | Exit 0. |
| `gh --version` | Exit 0; GitHub CLI available. |
| `gh auth status` | Exit 0; authenticated for repository operations. |

## Safe Local Commands

These commands ran locally without production or staging secrets:

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

These are not acceptable production settings. No real Render secrets were
copied into the local workspace.

## Operational Capability Inventory

Existing management commands:

- `python manage.py deployment_smoke`
- `python manage.py deployment_smoke --json`
- `python manage.py deployment_smoke --strict`
- `python manage.py production_settings_report`
- `python manage.py production_settings_report --json`
- `python manage.py project_status_report`
- `python manage.py project_status_report --json`
- `python manage.py seed_public_content`
- `python manage.py seed_booking_demo`

No dedicated backup, export, import, restore, or provider-backup management
command exists in the repository. Backup and restore remain operator/provider
operations documented through runbooks and plans.

Existing health endpoints:

- `GET /health/` public liveness, no database check, no-cache, privacy-safe JSON.
- `GET /health/ready/` readiness, database connectivity check, no-cache,
  returns only `ok` or `unavailable`.

Existing observability foundations:

- console logging for Django, request errors, security events, and
  `apps.booking`;
- safe exception labels in `deployment_smoke`;
- safe output policies in smoke/status/settings report commands;
- no request-body logging configured by the repository;
- no third-party error-reporting SDK or DSN configured;
- no external uptime monitor or alert route configured.

Existing dependency/security tooling:

- GitHub Actions run Django checks, smoke reports, settings reports, and tests.
- Dependabot is configured for Python dependencies and GitHub Actions.
- No vulnerability scan evidence or approved response owner exists yet.

## Backup/Restore Plan Created

`docs/OPERATIONS_BACKUP_RESTORE_PLAN.md` now defines:

- backup scope and non-scope;
- PostgreSQL backup expectations;
- Redis/shared-cache recovery expectations;
- current media/private upload status;
- synthetic-only restore drill procedure;
- post-restore verification criteria;
- rollback and restore boundaries;
- owner checklist;
- frequency recommendations;
- retention/deletion considerations.

No backup was created and no restore was executed in this batch.

## Monitoring/Alerting Plan Created

`docs/OPERATIONS_MONITORING_ALERTING_PLAN.md` now defines:

- uptime checks for `/health/` and `/`;
- private readiness monitoring for `/health/ready/` where possible;
- latency thresholds, including the observed about 32.5 second `/health/`
  response;
- error-rate, deploy failure, database, cache, and backup alert expectations;
- privacy-safe error reporting requirements;
- alert routing and escalation placeholders;
- severity levels;
- incident response checklist;
- post-incident review checklist.

No monitoring provider, alert routing, or third-party error reporting service
was configured in this batch.

## Remaining Blockers

Production launch remains blocked by at least:

- real backup/restore drill not executed;
- backup retention, RPO, and RTO not approved;
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

## Secret and Data Handling

No booking POST was submitted. No patient, appointment, medical, upload,
payment, WhatsApp, or automation data was created. No real patient data was
used.

This document intentionally avoids secret values and connection strings. It may
mention forbidden labels such as `DATABASE_URL`, `CACHE_URL`, `SECRET_KEY`,
password, token, and private key only as categories or policy boundaries. No
values for those labels are recorded.
