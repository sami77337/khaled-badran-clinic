# Staging Gap Analysis

Batch 11 staging gap analysis for Dr. Khaled Badran Clinic.

This document compares the current repository against
`docs/STAGING_VALIDATION_PLAN.md`. It does not deploy the site, provision
external resources, store secrets, validate real staging infrastructure, or
authorize real patient data.

## Scope and Safety Boundary

The current repository provides local development code, local/CI validation
commands, operational documentation, and tests. It does not contain a live
staging or production environment.

Staging must remain:

- restricted or non-public,
- production-like,
- synthetic-data only,
- configured outside Git,
- free of real secrets, credentials, database dumps, logs, private media, and
  real patient data.

No visual design work is part of this gap analysis. Figma remains the source of
truth for visual design.

## Current Repository Baseline

Implemented and locally validated at the start of Batch 11:

- Split Django settings: local `config.settings.dev`, production-like
  `config.settings.prod`.
- Production settings require `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and
  `DATABASE_URL`.
- PostgreSQL is supported through `DATABASE_URL`.
- Redis cache is supported through `CACHE_URL`.
- Production readiness checks exist for unsafe production combinations.
- `deployment_smoke` supports human, JSON, and strict modes.
- `project_status_report` provides safe count-only operational output.
- Health endpoints exist:
  - `/health/` public liveness with no internals.
  - `/health/ready/` readiness with database connectivity and no exception
    details.
- Public booking remains UUID public-token based.
- Numeric public booking success URLs remain absent.
- Staff appointment operations remain staff-only.
- Patient portal pages remain no-cache and ownership filtered.
- Prohibited uploads, medical records, WhatsApp API/webhooks, payments, and
  medical automation routes remain absent.

Baseline command results before Batch 11 edits:

- `python manage.py test`: 228 tests ran, OK.
- `python manage.py deployment_smoke`: warning-only under local dev settings
  with 16 pass, 4 local-development warnings, 0 failures, 0 strict blockers.
- `python manage.py project_status_report`: safe count-only output with 0
  patients and 0 appointments.

## Comparison to Staging Validation Plan

| Requirement from staging plan | Current repo status | Gap |
| --- | --- | --- |
| `DJANGO_SETTINGS_MODULE=config.settings.prod` in staging | Production settings exist and are documented | Not validated against a real staging host |
| Staging application secret outside Git | Required by production settings and docs | No real staging secret exists in repo, correctly |
| Exact `DJANGO_ALLOWED_HOSTS` | Supported and checked | No actual staging hostname configured |
| HTTPS `DJANGO_CSRF_TRUSTED_ORIGINS` | Supported and checked | No actual staging HTTPS origin configured |
| PostgreSQL through `DATABASE_URL` | Supported by settings and dependency set | No real PostgreSQL staging validation has run |
| Redis/shared cache through `CACHE_URL` | Supported by settings and dependency set | No real Redis/shared-cache staging validation has run |
| `DEBUG=False` | Production default is false | Must be verified in staging environment |
| HTTPS redirect, secure cookies, HSTS | Production defaults exist | Must be verified through real TLS/proxy path |
| Reverse proxy header trust review | Settings are opt-in and documented | No real proxy exists to verify stripping/overwriting |
| No real patient data | Docs and tests enforce synthetic-only posture | Operator discipline still required in staging |
| `python manage.py migrate` | Supported | Has not run against staging PostgreSQL |
| `python manage.py check` | Runs locally and in CI | Must run under staging settings |
| `python manage.py check --deploy` | Documented | Must be reviewed under production-like env |
| `deployment_smoke --strict` | Exists | Must pass under staging settings and services |
| `deployment_smoke --json` safe archive | Exists | Must be checked after real staging run |
| `project_status_report --json` safe snapshot | Exists | Must be checked after real staging run |
| Seed commands use synthetic data | Existing commands avoid patients/appointments | Must be run only in safe staging context |
| Backup/restore drill | Runbook exists | No drill evidence exists |
| Load/concurrency validation | Plan exists | No PostgreSQL/Redis staging results exist |
| Monitoring and alerting | Health/readiness endpoints exist | No uptime checks, alerts, or error reporting configured |

## Already Implemented

- Django project foundation and split settings.
- Local SQLite fallback for development and CI.
- Production settings fail closed for missing core secrets/hosts/database URL.
- Redis cache support via Django `RedisCache`.
- Production readiness checks for:
  - `DEBUG=True`,
  - placeholder or missing `SECRET_KEY`,
  - empty or wildcard `ALLOWED_HOSTS`,
  - empty `CSRF_TRUSTED_ORIGINS`,
  - LocMemCache in production,
  - SQLite in production,
  - forwarded IP trust without proxy attestation.
- Safe `deployment_smoke` checks.
- Safe `project_status_report`.
- Health/readiness endpoints with no internals.
- CI checks and tests using local SQLite only.
- Booking UUID public-token safety.
- Staff-only appointment operations.
- Portal no-cache and ownership checks.
- Hashed rate-limit identity approach for booking and portal paths.
- Documentation for staging, production readiness, release gates, data
  exposure, route access, backup/restore, incident response, and load tests.

## Only Documented Today

The following are documented but not yet proven in a real environment:

- Restricted staging access model.
- Real staging hostnames.
- Real TLS certificate and HTTPS redirect behavior.
- Real reverse proxy header stripping and rewriting.
- Staging PostgreSQL provisioning.
- Staging Redis/shared-cache provisioning.
- Least-privilege staging database user.
- Real staging environment variables.
- Staging admin/staff credential procedure.
- Backup encryption and retention.
- Restore drill evidence.
- Monitoring owner and alert routing.
- Error reporting privacy scrubbing.
- Dependency vulnerability response workflow.
- Staff access review and offboarding process.
- Legal/privacy approval.
- Patient identity verification policy.
- Secure account recovery policy.

## Requires Real External Infrastructure

The following cannot be completed inside this repository alone:

- Hosting platform, process manager, and private staging access controls.
- DNS or internal staging hostname management.
- TLS certificate provisioning and renewal.
- Reverse proxy or load balancer behavior.
- PostgreSQL service and credentials.
- Redis or equivalent shared cache service.
- Secret manager or environment injection.
- Backup storage and encryption key management.
- Uptime monitoring service.
- Error reporting or application performance monitoring service.
- Alert recipient routing.
- Provider-specific log aggregation.

Batch 11 must not create any of these resources.

## Can Be Validated Locally

The repository can validate these items without external services:

- `makemigrations --check --dry-run`.
- Local migrations against SQLite.
- `python manage.py check`.
- `python manage.py check --deploy` with expected local warnings.
- `deployment_smoke` human and JSON output safety.
- `deployment_smoke --strict` behavior under test-overridden production-like
  settings.
- `project_status_report` human and JSON output safety.
- Full Django test suite.
- Seed command safety.
- Route absence for prohibited features.
- No raw secrets or patient-identifying values in command output.
- No raw phone or public-token values in rate-limit cache keys.
- No CSS or visual-design changes.
- Static scans for forbidden command patterns in local validation scripts.

## Can Be Validated in CI

CI can safely validate:

- Dependency installation from `requirements.txt`.
- Migration drift check.
- Django system checks.
- Local SQLite migration application.
- `deployment_smoke` and safe JSON smoke output.
- `project_status_report` and safe JSON status output.
- Full test suite.
- Documentation and script static checks.
- No real-looking secrets in templates, scripts, Docker harness, and Dependabot
  config.

CI should not require external PostgreSQL, Redis, DNS, TLS, or provider secrets
unless a later batch explicitly approves a stable service-backed CI strategy.

## Requires Docker, PostgreSQL, or Redis

These checks need local Docker services or externally provided local services:

- PostgreSQL migration validation against a PostgreSQL database.
- PostgreSQL appointment active-slot constraint inspection.
- PostgreSQL duplicate booking race behavior under concurrent transactions.
- Redis/shared-cache rate-limit behavior.
- Cache key prefix isolation against Redis.
- Redis outage behavior experiments.

If Docker Desktop, PostgreSQL, or Redis is unavailable, Batch 11 should record
the blocker and continue with documentation, scripts, tests, and dry-run checks.

## Must Remain Manual

The following require human/operator review:

- Confirm staging remains private or access-restricted.
- Verify no real patient data enters staging.
- Approve generated staging secrets outside Git.
- Verify TLS certificate, HTTPS redirect, HSTS, and cookie behavior through a
  browser or trusted HTTP client.
- Verify reverse proxy header stripping/overwriting.
- Review `check --deploy` warnings in the actual staging context.
- Review logs for secret and patient-data scrubbing.
- Approve backup retention, RPO, and RTO.
- Review restore drill evidence.
- Approve legal/privacy content.
- Approve staff/admin access roster.
- Approve any future Figma visual handoff.

## Launch Blockers Remaining After Batch 10

- No real staging infrastructure has been validated.
- No production infrastructure exists.
- No PostgreSQL staging validation has run.
- No Redis/shared-cache staging validation has run.
- No TLS/reverse proxy validation has run.
- No backup/restore drill evidence exists.
- No monitoring, alerting, uptime checks, or error reporting are configured.
- No dependency vulnerability scanning process is active.
- No formal staff/admin access governance process is approved.
- No legal/privacy review is recorded.
- No patient identity verification policy is approved.
- No secure account recovery process is approved.
- No production rate-limit tuning has occurred.
- No load/concurrency test results exist.
- No static serving strategy has been validated.
- Future visual changes remain blocked on Figma.
- Uploads, medical records, WhatsApp API/webhooks, payments, and medical
  automation remain intentionally absent.

## Severity Table

| Severity | Gap | Why it matters | Current disposition |
| --- | --- | --- | --- |
| Critical blocker | No restricted production-like staging run | The app has not been proven with production settings and infrastructure | Must complete before launch |
| Critical blocker | No PostgreSQL staging validation | SQLite local passing is not concurrency or migration proof | Must complete before launch |
| Critical blocker | No Redis/shared-cache validation | Rate limits may not work across production processes with LocMemCache | Must complete before launch |
| Critical blocker | No HTTPS/proxy validation | Secure cookies, redirects, CSRF origins, and IP trust depend on real proxy behavior | Must complete before launch |
| Critical blocker | No backup/restore drill | Recovery is unproven | Must complete before launch |
| High | No monitoring or alert routing | Failures and abuse may go unnoticed | Add before launch |
| High | Legal/privacy review incomplete | Public clinic/patient flows need formal review | Blocked pending owner/counsel |
| High | Account recovery and identity policy unresolved | Portal safety depends on verified ownership and identity processes | Blocked pending policy |
| High | Dependency scanning not configured | Vulnerable dependencies may be missed | Add low-noise scanning |
| Medium | Load/concurrency testing not run | Booking races and performance are not staged | Run after PostgreSQL/Redis staging exists |
| Medium | Staff/admin governance not formalized | Admin access risk remains operational | Document and approve process |
| Medium | Static serving strategy not finalized | Production asset delivery is unproven | Validate with deployment target |
| Low | Local validation scripts absent at baseline | Operators need repeatable command bundles | Add Batch 11 scripts |
| Low | Service-only local Docker harness absent at baseline | Local PostgreSQL/Redis rehearsal is harder | Add optional local-only harness if safe |
| Deferred | Upload/private media design | Uploads are intentionally absent | Future approved batch only |
| Deferred | Medical records | Not implemented and not launch prerequisite for current bounded demo | Future approved batch only |
| Deferred | WhatsApp API/webhooks | Not implemented and requires separate consent/security design | Future approved batch only |
| Deferred | Payments | Not implemented and requires provider/privacy/reconciliation design | Future approved batch only |
| Deferred | Medical AI/automation | Prohibited in current scope | Keep absent |

## Conservative Conclusion

The project is not launch-ready.

The current repository is suitable for local synthetic demos and for building a
restricted staging validation process. It is not evidence that staging or
production is safe. Launch remains blocked until production-like staging passes
with PostgreSQL, Redis/shared cache, HTTPS/proxy validation, safe environment
variables, backup/restore evidence, monitoring/alerting readiness, legal/privacy
review, staff/admin governance, and dependency/security review.

Design status: No design work performed by Codex.
