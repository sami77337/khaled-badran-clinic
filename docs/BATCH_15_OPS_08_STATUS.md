# Batch 15 OPS 08 Status - Extended Observation and Restore Readiness

## Scope

BATCH-15-OPS-08 is a docs/evidence-only operations batch for:

- extended low-frequency public staging observation;
- Render managed PostgreSQL restore-drill operator approval readiness;
- backup retention, RPO, and RTO owner decision gates;
- production blocker closure roadmap;
- continued production-ready `no` posture.

No application code, models, migrations, templates, workflows, dependencies,
Render settings, external providers, alert routes, or error-reporting SDKs were
changed.

Production-ready status:

```text
no
```

## Branch And Base

Branch:

```text
codex/batch-15-ops-08-extended-observation-restore-readiness
```

Base commit:

```text
bb3e2ec13b934b582cdf175e20d80248f019a089
```

Final commit reporting:

```text
reported in the final response and PR after commit creation
```

## Inspected Files

Required files inspected:

- `.github/workflows/django.yml`
- `.github/workflows/dependency-audit.yml`
- `.github/workflows/staging-uptime.yml`
- `docs/BATCH_15_OPS_01_STATUS.md`
- `docs/BATCH_15_OPS_02_STATUS.md`
- `docs/BATCH_15_OPS_03_STATUS.md`
- `docs/BATCH_15_OPS_04_STATUS.md`
- `docs/BATCH_15_OPS_05_STATUS.md`
- `docs/BATCH_15_OPS_06_STATUS.md`
- `docs/BATCH_15_OPS_07_STATUS.md`
- `docs/OPERATIONS_BACKUP_RESTORE_PLAN.md`
- `docs/SYNTHETIC_RESTORE_DRILL_EVIDENCE.md`
- `docs/OPERATIONS_MONITORING_ALERTING_PLAN.md`
- `docs/OPERATIONS_SIGNAL_MATRIX.md`
- `docs/STAGING_UPTIME_LATENCY_MONITORING_EVIDENCE.md`
- `docs/MONITORING_ALERTING_READINESS.md`
- `docs/DEPENDENCY_AUDIT_WORKFLOW_EVIDENCE.md`
- `docs/DEPENDENCY_SECURITY_READINESS.md`
- `docs/INCIDENT_RESPONSE_RUNBOOK.md`
- `docs/SECURITY_REGRESSION_CHECKLIST.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/RELEASE_CHECKLIST.md`

## Validation Commands

Validation was run locally during this batch before final evidence/status
completion. Local validation used:

```text
DJANGO_SETTINGS_MODULE=config.settings.dev
```

The explicit dev settings module was required for this local checkout, matching
earlier batch evidence.

| Command | Result |
| --- | --- |
| `python --version` | Exit 0; Python 3.14.2. |
| `python -m pip --version` | Exit 0; pip 26.1.2 for Python 3.14. |
| `python manage.py check` | Exit 0; no system check issues. |
| `python manage.py makemigrations --check --dry-run` | Exit 0; no changes detected. |
| `python manage.py deployment_smoke` | Exit 0; 16 pass, 4 expected local warnings, 0 failures, 0 strict blockers. |
| `python manage.py deployment_smoke --strict` | Exit 0; 16 pass, 4 expected local warnings, 0 failures, 0 strict blockers. |
| `python manage.py production_settings_report` | Exit 0; safe categories only; local dev showed SQLite/LocMem and local HTTPS warnings. |
| `python manage.py project_status_report` | Exit 0; safe counts/categories only; patients 0 and appointments 0 in local dev data. |
| `python manage.py test` | Exit 0; 246 tests ran, OK. |
| `python -m pip check` | Exit 0; no broken requirements found. |
| `pip-audit --version` | Exit 0; pip-audit 2.10.1. |
| `pip-audit -r requirements.txt --progress-spinner off` | Exit 0; no known vulnerabilities found at scan time; emitted a Windows temp-path warning from the audit environment. |

Expected local warnings:

- `DEBUG=True`;
- SQLite active locally;
- LocMem cache active locally;
- HTTPS redirect disabled locally.

These warnings remain unacceptable for production launch.

## Extended Staging Observation Summary

Status:

```text
complete
```

Evidence document:

- `docs/EXTENDED_STAGING_OBSERVATION_EVIDENCE.md`

The final observation used only:

- `GET /health/`
- `GET /`

It recorded only status, `time_total`, final URL, local timestamp, and curl
exit code. Response bodies were discarded.

Final observation summary:

- 8 rounds completed from 2026-07-13 13:52:46 +03:00 through
  2026-07-13 15:37:51 +03:00;
- 16 checks returned HTTP 200 with curl exit code 0;
- `/health/` was severe in rounds 1 and 3, slow in rounds 5 and 7, and fast in
  rounds 2, 4, 6, and 8;
- `/health/` ranged from 0.312925 seconds to 32.762653 seconds;
- `/` was fast in all 8 rounds and ranged from 0.159444 seconds to 0.995978
  seconds;
- the earlier interrupted observation was preserved as recovery context and
  was not used to fill the final 8-round table.

## Render Managed PostgreSQL Restore-Drill Readiness

Status:

```text
operator approval pack created; real managed restore not executed
```

New pack:

- `docs/RENDER_MANAGED_POSTGRES_RESTORE_DRILL_OPERATOR_PACK.md`

The pack documents owner approvals, secret boundaries, patient-data
boundaries, allowed/forbidden evidence, pre-drill checklist, execution roles,
isolation model, backup source requirements, restore target requirements,
verification categories, rollback/cleanup, incident criteria, and acceptance
criteria.

No Render managed PostgreSQL restore drill was executed in this batch.

## Backup Retention, RPO, And RTO Approval Status

Status:

```text
decision pack created; no owner commitment approved
```

New decision pack:

- `docs/BACKUP_RPO_RTO_APPROVAL_DECISION_PACK.md`

No backup retention, RPO, or RTO commitment is approved until owner signs off.

## Production Blocker Closure Roadmap Summary

Status:

```text
roadmap created; blockers remain open
```

New roadmap:

- `docs/PRODUCTION_BLOCKER_CLOSURE_ROADMAP.md`

The roadmap maps current evidence, blocker status, next action, owner role,
risk if skipped, safe evidence, forbidden evidence/data, dependency ordering,
and whether Codex can close the item without external credentials.

## What Was Not Changed

This batch did not:

- change app code;
- change models;
- add migrations;
- change templates;
- change workflows;
- change dependencies;
- generate lockfiles;
- change Render settings;
- use Render credentials;
- open Render shell;
- run real managed backup or restore commands;
- submit booking POSTs;
- create patient data;
- access private/admin/staff/patient endpoints;
- configure external monitoring providers;
- configure alert destinations;
- add Sentry or any external SDK;
- add WhatsApp, uploads, medical records, payments, AI, diagnosis, triage, or
  treatment automation.

## Remaining Blockers

Production launch remains blocked by at least:

- intermittent severe staging latency remains unresolved; the final OPS-08
  observation recorded severe `/health/` latency in rounds 1 and 3 and slow
  `/health/` latency in rounds 5 and 7;
- no external monitoring provider is configured;
- no alert routing is configured or tested;
- no privacy-safe error-reporting provider is configured;
- no private provider-connected readiness monitoring exists;
- no Render managed PostgreSQL restore drill has been completed;
- backup retention, RPO, and RTO remain unapproved;
- no backup success/failure alert route is configured;
- no legal/privacy approval is recorded;
- no load/concurrency validation exists;
- no production DNS/TLS/custom-domain evidence exists;
- no named owner/backup owner is recorded where required;
- dependency response owner, GitHub alert settings, and lockfile/hash decisions
  remain incomplete;
- dashboard/admin polish remains partial if the owner treats it as
  launch-blocking.

## Safety Confirmation

This batch records only safe documentation and public GET metadata.

It does not record response bodies, cookies, session identifiers, CSRF token
values, full logs, provider environment values, connection strings, database
dumps, backup files, private keys, secret values, real patient data, patient
names, patient emails, patient phone numbers, appointment details, or medical
data.

Policy/category labels may appear in safety rules, but no secret values or
patient data are recorded.

## Final Readiness

Production-ready remains:

```text
no
```
