# Batch 14C-VALIDATE-01 Status - Render Restricted Staging Evidence

## Scope

Batch 14C-VALIDATE-01 validated and documented sanitized evidence for the real
Render restricted staging environment after the staging web service became
externally reachable.

This was a verification and documentation batch only. It did not add product
features, redesign UI, change models, add migrations, change deployment code,
use real patient data, create appointments, or expose secret values.

The previously exposed staging database connection is treated as deleted and
invalid. No database or cache connection strings are recorded in this document.

## Branch and Base

- Working branch:
  `codex/batch-14c-validate-01-render-staging-evidence`
- Base branch: `main`
- Verified base commit:
  `3e54321cda3edd8d0db9b6e0b2c2f25cbea94ee8`
- Repository remote:
  `sami77337/khaled-badran-clinic`
- Starting local state:
  clean `main` tracking `origin/main`

The preserved local branch `feat/security-operations-release-evidence` was not
checked out, modified, rebased, merged, deleted, pushed, or used.

## Render Staging Snapshot

- Staging URL:
  `https://khaled-badran-clinic-staging.onrender.com`
- Render Web Service ID:
  `srv-d937nq67r5hc73bnebi0`
- Render region:
  Frankfurt
- Render branch:
  `main`
- Runtime:
  Python
- Validation timestamp:
  `2026-07-02 22:51:58 +03:00` Asia/Amman
- Data boundary:
  synthetic/no-patient data only

The service ID, region, branch, and runtime are sanitized operational facts from
the known staging state. No Render environment values, credentials, connection
strings, tokens, or full logs were used or recorded.

Functional restricted staging status:

```text
yes - bounded public GET and liveness evidence only
```

Production-ready status:

```text
no
```

## Documentation Inspected

The validation pass inspected the existing staging and release documentation,
including:

- `docs/RENDER_STAGING_SETUP.md`
- `docs/STAGING_ENVIRONMENT_CONTRACT.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/BATCH_14C_PREP_01_STATUS.md`
- `docs/RESTRICTED_STAGING_VALIDATION_EVIDENCE.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- related Batch 14, Batch 14B, and Batch 14B-FIX-01 evidence docs

`docs/LAST_CHECKPOINT.md` and `docs/BLOCKERS.md` were not present in this
checkout.

## Repository State Commands

| Command | Result |
| --- | --- |
| `git branch --show-current` before branching | `main` |
| `git status -sb` before branching | Clean `main` tracking `origin/main`. |
| `git remote -v` | Remote points to `sami77337/khaled-badran-clinic`. |
| `git fetch origin main` | Exit 0. |
| `git rev-parse origin/main` | `3e54321cda3edd8d0db9b6e0b2c2f25cbea94ee8` |
| `git rev-parse HEAD` before branching | `3e54321cda3edd8d0db9b6e0b2c2f25cbea94ee8` |
| `git switch -c codex/batch-14c-validate-01-render-staging-evidence origin/main` | Exit 0. |

## Local Baseline Commands

These commands ran locally without production or staging secrets:

| Command | Result |
| --- | --- |
| `python --version` | `Python 3.14.2` |
| `python manage.py check` | Exit 0; no system check issues. |
| `python manage.py test` | Exit 0; 246 tests ran, OK. |
| `python manage.py deployment_smoke` | Exit 0; warning-only local result: 16 pass, 4 expected local warnings, 0 failures, 0 strict blockers. |
| `python manage.py production_settings_report` | Exit 0; safe local report only; development settings, SQLite, local memory cache, and local HTTPS/security warnings were reported without sensitive values. |
| `python manage.py project_status_report` | Exit 0; safe counts and feature flags only; 0 patients and 0 appointments in the local report. |

The local smoke warnings are expected for `config.settings.dev` and are not
acceptable production settings. No real staging environment values were copied
into the local workspace.

## External Staging Checks

`Invoke-WebRequest` was attempted first for the public staging URLs, but the
local PowerShell client raised a `NullReferenceException` before returning an
HTTP status. The same GET checks were rerun with `curl.exe` and completed.

| Check | Result |
| --- | --- |
| `GET https://khaled-badran-clinic-staging.onrender.com/health/` | HTTP 200 |
| `GET https://khaled-badran-clinic-staging.onrender.com/` | HTTP 200 |
| `GET https://khaled-badran-clinic-staging.onrender.com/book/` | HTTP 200 |
| `GET https://khaled-badran-clinic-staging.onrender.com/en/book/` | HTTP 200 |

Only safe public GET requests were used. No booking POST was submitted and no
patient or appointment data was created.

## Evidence Summary

Validated:

- the real Render restricted staging web service is externally reachable over
  HTTPS;
- `/health/` returns HTTP 200;
- `/` returns HTTP 200;
- Arabic and English public booking entry pages return HTTP 200 by GET;
- the staging service was checked after the clean start command had been
  restored;
- local baseline checks and the full local test suite still pass.

Not validated in this batch:

- full staging shell command evidence under the Render runtime;
- production-like deploy checks from inside the Render environment;
- booking POST, CSRF trusted-origin behavior, or secure-cookie behavior through
  a browser;
- HTTP-to-HTTPS redirect behavior;
- HSTS header behavior;
- reverse proxy header overwrite or client IP stripping behavior;
- managed database migration state by direct safe shell command;
- managed cache rate limits across multiple app processes;
- cache outage behavior;
- backup and restore;
- monitoring, alert routing, and error reporting;
- load or concurrency behavior;
- legal/privacy approval;
- production launch readiness.

## Remaining Blockers

Production launch remains blocked until all of the following are separately
validated or approved:

- legal/privacy approval;
- retention/deletion policy;
- patient identity verification policy;
- secure account recovery policy;
- backup/restore drill with synthetic data;
- monitoring, uptime checks, alert routing, and privacy-safe error reporting;
- load/concurrency validation against staging;
- duplicate booking and staff collision behavior under real provider
  concurrency;
- shared-cache quota behavior across processes;
- cache outage behavior;
- dependency vulnerability scan evidence and response ownership;
- staff access review and offboarding process;
- audit retention/access review policy;
- Figma-approved future visual changes where applicable.

The following product areas remain future-gated and out of scope:

- WhatsApp sending or webhooks;
- uploads and private media;
- medical records;
- payments;
- diagnosis automation;
- triage automation;
- treatment automation;
- clinical decision support;
- medical AI.

## Secret Handling

Render logs and Render CLI were not used in this batch. No environment dump was
printed. No passwords, tokens, application secrets, database connection
strings, cache connection strings, or patient-identifying data were documented
or committed.
