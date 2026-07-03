# Batch 15 OPS 03 Status - Staging Uptime and Latency Monitoring Evidence

## Scope

BATCH-15-OPS-03 added a safe, lightweight, repository-native uptime and latency
checking mechanism for the public Render restricted staging endpoints.

This batch did not add product features, routes, models, migrations,
templates, dashboards, WhatsApp, uploads, medical records, payments, AI, paid
monitoring providers, alert routes, external monitoring accounts, Render
setting changes, or patient data.

No booking POSTs were submitted. No private, staff, admin, or patient-specific
routes were checked. No response bodies were recorded.

Production-ready status:

```text
no
```

## Branch and Base

- Working branch:
  `codex/batch-15-ops-03-staging-uptime-latency-monitor`
- Base branch: `main`
- Verified base commit:
  `b13466b8f543e2272d59690d0f2fc4d2266c0aed`
- Base subject:
  `Merge PR #27: document synthetic restore drill evidence`
- Repository remote:
  `sami77337/khaled-badran-clinic`
- Render restricted staging URL:
  `https://khaled-badran-clinic-staging.onrender.com`
- Evidence date:
  `2026-07-03`

The preserved local branch `feat/security-operations-release-evidence` was not
checked out, modified, rebased, merged, deleted, pushed, or used.

## Documentation Inspected

This batch read the required operations, release, staging, and Render
documents before editing:

- `docs/BATCH_15_OPS_01_STATUS.md`
- `docs/BATCH_15_OPS_02_STATUS.md`
- `docs/OPERATIONS_MONITORING_ALERTING_PLAN.md`
- `docs/SYNTHETIC_RESTORE_DRILL_EVIDENCE.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/RENDER_STAGING_SETUP.md`
- `docs/STAGING_ENVIRONMENT_CONTRACT.md`

Existing GitHub Actions workflows were also inspected:

- `.github/workflows/django.yml`

## Repository State Commands

| Command | Result |
| --- | --- |
| `git fetch origin main` | Exit 0. |
| `git status -sb` before branching | Clean `main` tracking `origin/main`. |
| `git branch --show-current` before branching | `main` |
| `git rev-parse HEAD` before branching | `b13466b8f543e2272d59690d0f2fc4d2266c0aed` |
| `git rev-parse origin/main` | `b13466b8f543e2272d59690d0f2fc4d2266c0aed` |
| `git merge-base --is-ancestor b13466b origin/main` | Exit 0; `origin/main` contains `b13466b`. |
| `git branch --list feat/security-operations-release-evidence` | Branch exists locally and was left untouched. |
| `git switch -c codex/batch-15-ops-03-staging-uptime-latency-monitor origin/main` | Exit 0. |
| `gh --version` | Exit 0; GitHub CLI available. |
| `gh auth status` | Exit 0; authenticated for repository operations. No credential values are recorded here. |

## Existing GitHub Actions Inspection

Existing CI remains in `.github/workflows/django.yml`.

Current Django CI behavior:

- triggers on pull requests;
- triggers on pushes to `main` and `feat/**`;
- uses local development settings;
- installs repository requirements;
- checks migrations;
- runs Django checks and deploy checks;
- applies local CI migrations;
- runs deployment smoke reports;
- runs project and production settings reports;
- runs the full Django test suite.

BATCH-15-OPS-03 did not modify this workflow.

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

These local warnings remain unacceptable for production launch.

## Repository-Native Uptime Workflow

Added workflow:

- `.github/workflows/staging-uptime.yml`

Workflow behavior:

- can be run manually with `workflow_dispatch`;
- runs on a low-frequency schedule twice daily at `05:17` and `17:17` UTC;
- uses GitHub-hosted Ubuntu and built-in `curl`;
- does not check out the repository;
- does not use secrets;
- does not use third-party Actions;
- follows redirects;
- does not print response bodies;
- checks only public GET endpoints:
  - `https://khaled-badran-clinic-staging.onrender.com/health/`
  - `https://khaled-badran-clinic-staging.onrender.com/`
- captures only:
  - HTTP status;
  - total response time;
  - final URL.

Failure behavior:

- HTTP status other than `200` fails the workflow;
- `curl` timeout or transport failure fails the workflow;
- response time over `10` seconds emits a warning;
- response time over `60` seconds fails the workflow as a hard staging
  latency threshold;
- `curl` uses `--max-time 75` so slow cold-start behavior can be observed
  before the request is treated as failed.

This workflow is not a full monitoring provider and does not route alerts to
an operator. It is interim repository-native evidence only.

## Manual Local Verification Commands

PowerShell commands were documented in
`docs/STAGING_UPTIME_LATENCY_MONITORING_EVIDENCE.md` for manual, script-free
verification:

```powershell
curl.exe --location --silent --show-error --output NUL --max-time 75 --write-out "status=%{http_code} time_total=%{time_total}s final_url=%{url_effective}`n" "https://khaled-badran-clinic-staging.onrender.com/health/"
```

```powershell
curl.exe --location --silent --show-error --output NUL --max-time 75 --write-out "status=%{http_code} time_total=%{time_total}s final_url=%{url_effective}`n" "https://khaled-badran-clinic-staging.onrender.com/"
```

Interpretation documented:

- status other than `200` means the public staging check failed;
- response time over `10` seconds is a staging latency warning;
- response time over `30` seconds is severe staging latency evidence that
  requires review, even if the status is `200`;
- timeout, DNS failure, TLS failure, or connection failure means the public
  staging endpoint was unavailable from that client at that time.

## Latency Observations Documented

Metadata-only public GET spot checks run during this batch:

| Endpoint | HTTP status | Final URL | Response time |
| --- | ---: | --- | ---: |
| `GET /health/` | 200 | `https://khaled-badran-clinic-staging.onrender.com/health/` | `32.536797` seconds |
| `GET /` | 200 | `https://khaled-badran-clinic-staging.onrender.com/` | `0.776475` seconds |

No response bodies were printed.

Known staging observations documented for this interim evidence:

| Endpoint | Observation |
| --- | --- |
| `GET /health/` | HTTP 200 with observed response time around `32.5` seconds. |
| `GET /health/` | HTTP 200 with observed response time around `22.4` seconds. |
| `GET /health/` | HTTP 200 with observed response time around `42.5` seconds. |
| `GET /` | HTTP 200 with observed response time around `0.65` to `0.80` seconds. |

The slow `/health/` examples are staging evidence only. They are not a
production SLA, and they do not prove root cause. They may reflect Render
cold-start behavior, platform queuing, worker startup delay, network latency,
runtime stalls, or other staging-only conditions that require owner/operator
review before launch.

## Conclusions

Repository-native staging uptime workflow:

```text
added
```

Full monitoring provider:

```text
incomplete
```

Alert routing:

```text
incomplete
```

Privacy-safe error reporting:

```text
incomplete
```

Render cold-start/latency:

```text
observed and tracked
```

Production-ready:

```text
no
```

## Secret and Data Handling

No active Render settings were changed. No Render environment dump, full Render
log, credential value, connection string, private key, or operational secret
was recorded.

No booking POST was submitted. No patient, appointment, medical, upload,
payment, WhatsApp, or automation data was created. No real patient data was
used.

Only public GET checks against `/health/` and `/` are included in the workflow
and manual verification commands.

This document intentionally avoids secret values and connection strings. It may
mention forbidden labels such as `DATABASE_URL`, `CACHE_URL`, `SECRET_KEY`,
password, token, and private key only as categories or policy boundaries. No
values for those labels are recorded.

## Remaining Blockers

Production launch remains blocked by at least:

- full external monitoring provider not configured;
- alert routing not configured or tested;
- privacy-safe error reporting not configured;
- real Render managed PostgreSQL restore drill not executed;
- backup retention, RPO, and RTO not approved;
- backup job monitoring not configured;
- legal/privacy approval not recorded;
- load/concurrency validation not completed;
- direct managed PostgreSQL runtime evidence still incomplete;
- direct managed Redis/shared-cache runtime evidence still incomplete;
- Redis multi-process quota and outage behavior still incomplete;
- dependency vulnerability scan evidence and response ownership still
  incomplete;
- production hosting, DNS/custom domain/TLS, and production reverse proxy not
  configured by this repository.
