# Restricted Staging Validation Evidence

## Evidence Classification

Batch 14 evidence is classified as:

- `Local/provisional validation`: commands that ran successfully in this local
  workspace with development settings.
- `Negative local production-settings validation`: commands that intentionally
  showed production checks reject unsafe local database/cache substitutes.
- `Blocked real staging validation`: checks that require real restricted
  staging infrastructure that was not provided.

This document does not claim real restricted staging validation or production
readiness.

## Environment Used

Local environment:

- Branch: `batch-14-restricted-staging-validation-evidence`
- Base commit: `abeaf11d09872a63f1c98d54bce814c0e68acb66`
- Python: `Python 3.14.2`
- Default settings module: `config.settings.dev`
- Default database: SQLite
- Default cache: LocMemCache
- Local patient count from safe report: 0
- Local appointment count from safe report: 0

Infrastructure availability:

- Docker: unavailable
- `docker compose`: unavailable
- `psql`: unavailable
- `redis-cli`: unavailable
- Bash: unavailable
- Real restricted staging variables: unavailable
- Real staging services: unavailable

## Repository Sync Evidence

| Command | Summarized output |
| --- | --- |
| `git status --short --branch` | Clean `main` tracking `origin/main` before work. |
| `git fetch origin` | Exit 0. |
| `git checkout main` | Already on `main`; up to date. |
| `git pull --ff-only origin main` | Already up to date. |
| `git log -1 --oneline` | `abeaf11 BATCH-13: add final UX product flow specifications (#19)` |
| `git rev-parse HEAD` | `abeaf11d09872a63f1c98d54bce814c0e68acb66` |
| `git branch --show-current` | `main` before branch creation. |

After preflight, the working branch
`batch-14-restricted-staging-validation-evidence` was created from the verified
base.

## Local Validation Commands

| Command | Evidence classification | Summarized output |
| --- | --- | --- |
| `python --version` | Local/provisional | `Python 3.14.2` |
| `python manage.py check` | Local/provisional | Exit 0; no system check issues. |
| `python manage.py makemigrations --check --dry-run` | Local/provisional | Exit 0; no changes detected. |
| `python manage.py migrate --check` | Local/provisional | Exit 0; no unapplied migrations reported. |
| `python manage.py deployment_smoke` | Local/provisional | Exit 0; `WARNING`; 16 pass, 4 local warnings, 0 failures, 0 strict blockers. |
| `python manage.py deployment_smoke --json` | Local/provisional | Exit 0; JSON `status=warning`; summary 16 pass, 4 warnings, 0 failures, 0 strict blockers. |
| `python manage.py deployment_smoke --strict` | Local/provisional | Exit 0 under dev settings; same 16 pass, 4 warnings, 0 failures, 0 strict blockers. |
| `python manage.py check --deploy` | Local/provisional | Exit 0 with 6 expected local-development Django security warnings. |
| `python manage.py production_settings_report` | Local/provisional | Exit 0; reported dev settings, SQLite, LocMem, HTTPS redirect false, secure cookies false, HSTS false, proxy trust false. |
| `python manage.py production_settings_report --json` | Local/provisional | Exit 0; safe JSON only; backend categories and booleans. |
| `python manage.py project_status_report` | Local/provisional | Exit 0; counts and booleans only; 0 patients, 0 appointments. |
| `python manage.py project_status_report --json` | Local/provisional | Exit 0; route/security categories only; prohibited feature flags false. |

The four local smoke warnings were:

- `DEBUG=True` under development settings.
- SQLite active instead of PostgreSQL.
- LocMemCache active instead of Redis/shared cache.
- HTTPS redirect disabled under development settings.

These are expected local-development warnings and are not real staging results.

## Documented Local Script Evidence

| Command | Evidence classification | Summarized output |
| --- | --- | --- |
| `powershell -ExecutionPolicy Bypass -File scripts/validate_local_release.ps1` | Local/provisional | Exit 0; branch and HEAD reported; migration commands passed; smoke warning-only; project status report safe; full 246-test suite OK. |

The script did not deploy, provision, publish, push, merge, or print secret
values.

## Strict Staging Script Evidence

| Command | Evidence classification | Summarized output |
| --- | --- | --- |
| `powershell -ExecutionPolicy Bypass -File scripts/validate_staging_env.ps1 -Strict -Json` | Blocked real staging validation | Exit 1; required staging environment variables were missing; values were not printed. |

The missing staging contract variables were:

- `DJANGO_SETTINGS_MODULE`
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL`
- `CACHE_URL`
- `DJANGO_CACHE_KEY_PREFIX`

This means no real restricted staging shell was available for Batch 14.

## Local Service Availability Evidence

| Command | Evidence classification | Summarized output |
| --- | --- | --- |
| `docker --version` | Blocker check | Command unavailable in PATH. |
| `docker compose version` | Blocker check | Command unavailable in PATH. |
| `psql --version` | Blocker check | Command unavailable in PATH. |
| `redis-cli --version` | Blocker check | Command unavailable in PATH. |
| `bash --version` | Blocker check | Command unavailable in PATH. |

Because Docker and direct PostgreSQL/Redis clients were unavailable, the
documented local PostgreSQL/Redis harness could not be started or validated.

## Synthetic Production-Settings Negative Evidence

A synthetic local-only `config.settings.prod` environment was attempted with
generated local-only secret material, localhost host/origin shapes, SQLite, and
LocMemCache. No real secrets, production services, or real patient data were
used.

| Command | Evidence classification | Summarized output |
| --- | --- | --- |
| `python manage.py production_settings_report` under synthetic local `config.settings.prod` with SQLite and LocMem | Negative local production-settings validation | Exit 1 before report output; system checks rejected LocMemCache and SQLite. |
| `python manage.py check` under the same synthetic local `config.settings.prod` environment | Negative local production-settings validation | Exit 1 with `clinic.E005` and `clinic.E006`. |

This confirms the project does not silently accept SQLite or LocMemCache in
production settings. It does not validate real PostgreSQL, Redis, HTTPS, or
proxy behavior.

## Test Evidence

| Command | Summarized output |
| --- | --- |
| `python manage.py test apps.core` | 63 tests ran, OK. |
| `python manage.py test apps.clinic` | 7 tests ran, OK. |
| `python manage.py test apps.booking` | 130 tests ran, OK. |
| `python manage.py test apps.patients` | 46 tests ran, OK. |
| `python manage.py test` | 246 tests ran, OK. |

Expected test warning logs were observed for negative security cases:

- prohibited routes returning 404;
- numeric public success routes returning 404;
- numeric portal appointment URLs returning 404;
- CSRF-enforced POSTs returning 403 without a CSRF cookie;
- non-staff staff-route access returning 403;
- GET/POST method boundaries for logout and account recovery.

## Route and Privacy Behaviors Covered by Existing Tests

The existing test suite and safe reports cover:

- login-free public booking;
- confirmed appointment creation in the current bounded booking flow;
- UUID public success URLs;
- absence of numeric public success routes;
- no-cache behavior on booking confirmation and success;
- staff-only appointment list/detail and status operations;
- patient portal authentication;
- patient appointment ownership filtering;
- POST-only portal logout;
- GET-only account recovery;
- no-cache patient portal pages;
- generic portal linking errors;
- hashed rate-limit cache identities;
- no raw public tokens on patient account/dashboard pages;
- no staff URLs or staff-only data on patient pages;
- absence of uploads, medical records, WhatsApp API/webhooks, payments, and
  medical automation routes.

## What Was Validated

Validated locally:

- local repository baseline and clean branch;
- local Django startup and checks;
- local migration drift and migration state;
- local database connectivity;
- local cache set/get/delete;
- local deployment smoke safe output;
- local settings report safe output;
- local route/security status report safe output;
- bounded route/privacy behavior through existing tests;
- production system checks reject SQLite and LocMem under production settings.

## What Was Not Validated

Not validated:

- real restricted staging environment;
- real `config.settings.prod` staging runtime with valid PostgreSQL and Redis;
- real PostgreSQL migrations;
- real PostgreSQL concurrency;
- real Redis/shared-cache rate limits across processes;
- real HTTPS redirect through a reverse proxy;
- real TLS certificate;
- real secure-cookie behavior over HTTPS;
- real CSRF trusted origin behavior for a staging hostname;
- real proxy header overwrite/stripping behavior;
- real backup/restore drill;
- real monitoring/alerting;
- real load/concurrency test;
- real legal/privacy approval.

## Claims Not Allowed From This Evidence

This evidence must not be used to claim:

- production readiness;
- launch readiness;
- real staging readiness;
- PostgreSQL readiness;
- Redis readiness;
- HTTPS/proxy readiness;
- legal/privacy approval;
- backup/restore readiness;
- monitoring readiness;
- load readiness.

The correct conclusion is that local validation passed for the bounded current
scope, while real restricted staging validation remains blocked because the
required infrastructure and environment were not provided.
