# Monitoring and Alerting Readiness

Batch 11 monitoring and alerting readiness plan for Dr. Khaled Badran Clinic.

This document does not configure external monitoring, create accounts, add
credentials, or send alerts. It defines what must be ready before launch.

## Current Health and Readiness Endpoints

Implemented endpoints:

- `GET /health/`
- `GET /health/ready/`

Current behavior:

- `/health/` returns public liveness JSON with status and service name.
- `/health/ready/` checks database connectivity.
- Readiness returns only `{"status": "ok"}` or
  `{"status": "unavailable"}`.
- Both endpoints are `GET` only.
- Both endpoints are no-cache.
- Neither endpoint exposes secrets, database URLs, cache URLs, exception text,
  settings, stack traces, hostnames, database engine, or patient data.

## What Health Endpoints Do Not Prove

They do not prove:

- PostgreSQL is tuned correctly.
- Redis/shared-cache rate limits work across processes.
- HTTPS, TLS, HSTS, or reverse proxy behavior is correct.
- Static assets are served correctly.
- Public booking works end to end.
- Staff access governance is correct.
- Patient portal abuse monitoring is active.
- Backups are running.
- Restore works.
- Legal/privacy approval exists.
- Error reporting is configured.
- Logs are scrubbed.

Health endpoints are necessary, not sufficient.

## Uptime Check Requirements

Before launch, configure an uptime monitor for:

- `/health/` through the public route.
- `/health/ready/` through a private/internal monitoring path where possible.

Requirements:

- Alert on repeated failures, not a single transient packet loss.
- Record the environment, revision, and timestamp.
- Do not expose readiness details publicly as a diagnostic page.
- Keep alert recipients as placeholders until owner approval.

## Error Reporting Requirements

No external error reporting integration is active in Batch 11.

Before enabling Sentry or another service:

- complete privacy scrubbing review,
- prevent request-body capture by default,
- scrub cookies, authorization headers, CSRF tokens, passwords, phone numbers,
  public tokens, connection strings, and secrets,
- define who can access error events,
- define retention,
- run a synthetic incident test.

Do not add error-reporting DSNs or credentials to Git.

## Log Scrubbing Requirements

Logs must not include:

- full form payloads,
- passwords,
- patient medical content,
- booking notes by default,
- raw phone numbers unless explicitly approved for restricted staff operations,
- raw public tokens,
- database URLs,
- cache URLs,
- secret keys,
- cookies,
- CSRF tokens,
- authorization headers,
- request bodies,
- private media contents.

Logs should include safe operational summaries:

- status codes,
- route names or safe paths,
- exception class where appropriate,
- timestamp,
- environment,
- release revision,
- synthetic test marker when applicable.

## Alert Recipients

Alert recipient names and contact details are placeholders only:

- Primary operator: `TBD`
- Backup operator: `TBD`
- Project owner escalation: `TBD`
- Legal/privacy escalation: `TBD`

Do not commit real private phone numbers, emails, chat webhooks, pager tokens,
or alerting credentials.

## Security Event Signals

Monitor for:

- repeated staff/admin login failures,
- unexpected staff/admin access from unusual networks,
- CSRF failures above baseline,
- repeated 403 responses on staff routes,
- repeated 404 probing of prohibited routes,
- suspicious spikes in account registration or login attempts,
- sudden change in `deployment_smoke --strict` result.

## Booking Abuse Signals

Monitor for:

- high public booking POST rate from one IP identity,
- high booking attempts for one normalized phone hash,
- repeated stale-slot submissions,
- repeated validation failures,
- distributed booking abuse patterns,
- attempts to use numeric success URLs,
- repeated probing of staff operation URLs.

## Portal Abuse Signals

Monitor for:

- high login failure rates,
- high registration attempts,
- high appointment-link attempts,
- repeated wrong token/phone link attempts,
- attempts to access another user's appointment,
- attempts to use numeric portal appointment URLs,
- POST attempts to account recovery,
- repeated CSRF failures on portal forms.

## Failed Login and Linking Rate Monitoring

Staging and production should track rates for:

- portal login failures,
- registration attempts,
- appointment-link failures,
- booking IP quota blocks,
- booking phone quota blocks.

Use aggregated counts and hashed identities where practical. Do not expose raw
phones, raw tokens, passwords, or patient names in monitoring dashboards.

## Backup Failure Alerts

Before launch:

- backup job failure must alert an operator,
- missing backup within the approved window must alert,
- restore drill failure must create a tracked follow-up,
- backup storage access changes must be reviewed.

## Dependency and Security Scan Alerts

Before launch:

- dependency scan failures should create review work,
- high/critical vulnerabilities should alert the owner/operator,
- GitHub Actions failures should be visible,
- Dependabot PRs, if enabled, must be reviewed manually and not auto-merged.

## No External Credentials in Batch 11

Batch 11 does not add:

- Sentry DSN,
- alert webhook,
- email credentials,
- SMS credentials,
- WhatsApp credentials,
- monitoring service API tokens.

All future credentials must be managed outside Git.

## Current Batch 11 Status

Monitoring readiness is planned/partial:

- Safe health/readiness endpoints exist.
- Logging foundation exists.
- Monitoring requirements are documented.
- No external uptime checks, alert routing, error reporting, or abuse dashboards
  are configured.

Design status: No design work performed by Codex.
