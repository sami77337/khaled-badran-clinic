# Operations Signal Matrix

## Purpose

This matrix maps the operational signals required before production launch to
the current repository evidence, monitoring-provider readiness, alert-routing
readiness, and privacy-safe error-reporting status for Dr. Khaled Badran
Clinic.

This is a docs/evidence-only matrix. It does not configure providers, create
external accounts, route alerts, add SDKs, store credentials, change Render
settings, change application code, add migrations, submit forms, or approve
production launch.

Production-ready status:

```text
no
```

## Current Readiness Summary

Monitoring provider readiness:

```text
not configured; incomplete
```

Alert routing readiness:

```text
not configured; incomplete
```

Privacy-safe error reporting:

```text
not configured; incomplete
```

Operations signal coverage:

```text
documented, but not fully wired to providers or alerts
```

Governance decision packs:

```text
documented, but owner/provider/route decisions remain open
```

## Public Staging Spot Check Evidence

On `2026-07-05`, safe public GET checks were run against the existing Render
restricted staging host. Response bodies were discarded.

OPS-06 spot checks:

| Endpoint | HTTP status | Total time | Interpretation |
| --- | ---: | ---: | --- |
| `GET /health/` | 200 | `32.828721` seconds | Available, but severe staging latency. |
| `GET /` | 200 | `31.897716` seconds | Available, but severe staging latency. |

OPS-07 bounded repeated checks:

| Endpoint | HTTP status | Total time range | Interpretation |
| --- | ---: | ---: | --- |
| `GET /health/` | 200 | `0.103777` to `0.243988` seconds | Available and fast during the bounded repeated check window. |
| `GET /` | 200 | `0.106962` to `0.169094` seconds | Available and fast during the bounded repeated check window. |

BATCH-15-OPS-08 extended observation:

- evidence file: `docs/EXTENDED_STAGING_OBSERVATION_EVIDENCE.md`;
- method: 8 rounds, 15 minutes between rounds, public `GET /health/` and
  `GET /` only;
- result: all checks returned HTTP 200 with curl exit code 0;
- latency: `/health/` was severe in rounds 1 and 3, slow in rounds 5 and 7,
  and fast in rounds 2, 4, 6, and 8; `/` was fast in all rounds;
- recorded fields: round, local timestamp, endpoint label, HTTP status, total
  time, final URL, and curl exit code;
- no response bodies, private endpoints, booking POSTs, provider logs,
  credentials, Render settings changes, or alert-provider configuration.

These checks are public staging availability and latency observations only.
They do not prove private readiness, database health, cache health, provider
alerting, production uptime, or launch readiness.

## Batch 15-OPS-09 Governance Decision Packs

BATCH-15-OPS-09 adds decision-pack evidence for the provider and routing
decisions that this matrix depends on:

- `docs/OPERATIONS_OWNER_ASSIGNMENT_DECISION_PACK.md`
- `docs/MONITORING_PROVIDER_SELECTION_DECISION_PACK.md`
- `docs/ALERT_ROUTING_APPROVAL_AND_SYNTHETIC_TEST_PLAN.md`
- `docs/DEPENDENCY_SECURITY_GOVERNANCE_DECISION_PACK.md`
- `docs/OPS_GOVERNANCE_CLOSURE_MATRIX.md`

These documents define required roles, provider capabilities, synthetic alert
tests, safe evidence, forbidden evidence, Codex boundaries, and remaining
blockers. They do not configure a provider, route an alert, assign private
contacts, enable GitHub security settings, add error-reporting SDKs, or approve
production readiness.

## Signal Matrix

| Signal group | Required signal | Current repository support or evidence | Monitoring provider readiness | Alert routing readiness | Privacy-safe handling | Current status |
| --- | --- | --- | --- | --- | --- | --- |
| Public liveness | `GET /health/` status, final URL, latency | Endpoint exists; low-frequency GitHub Actions staging uptime workflow exists; manual GET evidence recorded. | External provider not configured. | No route configured. | No response bodies required. | Partial interim evidence. |
| Public home page | `GET /` status, final URL, latency | Public home page exists; workflow and manual GET evidence record safe metadata only. | External provider not configured. | No route configured. | No response bodies required. | Partial interim evidence. |
| Private readiness | `GET /health/ready/` through private/internal path | Endpoint exists and returns only safe status values; direct private provider path not validated. | Private monitoring path not configured. | No route configured. | No diagnostics or connection details should be emitted. | Incomplete. |
| Public latency | p95 and severe single-response latency | Thresholds documented; OPS-03/OPS-06 exceeded 30 seconds; OPS-07 repeated checks were fast. | Provider latency tracking not configured. | No slow-response alert route configured. | Store timing/status only. | Partial evidence; intermittent latency blocker remains. |
| HTTP 5xx rate | 5xx rate by environment and route group | Requirements documented; local tests pass by supplied evidence. | Provider dashboard not configured. | No 5xx alert route configured. | Do not include request bodies or patient identifiers. | Incomplete. |
| Request errors | Django request errors and exception classes | Console logging foundation exists. | Error aggregation not configured. | No error alert route configured. | Exception metadata must be scrubbed. | Incomplete. |
| Security warnings | Django security warnings, CSRF spikes, suspicious auth patterns | Requirements documented; regression checklist exists. | Provider/security dashboard not configured. | No security alert route configured. | Aggregate counts only; no raw tokens, cookies, or request bodies. | Incomplete. |
| Deploy failures | build, deploy, migration, crash/restart, smoke failure | Deploy validation commands and incident response expectations documented. | Render/provider alert evidence not recorded. | No deploy alert route tested. | No secret env dumps in alert payloads. | Incomplete. |
| PostgreSQL readiness | database connectivity, migration state, provider health, connection errors | Local Docker PostgreSQL validation and local synthetic restore drill exist; Render managed DB command evidence remains incomplete. | Provider DB alerting not configured. | No database alert route configured. | No database URLs, hostnames, usernames, or query payloads in alerts. | Incomplete. |
| Redis/shared cache | cache set/get/delete, service health, rate-limit backend behavior | Local Docker Redis validation exists; real staging multi-process/outage evidence remains incomplete. | Provider cache alerting not configured. | No cache alert route configured. | No cache URLs, raw phone numbers, public tokens, or raw IP identities. | Incomplete. |
| Backups | backup success, missing backup, restore drill failure | Backup/restore plan exists and local synthetic logical restore drill passed. | Render managed backup alert evidence not recorded. | No backup alert route configured. | Backup artifacts, dumps, and logs must stay out of Git. | Incomplete. |
| Booking abuse | booking POST rate, stale slot attempts, quota blocks, suspicious probing | Required aggregate signals documented; no provider dashboard exists. | Abuse monitoring not configured. | No abuse alert route configured. | Use aggregate counts and hashed identities where practical. | Incomplete. |
| Portal abuse | login failures, registration spikes, appointment-link failures, CSRF failures | Required aggregate signals documented; portal rate-limit foundations exist. | Abuse monitoring not configured. | No abuse alert route configured. | No raw phones, emails, passwords, or public tokens. | Incomplete. |
| Dependency security | dependency scan failures and advisories | `pip-audit` local/CI scanning added by BATCH-15-OPS-05. | GitHub/security alert settings still need owner decision if not enabled. | No named dependency owner route approved. | Scanner output should not include secrets or patient data. | Partial. |
| Privacy-safe error reporting | scrubbed exception/event reporting | Requirements documented. | Provider not selected or configured. | No event alert route tested. | Request bodies, cookies, auth headers, CSRF tokens, patient identifiers, and secrets must be scrubbed. | Incomplete. |
| Incident response | severity, owner, timeline, escalation, recovery checks | Incident response runbook and severity model exist. | Detection sources not fully wired. | No live escalation route tested. | Incident evidence containing sensitive data must stay outside Git. | Partial planning. |

OPS-09 updates the governance state for this matrix, but not the wired signal
state: monitoring provider readiness, alert routing readiness, privacy-safe
error reporting, dependency response ownership, and incident owner coverage
remain incomplete until owner-approved external decisions and tests occur.

## Provider Readiness Criteria

Monitoring provider readiness cannot be claimed until all of the following are
true:

- provider is selected and approved by the owner;
- provider account and environment are configured outside Git;
- public `/health/` and `/` checks run at approved frequency;
- private `/health/ready/` monitoring path is configured where possible;
- latency, uptime, 5xx, deploy, database, cache, backup, and abuse signal
  policies are configured or intentionally deferred with owner approval;
- alert payloads are reviewed for secret and patient-data safety;
- event retention and operator access are approved;
- a synthetic alert is sent and acknowledged through the approved route;
- no credentials or provider environment dumps are committed.

Current status:

```text
not ready
```

## Alert Routing Criteria

Alert routing readiness cannot be claimed until all of the following are true:

- primary technical operator is named and approved outside Git;
- backup technical operator is named and approved outside Git;
- project owner escalation route is approved;
- legal/privacy escalation route is approved;
- SEV-1 through SEV-4 routing behavior is documented in the provider;
- primary and backup routes are tested;
- route failure fallback is tested or documented;
- alert payload review confirms no secrets, patient data, request bodies, raw
  tokens, cookies, database URLs, cache URLs, private keys, or provider keys
  are included.

Current status:

```text
not ready
```

## Privacy-Safe Error Reporting Criteria

Privacy-safe error reporting readiness cannot be claimed until all of the
following are true:

- provider is selected and approved;
- request-body capture is disabled by default;
- cookies, authorization headers, CSRF tokens, session identifiers, public
  appointment tokens, phone numbers, emails unless explicitly approved, patient
  names, booking notes, medical content, database/cache URLs, secret values,
  and provider keys are scrubbed;
- access is limited to named operators;
- event retention is approved;
- a synthetic error event is reviewed before live activation;
- no DSN, API key, webhook URL, token, or provider environment dump is
  committed.

Current status:

```text
not ready
```

## Readiness Conclusions

| Area | Status | Reason |
| --- | --- | --- |
| Public staging availability | Partial | Latest safe GET checks returned HTTP 200 for `/health/` and `/`. |
| Public staging latency | Blocked | OPS-03 and OPS-06 documented intermittent severe responses over 30 seconds, post-PR operator evidence again showed severe `/health/` latency, and OPS-08 recorded severe `/health/` latency in rounds 1 and 3 plus slow `/health/` latency in rounds 5 and 7. Root cause and mitigation are still not approved. |
| Full monitoring provider | Incomplete | No external provider is selected, configured, or validated. |
| Alert routing | Incomplete | No primary or backup route is configured or tested. |
| Privacy-safe error reporting | Incomplete | No provider integration or scrubbed synthetic event exists. |
| Signal definitions | Documented | Required signal groups and privacy boundaries are now mapped. |
| Production launch | Blocked | Provider, alert routing, error reporting, backup/restore, legal/privacy, load, and production infrastructure blockers remain. |

## Remaining Required Operator Decisions

- Select and approve the monitoring provider.
- Approve public uptime and latency thresholds.
- Decide whether Render staging/production must use a non-sleeping or otherwise
  mitigated runtime class before launch.
- Approve private readiness monitoring path.
- Name primary and backup monitoring operators.
- Approve project-owner and legal/privacy escalation routes.
- Approve alert-channel provider and payload boundaries.
- Decide whether to enable privacy-safe error reporting and which provider to
  use.
- Approve event retention and operator access.
- Complete a synthetic alert test outside Git.
- Complete a scrubbed synthetic error-reporting event review outside Git.
- Complete a Render managed PostgreSQL restore drill with synthetic data only.
- Decide backup retention, RPO, and RTO.
- Close or owner-accept the production blocker roadmap before go/no-go.

## Safety Boundary

No secrets, tokens, connection strings, private keys, patient names, emails,
phone numbers, appointment details, medical data, database dumps, logs,
response bodies, cookies, request bodies, or provider environment values are
included in this matrix.

No Render setting, external provider, application code, migration, dependency
file, workflow, or route behavior was changed by this matrix.
