# Operations Monitoring and Alerting Plan

## Purpose

This plan defines production-oriented monitoring, alerting, uptime checks,
error reporting, and incident response readiness for Dr. Khaled Badran Clinic.

This is primarily a planning document. BATCH-15-OPS-03 adds interim
repository-native staging checks, and BATCH-15-OPS-06 adds a docs-only
operations signal matrix for provider readiness, alert routing, and
privacy-safe error-reporting readiness. This document does not configure a
full monitoring provider, add third-party dependencies, create accounts, store
credentials, route alerts, change Render settings, or approve production
launch.

Production-ready status:

```text
no
```

## Current Observability Inventory

Implemented endpoints:

- `GET /health/`
- `GET /health/ready/`

Current endpoint behavior:

- `/health/` is public liveness and does not check the database.
- `/health/ready/` checks database connectivity and returns only `ok` or
  `unavailable`.
- both endpoints are GET-only;
- both endpoints are no-cache;
- neither endpoint exposes secrets, connection strings, hostnames, stack
  traces, database engines, cache URLs, exception text, or patient data.

Existing local commands:

- `python manage.py deployment_smoke`
- `python manage.py deployment_smoke --json`
- `python manage.py deployment_smoke --strict`
- `python manage.py production_settings_report`
- `python manage.py production_settings_report --json`
- `python manage.py project_status_report`
- `python manage.py project_status_report --json`

Existing logging:

- console logging for Django, request errors, security warnings, and booking
  application logs;
- no structured logging dependency;
- no third-party error reporting SDK;
- repository-native GitHub Actions staging uptime workflow exists for public
  `/health/` and `/` evidence only;
- docs-only operations signal matrix exists in
  `docs/OPERATIONS_SIGNAL_MATRIX.md`;
- no external uptime monitoring provider configured;
- no alert routing configured.

## Batch 15-OPS-06 Signal Matrix and Readiness Evidence

BATCH-15-OPS-06 documents the operational signal matrix without configuring
external providers or storing credentials.

New evidence:

- `docs/BATCH_15_OPS_06_STATUS.md`
- `docs/OPERATIONS_SIGNAL_MATRIX.md`

Readiness status:

| Area | Status | Reason |
| --- | --- | --- |
| Monitoring provider readiness | Not configured; incomplete | No external provider is selected, configured, validated, or connected to escalation. |
| Alert routing readiness | Not configured; incomplete | No primary or backup alert route is configured or tested. |
| Privacy-safe error reporting | Not configured; incomplete | No provider integration, privacy-scrubbing configuration evidence, or scrubbed synthetic event review exists. |
| Operations signal matrix | Documented | Liveness, latency, readiness, HTTP errors, deploy, database, cache, backup, abuse, dependency, error-reporting, and incident-response signals are mapped to current evidence and blockers. |

Latest BATCH-15-OPS-06 safe public staging spot checks:

| Endpoint | HTTP status | Total time | Interpretation |
| --- | ---: | ---: | --- |
| `GET /health/` | 200 | `32.828721` seconds | Available, but severe staging latency. |
| `GET /` | 200 | `31.897716` seconds | Available, but severe staging latency. |

Response bodies were discarded. These checks do not prove private readiness,
database health, cache health, provider alerting, production uptime, or launch
readiness.

## Uptime Checks

Interim repository-native staging checks:

- BATCH-15-OPS-03 adds `.github/workflows/staging-uptime.yml`;
- the workflow can be run manually and also runs twice daily;
- it checks only public GET `/health/` and `/` on the Render restricted
  staging URL;
- it uses `curl` only, follows redirects, records HTTP status, total response
  time, and final URL, and does not print response bodies;
- it fails on non-200 status, timeout, transport failure, or response time
  over 60 seconds;
- it warns on response time over 10 seconds;
- it does not use secrets, private routes, booking POSTs, third-party Actions,
  external monitoring providers, or alert routes;
- it is low-frequency evidence collection, not keep-alive polling.

This workflow is not a substitute for a production monitoring provider or
tested alert routing.

Before launch, configure external uptime monitoring for safe GET requests only:

- `GET /health/`
- `GET /`

Recommended public check behavior:

- interval: every 1 minute after provider and alert route are approved;
- timeout: 10 seconds for standard probes;
- alert after repeated failures, not a single transient network issue;
- record environment, route, HTTP status, latency, and revision if available;
- do not submit booking forms;
- do not create patients or appointments;
- do not include credentials or private staging access details in public
  dashboards.

Private/internal readiness monitoring:

- monitor `GET /health/ready/` only through a private/internal monitoring path
  where possible;
- alert on readiness failures separately from public liveness;
- treat readiness failure as database connectivity or runtime dependency risk;
- do not expose readiness diagnostics publicly.

## Latency Thresholds

Latest supplied staging context says:

- `GET /health/` returned HTTP 200, but observed response times included about
  32.5 seconds, 22.4 seconds, and 42.5 seconds.
- `GET /` returned HTTP 200, with observed response times around 0.65 to 0.80
  seconds.

The slow `/health/` responses are not acceptable as a normal production
latency target. Because `/health/` does not check the database, a slow liveness
response may indicate cold start, worker startup delay, platform queuing,
network latency, process saturation, or runtime stalls. It must be tracked
before launch.

The interim GitHub Actions staging workflow warns on any single response over
10 seconds and fails on any single response over 60 seconds. Manual evidence
should treat any response over 30 seconds as severe staging latency requiring
review, even if the HTTP status is 200.

Initial threshold recommendations, subject to owner/operator approval:

| Check | Warning threshold | Critical threshold |
| --- | --- | --- |
| `GET /health/` | p95 over 2 seconds for 10 minutes, or any single response over 10 seconds | three consecutive failures, p95 over 10 seconds for 5 minutes, or two responses over 30 seconds in 15 minutes |
| `GET /` | p95 over 3 seconds for 10 minutes | three consecutive failures, p95 over 10 seconds for 5 minutes, or any sustained 5xx |
| `GET /health/ready/` private | one failure should warn; repeated failures should page/escalate | three consecutive failures or any readiness failure during deploy validation |

Before production launch, tune thresholds using staging evidence and provider
behavior. Do not hide persistent slow `/health/` responses by raising the
threshold without root-cause review.

## Error-Rate Monitoring

Before launch, monitor at least:

- HTTP 5xx rate by environment and route group;
- HTTP 4xx spikes on staff, portal, and prohibited routes;
- Django request error logs;
- Django security warnings;
- CSRF failures above baseline;
- public booking validation failures and quota blocks as aggregate counts;
- portal login, registration, and appointment-link failures as aggregate
  counts;
- repeated 404 probing of prohibited routes;
- staff/admin authentication failures;
- unexpected growth in response time.

Initial alert thresholds should be conservative:

- warning when 5xx rate exceeds 1% for 5 minutes;
- critical when 5xx rate exceeds 5% for 5 minutes or key routes are unusable;
- warning on clear spikes in CSRF failures, staff-route 403s, or prohibited
  route probing;
- critical when suspicious staff/admin access or suspected data exposure is
  involved.

Do not store raw phone numbers, public tokens, passwords, request bodies,
cookies, authorization headers, or patient medical content in monitoring
events.

## Deploy Failure Monitoring

Before launch, configure deploy visibility and alerts for:

- failed build;
- failed deploy;
- failed migration or pre-deploy command;
- repeated app crash/restart;
- failed post-deploy smoke command;
- failed static collection;
- new 5xx spike after deploy;
- rollback initiation.

Post-deploy validation should include:

```bash
python manage.py check
python manage.py check --deploy
python manage.py deployment_smoke --strict
python manage.py production_settings_report
python manage.py project_status_report
```

Run the commands only in a trusted operator shell with environment values
already configured outside Git. Do not print or archive secret values.

## Database Connectivity Monitoring

Monitor database health through:

- private/internal `GET /health/ready/` where possible;
- `deployment_smoke --strict` during deploy validation;
- provider database health dashboard;
- database connection errors in logs;
- migration command failures;
- backup success/failure alerts.

Alert when:

- readiness returns unavailable repeatedly;
- connection errors appear in request logs;
- migration state is uncertain;
- backup job fails or is missing inside the approved recovery window;
- database CPU, memory, storage, or connection count approaches provider
  limits.

Do not expose database hostnames, URLs, usernames, or connection strings in
alerts.

## Cache Connectivity Monitoring

Monitor Redis/shared-cache health through:

- `deployment_smoke --strict` cache set/get/delete;
- provider cache service dashboard;
- cache connection errors in application logs;
- rate-limit behavior checks during staging validation;
- Redis outage drill results once approved.

Alert when:

- cache set/get/delete fails;
- Redis service becomes unavailable;
- cache latency is sustained above provider baseline;
- rate-limit counters are not shared across processes;
- cache outage causes booking or portal throttling to fail open or fail
  unexpectedly.

Redis is not authoritative application data, but it is security-relevant for
rate limits. Treat cache failures as operational security issues, not only
performance issues.

## Privacy-Safe Error Reporting Requirements

No third-party error reporting is configured by this batch.

Before enabling Sentry, GlitchTip, Bugsnag, Rollbar, OpenTelemetry, or another
provider, complete privacy scrubbing review.

Required configuration:

- request-body capture disabled by default;
- cookies scrubbed;
- authorization headers scrubbed;
- CSRF tokens scrubbed;
- session identifiers scrubbed;
- public appointment tokens scrubbed;
- phone numbers scrubbed;
- email addresses scrubbed unless explicitly approved and minimized;
- patient names scrubbed;
- booking notes and medical content scrubbed;
- database/cache connection strings scrubbed;
- application secret values scrubbed;
- provider API keys scrubbed;
- event retention defined;
- access limited to named operators;
- synthetic test event reviewed before live activation.

Do not commit DSNs, webhook URLs, API keys, tokens, private keys, or provider
environment dumps.

## Monitoring Provider Options

No provider is selected or configured in this batch.

Possible future options, without installing anything now:

- GitHub Actions staging uptime workflow for interim repository-native
  evidence only;
- Render native service events and health checks;
- a third-party uptime monitor for `/health/` and `/`;
- Sentry or another error-reporting provider after privacy scrubbing review;
- provider database/cache dashboards for resource alerts;
- GitHub Actions and Dependabot notifications for CI/dependency signals.

The selected provider must support privacy-safe alerting without exposing
patient data or secrets in alert payloads.

## Alert Routing and Escalation

Alert recipients remain placeholders until owner approval:

- Primary technical operator: `TBD`
- Backup technical operator: `TBD`
- Project owner: `TBD`
- Legal/privacy escalation: `TBD`
- Hosting/provider escalation path: `TBD`

Routing requirements:

- no private phone numbers, emails, chat webhooks, pager tokens, or alerting
  credentials in Git;
- alert route tested before launch;
- backup route tested before launch;
- escalation timing documented;
- severity included in alert title;
- environment included in alert title;
- no secret values or patient details in alert payloads.

Recommended escalation timing:

- SEV-1: immediate primary and owner escalation.
- SEV-2: primary operator within 15 minutes; owner if unresolved in 30 minutes.
- SEV-3: primary operator during working hours or according to approved support
  schedule.
- SEV-4: track as planned follow-up.

## Incident Severity Levels

`SEV-1 Critical`

- confirmed or likely patient-data, credential, or private-file exposure;
- active staff/admin compromise;
- production outage affecting booking or staff operations with no workaround;
- data corruption or significant data-loss risk;
- destructive restore or migration failure affecting production.

`SEV-2 High`

- suspicious admin activity not yet confirmed as compromise;
- significant error spike affecting key workflows;
- Redis/cache outage degrading rate limits;
- database readiness failures;
- failed deploy requiring rollback;
- backup job failure inside the approved recovery window.

`SEV-3 Medium`

- degraded public pages;
- intermittent errors;
- elevated latency;
- staging-only failure blocking release validation;
- monitoring gap that reduces confidence but has no active patient impact.

`SEV-4 Low`

- documentation updates;
- checklist follow-up;
- non-urgent tuning;
- planned operational improvement.

## Incident Response Checklist

Use this checklist with `docs/INCIDENT_RESPONSE_RUNBOOK.md`.

1. Assign an incident owner.
2. Declare severity and affected environment.
3. Start a timeline with exact timestamps.
4. Preserve relevant logs and deploy metadata outside Git.
5. Remove secrets, patient data, and raw request bodies from any shared
   evidence.
6. Identify whether impact is availability, data integrity, privacy, security,
   deploy, database, cache, backup, or legal/privacy.
7. Stop the bleeding:
   - pause deploys;
   - roll back code if safer than forward fix;
   - restrict writes if data integrity is at risk;
   - disable affected integration if applicable;
   - restrict staff/admin access if compromise is suspected.
8. Check `/health/`, `/`, and private `/health/ready/` where available.
9. Run safe smoke commands in the affected production-like environment when
   the operator shell is trusted.
10. Escalate to legal/privacy counsel if patient data, credentials, private
    files, or regulated information may be involved.
11. Communicate status through the approved incident channel.
12. Validate recovery before closing.

Do not paste full logs, credentials, connection strings, private keys, tokens,
cookies, request bodies, or real patient data into the incident timeline.

## Post-Incident Review Checklist

Complete after containment and recovery:

- incident severity;
- owner;
- affected environment;
- start and end timestamps;
- detection source;
- root cause;
- customer/patient/clinic impact;
- data integrity assessment;
- privacy/legal assessment;
- what alerted correctly;
- what failed to alert;
- time to detect;
- time to acknowledge;
- time to mitigate;
- time to fully recover;
- commands/checks used for recovery;
- rollback or restore decisions;
- follow-up owners and due dates;
- tests, docs, monitoring, or code changes required;
- confirmation that no secrets or real patient data were stored in Git.

Do not close SEV-1 or SEV-2 incidents without owner approval.

## Current Readiness Classification

Monitoring/alerting readiness:

```text
partial interim evidence, full monitoring not configured
```

Reasons:

- health and readiness endpoints exist;
- privacy-safe smoke/status/settings commands exist;
- logging foundation exists;
- Dependabot exists for dependency update visibility;
- a low-frequency GitHub Actions staging uptime workflow exists for public
  `/health/` and `/` checks;
- the operations signal matrix now documents required signal groups and
  readiness gaps;
- BATCH-15-OPS-06 public staging spot checks returned HTTP 200 for `/health/`
  and `/`, but both exceeded 30 seconds and remain severe staging latency
  evidence;
- external uptime monitoring provider is not configured;
- alert routing is not configured;
- privacy-safe error reporting is not configured;
- deploy/database/cache alerts are not configured;
- backup failure alerts are not configured;
- abuse monitoring is not configured;
- legal/privacy approval remains blocked.

Production launch remains blocked.
