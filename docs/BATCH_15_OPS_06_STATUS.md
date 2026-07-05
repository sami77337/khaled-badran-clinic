# Batch 15 OPS 06 Status - Monitoring, Alert Routing, and Error Readiness

## Scope

BATCH-15-OPS-06 records documentation and evidence for monitoring-provider
readiness, alert-routing readiness, privacy-safe error-reporting readiness,
and the operations signal matrix for Dr. Khaled Badran Clinic.

This batch is docs/evidence-only. It does not configure a monitoring provider,
create external accounts, route alerts, add an error-reporting SDK, add
credentials, change Render settings, change dependencies, change application
code, add migrations, submit booking forms, create patient data, inspect
private provider state, or approve production launch.

Production-ready status:

```text
no
```

## Branch and Base

- Working branch:
  `codex/batch-15-ops-06-monitoring-alerting-error-readiness`
- Base branch: `main`
- Verified base commit:
  `24704577e801e1ec5a4903ca2f18a61ef036ca52`
- Base subject:
  `Merge pull request #31 from sami77337/codex/batch-15-ops-05-dependency-scan-workflow`
- Repository remote:
  `sami77337/khaled-badran-clinic`
- Evidence date:
  `2026-07-05` local Asia/Amman workstation date

## Pre-Change Validation Evidence

The operator supplied the following pre-change validation evidence for this
docs/evidence-only batch:

| Validation | Result |
| --- | --- |
| Local baseline settings | Ran under `config.settings.dev`. |
| `python manage.py test` | Passed; 246 tests OK. |
| `python -m pip check` | Passed. |
| `pip-audit` version | `pip-audit 2.10.1`. |
| `pip-audit -r requirements.txt --progress-spinner off` | Passed; `No known vulnerabilities found`. |

This batch did not rerun the full application test suite because no app code,
migrations, dependency files, settings, templates, or workflows were changed.

## Documents Inspected

- `docs/NEXT_BATCH.md`
- `docs/BATCH_15_OPS_05_STATUS.md`
- `docs/OPERATIONS_MONITORING_ALERTING_PLAN.md`
- `docs/STAGING_UPTIME_LATENCY_MONITORING_EVIDENCE.md`
- `docs/MONITORING_ALERTING_READINESS.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/SECURITY_REGRESSION_CHECKLIST.md`
- `docs/INCIDENT_RESPONSE_RUNBOOK.md`

## New Evidence Documents

- `docs/BATCH_15_OPS_06_STATUS.md`
- `docs/OPERATIONS_SIGNAL_MATRIX.md`

## Existing Documents Updated

- `docs/OPERATIONS_MONITORING_ALERTING_PLAN.md`
- `docs/STAGING_UPTIME_LATENCY_MONITORING_EVIDENCE.md`
- `docs/MONITORING_ALERTING_READINESS.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/SECURITY_REGRESSION_CHECKLIST.md`

## Public Staging GET Spot Checks

Safe public GET checks were run against the existing Render restricted staging
host. Response bodies were discarded. The commands printed only HTTP status,
total response time, and final URL.

| Check | Result |
| --- | --- |
| Safe public GET `/health/` with `curl.exe`, response body discarded, status/time/final URL only | Exit 0; `status=200`; `time_total=32.828721s`; final URL remained `https://khaled-badran-clinic-staging.onrender.com/health/`. |
| Safe public GET `/` with `curl.exe`, response body discarded, status/time/final URL only | Exit 0; `status=200`; `time_total=31.897716s`; final URL remained `https://khaled-badran-clinic-staging.onrender.com/`. |

Interpretation:

- Both public endpoints were available from the local workstation at check
  time because each returned HTTP 200.
- Both response times are severe staging latency evidence under the existing
  manual interpretation threshold for responses over 30 seconds.
- These checks do not prove production uptime, production latency, private
  readiness, database readiness, cache readiness, provider alerting, or launch
  readiness.

## Monitoring Provider Readiness

Status:

```text
not configured; readiness incomplete
```

What exists:

- public `/health/` endpoint;
- private/intended `/health/ready/` endpoint;
- safe smoke/status/report management commands;
- console logging foundation;
- low-frequency repository-native staging uptime workflow for public
  `/health/` and `/` GET checks;
- dependency audit workflow and documented dependency response process;
- monitoring, alerting, error-reporting, and incident-response requirements.

What is still missing:

- approved provider selection;
- external uptime provider account/configuration evidence;
- provider dashboard or alert policy evidence;
- database/cache provider alert evidence;
- backup-failure alert evidence;
- abuse-monitoring dashboard or alert evidence;
- retention/access approval for monitoring events.

Readiness remains incomplete because no external monitoring provider is
selected, configured, validated, or connected to escalation.

## Alert Routing Readiness

Status:

```text
not configured; readiness incomplete
```

What exists:

- role placeholders for primary technical operator, backup technical operator,
  project owner, legal/privacy escalation, and hosting/provider escalation;
- severity model from SEV-1 through SEV-4;
- escalation timing recommendations;
- privacy rules for alert payloads.

What is still missing:

- named human recipients approved outside Git;
- primary and backup alert routes;
- tested paging, chat, email, or provider-notification path;
- escalation coverage schedule;
- route failure fallback;
- evidence that alert payloads do not expose secrets or patient data.

Alert routing remains incomplete because no route is configured or tested.

## Privacy-Safe Error Reporting Readiness

Status:

```text
not configured; readiness incomplete
```

What exists:

- privacy-scrubbing requirements for any future Sentry, GlitchTip, Bugsnag,
  Rollbar, OpenTelemetry, or similar provider;
- documented requirements to disable request-body capture and scrub cookies,
  authorization headers, CSRF tokens, session identifiers, public appointment
  tokens, phone numbers, email addresses unless explicitly approved, patient
  names, booking notes, medical content, database/cache URLs, secret values,
  and provider keys;
- incident-response guidance that excludes secrets, raw logs, and patient data
  from Git.

What is still missing:

- approved provider selection;
- SDK/configuration in an external environment;
- privacy-scrubbing configuration evidence;
- synthetic test event review;
- event retention decision;
- named operator access review;
- legal/privacy approval.

Privacy-safe error reporting remains incomplete because no provider is
configured and no synthetic scrubbed event has been validated.

## Operations Signal Matrix Summary

Detailed matrix:

- `docs/OPERATIONS_SIGNAL_MATRIX.md`

Summary:

| Signal group | Current readiness |
| --- | --- |
| Public liveness and home-page availability | Partial interim evidence exists through GitHub Actions and safe manual GET checks. |
| Public latency | Partial interim evidence exists; latest spot checks show severe staging latency over 30 seconds. |
| Private readiness/database connectivity | Endpoint and smoke-command paths exist, but private provider-connected monitoring is not configured. |
| HTTP 5xx, request errors, and security warnings | Logging expectations are documented, but no provider dashboard or alert is configured. |
| Deploy failures | Command and incident-response expectations are documented, but provider deploy alerts are not validated. |
| PostgreSQL, Redis, and backup signals | Local and planning evidence exists, but provider alerts and Render managed restore evidence remain incomplete. |
| Booking/portal abuse signals | Required signals are documented as aggregate counts, but dashboards and alerts are not configured. |
| Dependency security signals | `pip-audit` local/CI scanning exists; named owner and GitHub alert settings still need decisions. |
| Privacy-safe error reporting | Requirements are documented; provider integration and synthetic scrubbed test are not configured. |
| Incident response | Runbook and severity model exist; live alert route and owner coverage remain untested. |

## Conclusions

Monitoring provider readiness:

```text
incomplete
```

Alert routing readiness:

```text
incomplete
```

Privacy-safe error reporting readiness:

```text
incomplete
```

Operations signal matrix:

```text
documented
```

Public staging availability:

```text
GET /health/ and GET / returned HTTP 200 during the spot checks
```

Public staging latency:

```text
severe staging latency observed; both spot checks exceeded 30 seconds
```

Production-ready:

```text
no
```

## Final Diff and Staged Safety Checks

| Command | Result |
| --- | --- |
| `git diff --check` | Exit 0; no whitespace errors reported. Git displayed local line-ending normalization warnings only. |
| `git diff --cached --name-only` | Exit 0; staged files were the 10 Markdown documents listed in this status file. |
| `git diff --cached --stat` | Exit 0; staged diff was docs-only. |
| `git diff --cached --check` | Exit 0; no whitespace errors reported. |
| Staged scope check | Exit 0; staged scope was docs-only Markdown changes; no app code, migrations, dependency files, Render files, or workflow files were staged. |
| Staged secret/data pattern scan | Exit 0; no staged secret or patient-data pattern matches found. |

## Remaining Blockers

- No external monitoring provider is selected, configured, or validated.
- No alert routing is configured or tested.
- No privacy-safe error-reporting provider is configured.
- No synthetic scrubbed error-reporting event is reviewed.
- No named monitoring owner, backup operator, legal/privacy escalation contact,
  or coverage schedule is approved in repository evidence.
- Public staging GET checks returned HTTP 200 but showed severe latency over
  30 seconds.
- No private `/health/ready/` provider-connected monitoring path is validated.
- No Render managed PostgreSQL restore drill has been completed.
- Backup retention, RPO, and RTO remain unapproved.
- Database, cache, backup, deploy, and abuse alerts are not wired to a tested
  route.
- Legal/privacy approval remains incomplete.
- Load/concurrency validation remains incomplete.
- Production hosting, DNS, custom domain, and TLS remain incomplete.
- Production-ready remains no.

## Secret and Data Handling

No secrets, tokens, connection strings, private keys, patient names, emails,
phone numbers, appointment details, medical data, database dumps, logs,
response bodies, cookies, or provider environment values were recorded.

No active Render staging or production setting was changed. No external
monitoring, alerting, or error-reporting provider was configured. No patient,
appointment, upload, medical record, payment, WhatsApp, or automation data was
created.
