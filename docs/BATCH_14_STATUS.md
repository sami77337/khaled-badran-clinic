# Batch 14 Status - Restricted Staging Validation Evidence

## Scope

Batch 14 performed a restricted staging / production-like validation pass for
the current bounded Dr. Khaled Badran Clinic system as far as this local
workspace allowed.

This batch is validation evidence and documentation only. It does not implement
new product features and it does not expand the doctor/admin dashboard surface.

## Branch and Base

- Working branch: `batch-14-restricted-staging-validation-evidence`
- Base branch synced before work: `main`
- Verified base HEAD: `abeaf11d09872a63f1c98d54bce814c0e68acb66`
- Verified base short HEAD: `abeaf11`
- Verified base subject: `BATCH-13: add final UX product flow specifications (#19)`
- Repository state before validation: clean working tree on `main`; then a new
  Batch 14 branch was created from the verified base.

The prompt expected the short HEAD `abeaf11`; that matched. The subject text in
Git was slightly different from the prompt's wording, but it was the same
verified commit.

## Files Changed

Batch 14 added:

- `docs/BATCH_14_STATUS.md`
- `docs/RESTRICTED_STAGING_VALIDATION_EVIDENCE.md`
- `docs/POSTGRESQL_REDIS_VALIDATION_EVIDENCE.md`
- `docs/HTTPS_PROXY_CSRF_VALIDATION_EVIDENCE.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`

Batch 14 updated:

- `docs/NEXT_BATCH.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`

## Explicit No-Code Statement

Batch 14 did not modify:

- application code;
- models;
- migrations;
- templates;
- CSS;
- JavaScript;
- settings;
- dependencies;
- CI;
- Docker or compose files;
- deployment files;
- secrets or credentials;
- external infrastructure.

## Environment Inspected

Local validation environment:

- OS shell: Windows PowerShell
- Python: `Python 3.14.2`
- Django settings during normal validation: `config.settings.dev`
- Database during normal validation: SQLite local development database
- Cache during normal validation: Django LocMemCache
- Docker: unavailable in PATH
- `docker compose`: unavailable in PATH
- `psql`: unavailable in PATH
- `redis-cli`: unavailable in PATH
- Bash: unavailable in PATH
- Real restricted staging infrastructure: not provided
- Real PostgreSQL staging database: not provided
- Real Redis/shared-cache staging service: not provided
- Real HTTPS reverse proxy: not provided

## Required Baseline Commands

Repository preflight before validation:

| Command | Result |
| --- | --- |
| `git status --short --branch` | Clean `main` tracking `origin/main`. |
| `git fetch origin` | Exit 0. |
| `git checkout main` | Already on `main`; up to date with `origin/main`. |
| `git pull --ff-only origin main` | Already up to date. |
| `git log -1 --oneline` | `abeaf11 BATCH-13: add final UX product flow specifications (#19)` |
| `git rev-parse HEAD` | `abeaf11d09872a63f1c98d54bce814c0e68acb66` |
| `git branch --show-current` | `main` before creating the Batch 14 branch. |

Baseline local validation:

| Command | Result |
| --- | --- |
| `git status --short --branch` | Clean Batch 14 branch before documentation edits. |
| `git log -1 --oneline` | `abeaf11 BATCH-13: add final UX product flow specifications (#19)` |
| `git rev-parse HEAD` | `abeaf11d09872a63f1c98d54bce814c0e68acb66` |
| `git branch --show-current` | `batch-14-restricted-staging-validation-evidence` |
| `python --version` | `Python 3.14.2` |
| `python manage.py check` | Exit 0; system check identified no issues. |
| `python manage.py makemigrations --check --dry-run` | Exit 0; no changes detected. |
| `python manage.py migrate --check` | Exit 0; no unapplied migrations reported. |
| `python manage.py deployment_smoke` | Exit 0; `WARNING`, 16 pass, 4 local-development warnings, 0 failures, 0 strict blockers. |
| `python manage.py deployment_smoke --json` | Exit 0; JSON `status=warning`, 16 pass, 4 warnings, 0 failures, 0 strict blockers. |
| `python manage.py deployment_smoke --strict` | Exit 0 under dev settings; same 16 pass, 4 local-development warnings, 0 failures, 0 strict blockers. |
| `python manage.py check --deploy` | Exit 0 with 6 expected Django local-development security warnings. |
| `python manage.py production_settings_report` | Exit 0; safe local report showed dev settings, SQLite, LocMemCache, no HTTPS redirect, insecure local cookies, no HSTS. |
| `python manage.py production_settings_report --json` | Exit 0; safe JSON with booleans, counts, and backend categories only. |
| `python manage.py project_status_report` | Exit 0; safe counts-only report showed 0 patients and 0 appointments. |
| `python manage.py project_status_report --json` | Exit 0; route/security categories only; prohibited feature flags false. |

Documented local validation script:

| Command | Result |
| --- | --- |
| `powershell -ExecutionPolicy Bypass -File scripts/validate_local_release.ps1` | Exit 0; repeated migration check/application, Django check, deployment smoke, project status report, and 246-test suite. |

Strict staging environment script:

| Command | Result |
| --- | --- |
| `powershell -ExecutionPolicy Bypass -File scripts/validate_staging_env.ps1 -Strict -Json` | Exit 1 by design because real staging environment variables were not present. Values were not printed. |

Local production-settings negative check:

| Command | Result |
| --- | --- |
| Synthetic local `config.settings.prod` environment with SQLite and LocMem, then `python manage.py production_settings_report` | Exit 1 before report output because production checks rejected LocMemCache and SQLite. |
| Synthetic local `config.settings.prod` environment with SQLite and LocMem, then `python manage.py check` | Exit 1 with `clinic.E005` for LocMemCache and `clinic.E006` for SQLite. |

The synthetic production-settings commands used generated local-only values and
synthetic localhost host/origin shapes. They were negative checks only and are
not staging validation.

## Test Results

| Command | Result |
| --- | --- |
| `python manage.py test apps.core` | 63 tests ran, OK. |
| `python manage.py test apps.clinic` | 7 tests ran, OK. |
| `python manage.py test apps.booking` | 130 tests ran, OK. |
| `python manage.py test apps.patients` | 46 tests ran, OK. |
| `python manage.py test` | 246 tests ran, OK. |

Expected warning logs appeared during negative-route and security tests,
including 404 checks for prohibited routes, 404 checks for numeric success or
numeric portal appointment URLs, 403 checks for CSRF enforcement, 403 checks for
non-staff staff-route access, and method checks for POST-only or GET-only
routes.

## Pass, Warning, Fail, Blocker Summary

Pass:

- Repository was clean and synced from the verified `main` base.
- Local Django checks passed.
- Migration drift check passed.
- Local migration state check passed.
- Local deployment smoke passed with local-development warnings only.
- Local deployment smoke JSON emitted safe categories only.
- Strict smoke under dev settings did not report strict blockers.
- Project status report showed bounded route/security categories only and 0
  local patients / 0 local appointments.
- App-specific and full tests passed.
- Documented local PowerShell validation script passed.
- Existing tests cover route/privacy boundaries for the current bounded scope.

Warnings:

- Local validation used SQLite, not PostgreSQL.
- Local validation used LocMemCache, not Redis/shared cache.
- Local validation used `DEBUG=True` under `config.settings.dev`.
- Local validation had HTTPS redirect, secure cookies, and HSTS disabled as
  expected for development settings.
- `python manage.py check --deploy` produced 6 expected local-development
  warnings.

Failures:

- Synthetic production-settings commands with SQLite and LocMem failed as
  intended with production-readiness errors. This is a protective failure, not a
  product regression.
- Strict staging environment validation failed because real staging environment
  variables were not provided.

Blockers:

- Real restricted staging infrastructure was not provided or validated.
- Docker and `docker compose` were unavailable, so the documented local
  PostgreSQL/Redis harness could not be started.
- Local `psql` and `redis-cli` were unavailable.
- Real PostgreSQL validation remains incomplete.
- Real Redis/shared-cache validation remains incomplete.
- Real HTTPS/proxy/CSRF behavior remains unproven.

## PostgreSQL Validation Result

Status: blocked for real staging; not validated with PostgreSQL in this batch.

What was validated locally:

- Migration drift passed with `makemigrations --check --dry-run`.
- SQLite migration state check passed with `migrate --check`.
- Existing booking tests passed, including local constraint/collision coverage
  where implemented.
- Production checks reject SQLite under production settings.

What was not validated:

- Real staging PostgreSQL connection.
- PostgreSQL migrations on a staging database.
- PostgreSQL active-slot uniqueness under real PostgreSQL.
- Concurrent duplicate booking behavior under PostgreSQL.
- Staff reschedule collision behavior under PostgreSQL.
- Least-privilege database user, SSL mode, backups, restore, or provider
  connection behavior.

## Redis Validation Result

Status: blocked for real staging; not validated with Redis/shared cache in this
batch.

What was validated locally:

- LocMemCache set/get/delete passed in local smoke.
- Existing tests passed for hashed booking and portal rate-limit identity
  behavior.
- Production checks reject LocMemCache under production settings.

What was not validated:

- Real Redis/shared-cache connection.
- Multi-process shared quota behavior.
- Redis key prefix isolation.
- Redis expiry behavior.
- Redis outage behavior.
- Production rate-limit tuning.

## HTTPS, Proxy, and CSRF Result

Status: local/provisional only; real HTTPS/proxy validation blocked.

What was validated locally:

- Development settings report accurately shows no HTTPS redirect, no secure
  cookies, no HSTS, no proxy SSL header trust, and no forwarded IP trust.
- `check --deploy` warns about local insecure deployment settings.
- Production settings code was inspected and requires environment-driven secret,
  exact allowed hosts, `DATABASE_URL`, secure-cookie defaults, HSTS defaults,
  and opt-in proxy SSL header trust.
- Synthetic production-settings checks with SQLite/LocMem are blocked by
  production-readiness errors.

What was not validated:

- Real HTTP-to-HTTPS redirect through a reverse proxy.
- TLS certificate validity.
- Real `ALLOWED_HOSTS` and HTTPS `CSRF_TRUSTED_ORIGINS` for a staging hostname.
- Real `SECURE_PROXY_SSL_HEADER` behavior through a proxy that overwrites
  `X-Forwarded-Proto`.
- Real `BOOKING_TRUST_X_FORWARDED_FOR` behavior through a proxy that strips
  client-supplied forwarded headers.
- Browser-level secure cookie behavior over HTTPS.

## Route and Privacy Validation

Existing tests and smoke/status reports validated the current bounded scope:

- Public booking remains login-free.
- Public success lookup remains UUID public token based.
- Numeric public success routes remain absent.
- Booking confirmation and success pages are no-cache.
- Staff appointment pages and operations require staff authorization.
- Authenticated non-staff users are denied staff operations.
- Patient portal appointment detail uses UUID token plus authenticated
  ownership filtering.
- Portal pages are no-cache.
- Portal logout is POST-only.
- Account recovery is static/GET-only.
- Prohibited upload, medical-record, WhatsApp API/webhook, payment, and medical
  automation routes remain absent.
- Patient pages do not expose staff operation URLs, staff-only notes, audit
  data, or raw public tokens outside the explicit linking flow.

## Limitations

This batch cannot claim:

- real restricted staging validation;
- production readiness;
- PostgreSQL readiness;
- Redis/shared-cache readiness;
- HTTPS/proxy readiness;
- legal/privacy approval;
- backup/restore readiness;
- monitoring readiness;
- load/concurrency readiness;
- launch approval.

## Recommended Next Batch

Recommended next batch:

```text
Batch 14B: provision and re-run real restricted staging validation
```

Batch 14B should run the existing staging validation plan against a real
restricted staging environment with PostgreSQL, Redis/shared cache, HTTPS,
exact host/CSRF settings, reviewed reverse proxy behavior, and synthetic data
only.

Dashboard implementation should not start before the staging blockers are
resolved or explicitly accepted as deferred by the owner.

## Exclusions Preserved

Batch 14 did not add:

- real patient data;
- real phone numbers;
- real emails;
- real appointments;
- WhatsApp API sending;
- WhatsApp webhooks;
- uploads;
- private media handling;
- medical records;
- payments;
- deployment;
- DNS/TLS changes;
- external infrastructure;
- secrets or credentials;
- diagnosis automation;
- triage automation;
- treatment automation;
- clinical decision support;
- medical AI;
- Figma work;
- visual design.

The preserved local branch `feat/security-operations-release-evidence` was not
used, modified, rebased, merged, deleted, pushed, or included.
