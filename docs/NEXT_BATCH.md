# Next Batch: Final Product Completion Track

This document replaces the stale foundation-stage next-batch note. The project
is past the initial foundation stage. After Batch 14, the current track is
final product completion and professional delivery readiness.

## Current Direction

- Final Product Completion Track is now the active planning track.
- DEMO_TRACK is no longer the project priority.
- The project must continue toward a highly professional, smooth, comfortable,
  secure, production-ready clinic system.
- Synthetic demo data and seed commands may remain only for local
  validation/testing. They are not the delivery goal.
- Batch 11 completed repository-local restricted staging validation operations.
- Batch 11 reported 246 tests passing.
- The project is not production launched.
- Real Render restricted staging is now functionally reachable for bounded
  public GET evidence, HTTP-to-HTTPS HEAD redirects, and basic home-page static
  asset delivery, but full production-like staging validation remains
  incomplete.
- Legal/privacy approval remains blocked.
- WhatsApp, uploads, medical records, and payments remain outside the current
  implemented scope.
- Batch 12 recorded the final product completion track, dashboard-managed
  configuration principle, and authorized showcase requirements.
- Batch 13 produced final UX/product-flow specifications and design handoff
  requirements. Batch 13 did not create Figma work, visual design, application
  code, templates, CSS, JavaScript, models, migrations, settings, deployment,
  or external infrastructure.
- Batch 14 performed local/provisional restricted-staging validation evidence
  only. Local checks and tests passed, but real restricted staging
  infrastructure, PostgreSQL, Redis/shared cache, HTTPS, and reverse proxy
  validation were not provided or validated. Batch 14 did not create
  application code, deployment, secrets, external infrastructure, real patient
  data, or launch readiness.
- Batch 14B ran the repository-approved local Docker PostgreSQL/Redis service
  harness with synthetic local-only data. Docker Desktop and WSL2 were
  available, local PostgreSQL/Redis services started, migrations and smoke
  checks reached PostgreSQL and Redis, and Redis-backed booking/patient portal
  app tests passed. PostgreSQL-backed booking/patient portal/full-suite tests
  failed on a nullable outer-join `select_for_update()` PostgreSQL blocker, so
  local Docker PostgreSQL/Redis validation did not pass overall. Batch 14B did
  not create application code, settings changes, dependency-file changes,
  deployment, secrets, external infrastructure, real patient data, or launch
  readiness.
- Batch 14B-FIX-01 fixed the nullable outer-join PostgreSQL locking blocker in
  staff appointment operations and patient portal appointment linking, then
  reran the local Docker PostgreSQL/Redis validation path. Default local
  SQLite/LocMem validation passed; local Docker PostgreSQL-backed booking,
  patient portal, and full-suite tests passed; local Docker Redis-backed
  booking, patient portal, and full-suite tests passed; combined local Docker
  PostgreSQL+Redis booking, patient portal, and full-suite tests passed. This
  remains local Docker validation only and does not claim real restricted
  staging, HTTPS/proxy/CSRF-origin, production, backup/restore, monitoring,
  legal/privacy, Redis multi-process/outage, or load/concurrency readiness.
- Batch 14C-PREP-01 prepared manual Render restricted staging prerequisites by
  adding a production WSGI server dependency, WhiteNoise static serving support,
  and Render staging setup documentation. It did not deploy, create Render
  services, add `render.yaml`, add product features, use secrets, or validate
  real staging.
- Batch 14C-VALIDATE-01 recorded sanitized evidence that the real Render
  restricted staging service is externally reachable: `/health/`, `/`,
  `/book/`, and `/en/book/` returned HTTP 200. This validates functional
  restricted staging for public GET reachability only. It does not approve
  production launch, legal/privacy readiness, backup/restore readiness,
  monitoring readiness, load/concurrency readiness, shared-cache
  multi-process/outage readiness, or future product areas.
- Batch 14C-VALIDATE-02 recorded deeper sanitized public staging evidence:
  `/health/`, `/`, `/book/`, and `/en/book/` still returned HTTP 200 over
  HTTPS; HTTP HEAD checks redirected those paths to HTTPS; home-page static
  assets returned HTTP 200; public security headers were recorded; anonymous
  portal login/register forms rendered CSRF inputs and set a secure CSRF cookie
  over HTTPS. It did not submit booking POSTs, create patient data, run Render
  shell commands, fetch full Render logs, prove managed PostgreSQL/Redis
  runtime behavior, or approve launch readiness.
- Batch 15-OPS-01 created production-oriented backup/restore and
  monitoring/alerting readiness plans. It documented PostgreSQL backup
  expectations, Redis non-authoritative recovery boundaries, current media and
  upload backup boundaries, synthetic-only restore drill procedure,
  post-restore verification, rollback boundaries, owner checklist, frequency
  recommendations, retention/deletion considerations, uptime checks for
  `/health/` and `/`, latency thresholds including an observed about 32.5
  second `/health/` response, error-rate monitoring, deploy/database/cache
  alerts, privacy-safe error reporting, alert routing, severity levels,
  incident response, and post-incident review. It did not execute a restore
  drill, configure monitoring, configure alert routing, add credentials, add
  dependencies, change Render settings, or approve launch readiness.
- Batch 15-OPS-02 executed a synthetic-only local PostgreSQL logical
  backup/restore drill using the repository-approved local Docker service
  harness. It applied migrations, seeded only public/demo setup data, dumped a
  local synthetic source database, restored it into a separate local
  restore-test database, verified migration state, smoke checks, safe reports,
  safe row counts, and the 246-test suite, then removed the generated artifact
  and local drill databases. This is local restore-procedure evidence only. It
  does not prove real Render managed PostgreSQL restore behavior, backup
  retention, RPO, RTO, monitoring, alert routing, legal/privacy approval, or
  production readiness.
- Batch 15-OPS-03 added lightweight repository-native staging uptime and
  latency evidence. A GitHub Actions workflow now checks the public Render
  restricted staging `/health/` and `/` endpoints by safe GET only, with manual
  dispatch, low-frequency scheduling, `curl` status/time/final-URL capture,
  slow-response warnings, and a hard staging latency threshold. Manual
  PowerShell verification commands and recent latency observations are
  documented. This does not configure a full monitoring provider, alert
  routing, privacy-safe error reporting, Render settings, or production
  readiness.
- Batch 15-OPS-04 documented dependency inventory, safe local baseline,
  unavailable advisory scanners, unavailable GitHub vulnerability/Dependabot
  alerts, response ownership roles, severity handling, and update cadence. It
  did not produce a complete advisory-backed scan.
- Batch 15-OPS-05 added repository-supported `pip-audit` dependency scanning.
  Local baseline commands, the full 246-test suite, and `python -m pip check`
  passed under local development settings. `pip-audit 2.10.1` scanned
  `requirements.txt` and returned no known vulnerabilities at scan time. A
  dedicated `Dependency audit` GitHub Actions workflow now runs on pull
  requests, manual dispatch, and a low-frequency weekly schedule. This does
  not guarantee security, upgrade dependencies, generate a lockfile, enable
  GitHub security settings, change Render settings, approve a named response
  owner, or approve production launch readiness.
- Batch 15-OPS-06 documented monitoring provider readiness, alert-routing
  readiness, privacy-safe error-reporting readiness, and the operations signal
  matrix. Safe public staging GET spot checks returned HTTP 200 for
  `/health/` and `/`, but both responses exceeded 30 seconds and remain severe
  staging latency evidence. This does not configure a monitoring provider,
  route alerts, add error reporting, change Render settings, run a Render
  managed PostgreSQL restore drill, or approve production launch readiness.
- Batch 15-OPS-07 documented staging latency evidence and mitigation decision
  gates. It reviewed OPS-03 and OPS-06 latency evidence, inspected the staging
  uptime workflow, and ran four bounded rounds of safe public GET checks for
  `/health/` and `/` only. All eight checks returned HTTP 200 in under `0.25`
  seconds with response bodies discarded. This reduces evidence of persistent
  latency during that window, but it does not prove root cause, configure
  monitoring, route alerts, change Render settings, or approve production
  launch readiness.
- Batch 15-OPS-08 documented extended low-frequency public staging observation
  evidence, a Render managed PostgreSQL restore-drill operator approval pack, a
  backup retention/RPO/RTO approval decision pack, and a production blocker
  closure roadmap. The observation recorded intermittent slow/severe
  `/health/` latency while `/` stayed fast. It did not execute a managed
  restore, configure monitoring, route alerts, approve retention/RPO/RTO,
  change Render settings, change app code, submit POSTs, record response
  bodies, use secrets, or use patient data.

## Batch 14 Result

Batch 14 result:

```text
Local/provisional validation completed; real restricted staging validation
blocked.
```

Evidence added:

- `docs/BATCH_14_STATUS.md`
- `docs/RESTRICTED_STAGING_VALIDATION_EVIDENCE.md`
- `docs/POSTGRESQL_REDIS_VALIDATION_EVIDENCE.md`
- `docs/HTTPS_PROXY_CSRF_VALIDATION_EVIDENCE.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`

Key conclusion:

- local Django checks, smoke commands, settings reports, route/status reports,
  and 246 tests passed in the local development environment;
- the strict staging script failed the environment contract because real
  staging variables were missing;
- Docker, `docker compose`, `psql`, `redis-cli`, and Bash were unavailable in
  the local shell;
- production settings correctly rejected SQLite and LocMemCache when tested
  with synthetic local-only production variables;
- real PostgreSQL, Redis/shared cache, HTTPS, reverse proxy, host, and CSRF
  behavior remains unproven.

## Batch 14B Result

Batch 14B result:

```text
Local Docker PostgreSQL/Redis validation ran; PostgreSQL validation failed.
```

Evidence added:

- `docs/BATCH_14B_STATUS.md`
- `docs/LOCAL_DOCKER_POSTGRES_REDIS_VALIDATION_EVIDENCE.md`

Evidence updated:

- `docs/POSTGRESQL_REDIS_VALIDATION_EVIDENCE.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`

Key conclusion:

- Docker Desktop and WSL2 are available locally;
- the existing local-only Docker service harness starts PostgreSQL and Redis;
- PostgreSQL migrations applied successfully in the local Docker database;
- combined PostgreSQL+Redis smoke/report commands can reach both services
  under `config.settings.dev`;
- Redis-backed booking and patient portal app tests passed on SQLite;
- PostgreSQL-backed booking, patient portal, and full-suite tests failed with
  `FOR UPDATE cannot be applied to the nullable side of an outer join`;
- full Redis-enabled suite has one expected environment-default failure because
  a core test asserts local default cache is LocMem;
- no real restricted staging, HTTPS/proxy/CSRF-origin, backup/restore,
  monitoring, legal/privacy, or load/concurrency validation is complete.

## Batch 14B-FIX-01 Result

Batch 14B-FIX-01 result:

```text
Local Docker PostgreSQL/Redis validation now passes for the current bounded test/smoke/report scope.
```

What changed:

- staff appointment lock query now locks only the base appointment row with
  `select_for_update(of=("self",))`;
- patient appointment linking lock query now locks appointment and patient rows
  with `select_for_update(of=("self", "patient"))`;
- the local default-cache test was clarified so default LocMem behavior is
  asserted when no cache override is configured, while documented Redis override
  validation can run the full suite.

Why dashboard implementation still remains deferred:

- the current booking and portal flows already create and protect operational
  patient/appointment data;
- local Docker validation is now healthier, but real restricted staging,
  HTTPS/proxy, CSRF-origin, secure-cookie, backup/restore, monitoring,
  legal/privacy, Redis multi-process/outage, and load/concurrency evidence
  remain incomplete;
- dashboard implementation would expand the staff/admin surface before the
  current bounded system has passed real restricted staging validation.

The next recommended validation batch at that time was:

```text
Batch 14C-VALIDATE-01: real restricted Render HTTPS/proxy/staging-host validation
```

Batch 14C-VALIDATE-01 has now recorded bounded public GET evidence from the
real Render staging host. Deeper staging runtime, browser security, managed
database/cache, backup/restore, monitoring, legal/privacy, load/concurrency,
and shared-cache outage/multi-process validation remain future work.

## Batch 14C-PREP-01 Result

Batch 14C-PREP-01 result:

```text
Render restricted staging prerequisites prepared; real staging remained unvalidated at that point.
```

What changed:

- `gunicorn` is declared for the Render Python web service WSGI process.
- `whitenoise` is declared and configured immediately after
  `SecurityMiddleware`.
- Static files use WhiteNoise compressed storage through Django's `STORAGES`
  setting.
- `docs/RENDER_STAGING_SETUP.md` documents manual Render setup commands,
  environment variables, region/internal-URL expectations, migration handling,
  and validation commands.
- `docs/STAGING_ENVIRONMENT_CONTRACT.md` now includes the exact Render staging
  environment variable shape.

What did not happen:

- no Render deployment;
- no Render service creation;
- no `render.yaml`;
- no secrets, committed env files, production credentials, or real patient
  data;
- no models, migrations, templates, CSS, JavaScript, dashboard code, booking
  behavior changes, patient portal behavior changes, Docker changes, or CI
  changes.

## Batch 14C-VALIDATE-01 Result

Batch 14C-VALIDATE-01 result:

```text
Functional restricted Render staging public GET evidence recorded; production launch remains blocked.
```

Evidence added:

- `docs/BATCH_14C_VALIDATE_01_STATUS.md`

Evidence updated:

- `docs/RENDER_STAGING_SETUP.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`

Key conclusion:

- local baseline commands passed without staging secrets;
- the full local test suite passed: 246 tests, OK;
- the real Render staging web service returned HTTP 200 for `/health/` and
  `/`;
- public booking entry pages returned HTTP 200 for `/book/` and `/en/book/`
  by GET only;
- no booking POST was submitted and no patient or appointment data was
  created;
- no Render logs, environment dumps, credentials, connection strings, or
  patient-identifying data were documented;
- full browser security, managed database/cache command evidence,
  backup/restore, monitoring, legal/privacy, load/concurrency, and
  shared-cache outage/multi-process readiness remain incomplete.

## Batch 14C-VALIDATE-02 Result

Batch 14C-VALIDATE-02 result:

```text
Deeper restricted Render staging public evidence recorded; production launch remains blocked.
```

Evidence added:

- `docs/BATCH_14C_VALIDATE_02_STATUS.md`

Evidence updated:

- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`

Key conclusion:

- local baseline commands passed without staging secrets;
- the full local test suite passed: 246 tests, OK;
- required public staging GET checks returned HTTP 200 for `/health/`, `/`,
  `/book/`, and `/en/book/`;
- HTTP HEAD checks redirected the same public HTTP paths to HTTPS;
- four same-origin home-page static assets returned HTTP 200;
- public responses showed `X-Content-Type-Options=nosniff`,
  `Referrer-Policy=same-origin`, and
  `Cross-Origin-Opener-Policy=same-origin`;
- HSTS and CSP were absent on checked public responses;
- anonymous portal login/register forms rendered CSRF inputs and set a secure
  CSRF cookie with SameSite present over HTTPS;
- booking confirmation form and booking success no-cache behavior remain
  incomplete because no safe public slot/success path was available without
  creating data;
- in-app browser automation was unavailable in this session;
- managed PostgreSQL/Redis runtime commands, backup/restore, monitoring,
  legal/privacy, load/concurrency, sanitized log review, and production launch
  readiness remain incomplete or blocked.

## Batch 15-OPS-01 Result

Batch 15-OPS-01 result:

```text
Backup/restore and monitoring/alerting readiness plans documented; production launch remains blocked.
```

Evidence added:

- `docs/BATCH_15_OPS_01_STATUS.md`
- `docs/OPERATIONS_BACKUP_RESTORE_PLAN.md`
- `docs/OPERATIONS_MONITORING_ALERTING_PLAN.md`

Evidence updated:

- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`

Key conclusion:

- local baseline commands passed without staging secrets;
- the full local test suite passed: 246 tests, OK;
- backup/restore plan now defines PostgreSQL backup expectations, Redis
  non-authoritative recovery boundaries, current media/private upload status,
  synthetic-only restore drill procedure, post-restore verification, rollback
  boundaries, owner checklist, frequency recommendations, and retention/
  deletion considerations;
- monitoring/alerting plan now defines uptime checks for `/health/` and `/`,
  private readiness monitoring, latency thresholds including an observed about
  32.5 second `/health/` response, error-rate monitoring, deploy failure
  monitoring, database/cache monitoring, privacy-safe error reporting, alert
  routing, escalation, severity levels, incident response, and post-incident
  review;
- no backup was created;
- no restore was executed;
- no monitoring provider or account was configured;
- no alert routing or privacy-safe error reporting was configured;
- legal/privacy approval, load/concurrency validation, direct managed
  PostgreSQL/Redis runtime evidence, Redis outage/multi-process evidence, and
  production launch readiness remain incomplete or blocked.

## Batch 15-OPS-02 Result

Batch 15-OPS-02 result:

```text
Local synthetic PostgreSQL restore drill passed; production launch remains blocked.
```

Evidence added:

- `docs/BATCH_15_OPS_02_STATUS.md`
- `docs/SYNTHETIC_RESTORE_DRILL_EVIDENCE.md`

Evidence updated:

- `docs/OPERATIONS_BACKUP_RESTORE_PLAN.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`

Key conclusion:

- local baseline commands passed without staging secrets;
- the full local default suite passed: 246 tests, OK;
- Docker Desktop was started locally after the daemon was initially unavailable;
- local Docker PostgreSQL and Redis services became healthy;
- one local synthetic source database and one separate local restore-test
  database were used;
- migrations applied to the source database;
- `seed_public_content` and `seed_booking_demo` created public/demo setup data
  only;
- safe source and restored counts matched: 1 clinic profile, 1 doctor, 9 visit
  types, 5 doctor schedules, 7 system settings, 0 patients, and 0 appointments;
- a local custom-format PostgreSQL logical dump was created inside the local
  PostgreSQL container and restored into the restore-test database;
- restored migration checks, Django checks, smoke checks, safe reports, safe
  counts, and the 246-test suite passed;
- the generated dump artifact and local drill databases were removed;
- no active Render staging resource was modified;
- no real patient data was used;
- no generated backup artifact or credential was committed;
- real Render managed PostgreSQL restore, monitoring provider setup, alert
  routing, backup retention/RPO/RTO approval, legal/privacy approval, load
  validation, and production launch readiness remain incomplete or blocked.

## Batch 15-OPS-03 Result

Batch 15-OPS-03 result:

```text
Lightweight repository-native staging uptime and latency evidence added;
production launch remains blocked.
```

Evidence added:

- `.github/workflows/staging-uptime.yml`
- `docs/BATCH_15_OPS_03_STATUS.md`
- `docs/STAGING_UPTIME_LATENCY_MONITORING_EVIDENCE.md`

Evidence updated:

- `docs/OPERATIONS_MONITORING_ALERTING_PLAN.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`

Key conclusion:

- local baseline commands passed without staging secrets;
- the full local default suite passed: 246 tests, OK;
- the existing Django CI workflow was left intact;
- a new low-frequency GitHub Actions workflow checks public staging
  `/health/` and `/` with `curl` only;
- the workflow records HTTP status, total response time, and final URL only;
- response bodies are not printed;
- non-200 status, timeout, transport failure, or response time over 60 seconds
  fails the workflow;
- response time over 10 seconds produces a warning;
- manual PowerShell verification commands are documented for `/health/` and
  `/`;
- recent staging examples are documented: `/health/` around 32.5 seconds,
  22.4 seconds, and 42.5 seconds; `/` around 0.65 to 0.80 seconds;
- no booking POSTs were submitted;
- no private, staff, admin, patient, or readiness endpoints were called;
- no active Render staging setting was modified;
- no real patient data was used;
- full monitoring provider setup, alert routing, privacy-safe error reporting,
  Render managed PostgreSQL restore, backup retention/RPO/RTO approval,
  legal/privacy approval, load validation, and production launch readiness
  remain incomplete or blocked.

## Batch 15-OPS-04 Result

Batch 15-OPS-04 result:

```text
Dependency vulnerability scan attempt and response ownership documented;
complete advisory-backed scan remains blocked.
```

Evidence added:

- `docs/BATCH_15_OPS_04_STATUS.md`
- `docs/DEPENDENCY_VULNERABILITY_SCAN_EVIDENCE.md`

Evidence updated:

- `docs/DEPENDENCY_SECURITY_READINESS.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/RELEASE_CHECKLIST.md`

Key conclusion:

- local baseline commands passed without staging secrets;
- the full local default suite passed: 246 tests, OK;
- `python -m pip check` passed with no broken requirements;
- local `python manage.py check --deploy` and
  `python manage.py deployment_smoke --strict` ran under development settings
  and produced only expected local-development warnings;
- `requirements.txt` is the only dependency manifest found in the repository;
- no Python lockfile is currently committed;
- Dependabot is already configured weekly for Python `pip` and GitHub Actions;
- no dependency package was upgraded;
- no scanner was installed;
- `pip-audit`, `safety`, `osv-scanner`, `trivy`, and `grype` were not
  available locally;
- GitHub vulnerability alerts were disabled for the repository;
- GitHub Dependabot alerts were disabled for the repository;
- no GitHub repository security settings were changed;
- role-based response ownership, severity handling, and update cadence are
  now documented;
- no named human dependency response owner or backup owner is recorded yet;
- no real patient data, secrets, Render settings, dependency files, lockfiles,
  application code, or CI workflows were changed.

## Batch 15-OPS-05 Result

Batch 15-OPS-05 result:

```text
Advisory-backed dependency scanning added; production launch remains blocked.
```

Evidence added:

- `.github/workflows/dependency-audit.yml`
- `docs/BATCH_15_OPS_05_STATUS.md`
- `docs/DEPENDENCY_AUDIT_WORKFLOW_EVIDENCE.md`

Evidence updated:

- `docs/DEPENDENCY_SECURITY_READINESS.md`
- `docs/DEPENDENCY_VULNERABILITY_SCAN_EVIDENCE.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/RELEASE_CHECKLIST.md`

Key conclusion:

- local baseline commands passed without staging secrets under
  `config.settings.dev`;
- the full local default suite passed: 246 tests, OK;
- `python -m pip check` passed with no broken requirements;
- `pip-audit 2.10.1` is available in the local workstation environment;
- `pip-audit -r requirements.txt --progress-spinner off` completed
  successfully;
- the scan result was `No known vulnerabilities found`;
- this means no known advisories were returned by `pip-audit` at scan time,
  not a guarantee of security;
- the `Dependency audit` workflow installs `pip-audit` as CI tooling only and
  scans `requirements.txt`;
- no dependency package was upgraded;
- no lockfile was generated;
- no Render setting was changed;
- no GitHub repository security setting was changed;
- no real patient data, secrets, response bodies, logs, application code,
  models, migrations, templates, or product behavior were changed;
- named dependency response owner approval, GitHub alert settings decision,
  lockfile/hash workflow decision, full monitoring, alert routing,
  privacy-safe error reporting, Render managed PostgreSQL restore drill,
  legal/privacy approval, load/concurrency validation, and production hosting
  remain incomplete.

## Batch 15-OPS-06 Result

Batch 15-OPS-06 result:

```text
Monitoring provider, alert-routing, privacy-safe error-reporting, and signal
matrix readiness documented; production launch remains blocked.
```

Evidence added:

- `docs/BATCH_15_OPS_06_STATUS.md`
- `docs/OPERATIONS_SIGNAL_MATRIX.md`

Evidence updated:

- `docs/OPERATIONS_MONITORING_ALERTING_PLAN.md`
- `docs/STAGING_UPTIME_LATENCY_MONITORING_EVIDENCE.md`
- `docs/MONITORING_ALERTING_READINESS.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/SECURITY_REGRESSION_CHECKLIST.md`

Key conclusion:

- pre-change local baseline evidence was supplied under
  `config.settings.dev`;
- pre-change full local default suite passed: 246 tests, OK;
- pre-change `python -m pip check` passed;
- pre-change `pip-audit 2.10.1` scanned `requirements.txt` and returned no
  known vulnerabilities at scan time;
- safe public staging GET checks discarded response bodies and printed only
  HTTP status, total response time, and final URL;
- `GET /health/` returned HTTP 200 in `32.828721` seconds;
- `GET /` returned HTTP 200 in `31.897716` seconds;
- both public staging spot checks are availability-positive but severe latency
  evidence;
- the operations signal matrix now maps liveness, latency, private readiness,
  HTTP errors, deploy failures, PostgreSQL, Redis, backups, booking/portal
  abuse, dependency security, privacy-safe error reporting, and incident
  response signals to current evidence and blockers;
- monitoring provider readiness remains incomplete;
- alert routing readiness remains incomplete;
- privacy-safe error reporting remains incomplete;
- no app code, migrations, dependencies, workflows, Render settings, external
  provider configuration, secrets, patient data, logs, or response bodies were
  changed or committed;
- production launch remains blocked.

## Batch 15-OPS-07 Result

Batch 15-OPS-07 result:

```text
Staging latency evidence and mitigation decision gates documented; production
launch remains blocked.
```

Evidence added:

- `docs/BATCH_15_OPS_07_STATUS.md`

Evidence updated:

- `docs/STAGING_UPTIME_LATENCY_MONITORING_EVIDENCE.md`
- `docs/OPERATIONS_MONITORING_ALERTING_PLAN.md`
- `docs/OPERATIONS_SIGNAL_MATRIX.md`
- `docs/MONITORING_ALERTING_READINESS.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/RELEASE_CHECKLIST.md`

Key conclusion:

- OPS-03 and OPS-06 severe staging latency evidence remains valid historical
  evidence;
- the existing staging uptime workflow remains safe, low frequency, and limited
  to public GET `/health/` and `/` checks;
- safe public GET checks in BATCH-15-OPS-07 discarded response bodies and
  printed only HTTP status, total response time, and final URL;
- four bounded rounds were run with 20-second pauses;
- `GET /health/` returned HTTP 200 in `0.243988`, `0.103777`, `0.111525`, and
  `0.108991` seconds;
- `GET /` returned HTTP 200 in `0.123764`, `0.116320`, `0.106962`, and
  `0.169094` seconds;
- the BATCH-15-OPS-07 check window did not show persistent latency;
- likely causes remain unproven, with cold start, platform/runtime delay,
  deploy/restart behavior, queueing, or network path delay still plausible;
- production launch remains blocked until owner/operator latency mitigation,
  monitoring provider, alert routing, private readiness, backup/restore,
  legal/privacy, load/concurrency, and production infrastructure decisions are
  completed.

## Batch 15-OPS-08 Result

Batch 15-OPS-08 result:

```text
Extended staging observation, restore-drill operator pack, backup/RPO/RTO
decision pack, and production blocker closure roadmap documented; production
launch remains blocked.
```

Evidence added:

- `docs/BATCH_15_OPS_08_STATUS.md`
- `docs/EXTENDED_STAGING_OBSERVATION_EVIDENCE.md`
- `docs/RENDER_MANAGED_POSTGRES_RESTORE_DRILL_OPERATOR_PACK.md`
- `docs/BACKUP_RPO_RTO_APPROVAL_DECISION_PACK.md`
- `docs/PRODUCTION_BLOCKER_CLOSURE_ROADMAP.md`

Evidence updated:

- `docs/OPERATIONS_BACKUP_RESTORE_PLAN.md`
- `docs/OPERATIONS_MONITORING_ALERTING_PLAN.md`
- `docs/OPERATIONS_SIGNAL_MATRIX.md`
- `docs/STAGING_UPTIME_LATENCY_MONITORING_EVIDENCE.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/SECURITY_REGRESSION_CHECKLIST.md`
- `docs/INCIDENT_RESPONSE_RUNBOOK.md`

Key conclusion:

- extended public staging observation evidence is now recorded for `/health/`
  and `/` using 8 low-frequency rounds;
- the evidence records status, total time, final URL, local timestamp, and curl
  exit code only;
- response bodies were discarded;
- all checks returned HTTP 200 with curl exit code 0, but `/health/` recorded
  severe latency in rounds 1 and 3 and slow latency in rounds 5 and 7 while
  `/` stayed fast in every round;
- Render managed PostgreSQL restore readiness is improved by an operator pack,
  but no real managed restore drill was executed;
- backup retention, RPO, and RTO are framed for owner approval, but no
  commitment is approved;
- the production blocker closure roadmap identifies owner roles, safe
  evidence, forbidden evidence, dependency ordering, and whether Codex can
  close each item without external credentials;
- production launch remains blocked until owner/operator latency, monitoring,
  alert routing, privacy-safe error reporting, restore drill, backup/RPO/RTO,
  legal/privacy, load/concurrency, dependency ownership, and production
  infrastructure decisions are completed.

Batch 14A remains a valid later planning-only option:

```text
Batch 14A: dashboard implementation planning/authorization
```

Use Batch 14A only if the owner explicitly pauses staging validation to plan
dashboard implementation scope. Do not start dashboard code in Batch 14A unless
a separate implementation batch authorizes it.

Must read before the next staging or operations batch:

- `README.md`
- `docs/UX_PRODUCT_FLOW_AUDIT.md`
- `docs/FINAL_UX_PRODUCT_FLOW_SPEC.md`
- `docs/PUBLIC_SITE_UX_SPEC.md`
- `docs/BOOKING_FLOW_UX_SPEC.md`
- `docs/DOCTOR_DASHBOARD_UX_SPEC.md`
- `docs/PATIENT_PORTAL_UX_SPEC.md`
- `docs/BILINGUAL_CONTENT_UX_STANDARD.md`
- `docs/MOBILE_ACCESSIBILITY_UX_CHECKLIST.md`
- `docs/BATCH_13_STATUS.md`
- `docs/FINAL_PRODUCT_COMPLETION_PLAN.md`
- `docs/FINAL_PRODUCT_QUALITY_STANDARD.md`
- `docs/DOCTOR_MANAGED_CONFIGURATION_STANDARD.md`
- `docs/AUTHORIZED_SHOWCASE_REQUIREMENTS.md`
- `docs/FIGMA_DESIGN_HANDOFF.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/ROUTE_ACCESS_MATRIX.md`
- `docs/DATA_EXPOSURE_MATRIX.md`
- `docs/LEGAL_PRIVACY_OPERATIONS.md`
- `docs/STAGING_VALIDATION_PLAN.md`
- `docs/STAGING_GAP_ANALYSIS.md`
- `docs/STAGING_ENVIRONMENT_CONTRACT.md`
- `docs/RENDER_STAGING_SETUP.md`
- `docs/POSTGRESQL_READINESS.md`
- `docs/REDIS_RATE_LIMIT_READINESS.md`
- `docs/SECURITY_REGRESSION_CHECKLIST.md`
- `docs/BATCH_14_STATUS.md`
- `docs/BATCH_14B_STATUS.md`
- `docs/BATCH_14B_FIX_01_STATUS.md`
- `docs/BATCH_14C_PREP_01_STATUS.md`
- `docs/BATCH_14C_VALIDATE_01_STATUS.md`
- `docs/BATCH_14C_VALIDATE_02_STATUS.md`
- `docs/BATCH_15_OPS_01_STATUS.md`
- `docs/BATCH_15_OPS_02_STATUS.md`
- `docs/BATCH_15_OPS_03_STATUS.md`
- `docs/BATCH_15_OPS_04_STATUS.md`
- `docs/OPERATIONS_BACKUP_RESTORE_PLAN.md`
- `docs/OPERATIONS_MONITORING_ALERTING_PLAN.md`
- `docs/DEPENDENCY_SECURITY_READINESS.md`
- `docs/BATCH_15_OPS_05_STATUS.md`
- `docs/SYNTHETIC_RESTORE_DRILL_EVIDENCE.md`
- `docs/STAGING_UPTIME_LATENCY_MONITORING_EVIDENCE.md`
- `docs/DEPENDENCY_AUDIT_WORKFLOW_EVIDENCE.md`
- `docs/DEPENDENCY_VULNERABILITY_SCAN_EVIDENCE.md`
- `docs/BATCH_15_OPS_06_STATUS.md`
- `docs/BATCH_15_OPS_07_STATUS.md`
- `docs/BATCH_15_OPS_08_STATUS.md`
- `docs/OPERATIONS_SIGNAL_MATRIX.md`
- `docs/EXTENDED_STAGING_OBSERVATION_EVIDENCE.md`
- `docs/RENDER_MANAGED_POSTGRES_RESTORE_DRILL_OPERATOR_PACK.md`
- `docs/BACKUP_RPO_RTO_APPROVAL_DECISION_PACK.md`
- `docs/PRODUCTION_BLOCKER_CLOSURE_ROADMAP.md`
- `docs/RESTRICTED_STAGING_VALIDATION_EVIDENCE.md`
- `docs/POSTGRESQL_REDIS_VALIDATION_EVIDENCE.md`
- `docs/LOCAL_DOCKER_POSTGRES_REDIS_VALIDATION_EVIDENCE.md`
- `docs/HTTPS_PROXY_CSRF_VALIDATION_EVIDENCE.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`

## Ordered Recommended Batches

1. Batch 14C-VALIDATE-03: complete operator-assisted Render runtime validation
   if safe access is available, including staging shell management commands,
   managed PostgreSQL/Redis command evidence, booking confirmation/browser
   checks with synthetic data only, and sanitized targeted log review.
2. Next operations follow-up: owner/operator Render latency mitigation and
   external monitoring/alert-routing setup for intermittent slow/severe
   `/health/` latency; then operator-approved Render managed PostgreSQL
   restore drill execution planning with synthetic data only.
3. Batch 15-OPS-09: dependency response owner approval, GitHub alert settings
   decision, and bounded-ranges versus lockfile/hash workflow decision.
4. Batch 14A: dashboard implementation planning/authorization, only if the
   owner explicitly chooses planning before dashboard code.
5. Batch 16: legal/privacy/account recovery and patient identity verification
   policy.
6. Batch 17: doctor dashboard workflow completion/polish.
7. Batch 18: patient portal completion/hardening.
8. Batch 19: WhatsApp limited integration design/implementation only after
   privacy gates.
9. Batch 20: approved cases/reviews/media showcase plus private publication
   rules.
10. Batch 21: release candidate hardening.

## Final Quality Goals

Future batches must move toward:

- a professional visual experience approved through Figma/design governance;
- smooth patient booking;
- a comfortable doctor/admin workflow;
- high-quality Arabic and English copy;
- mobile-first behavior;
- privacy and security by default;
- no real launch without staging, legal/privacy, backup/restore, monitoring,
  load, and security evidence.

## Stop Rules

Stop and report instead of continuing if:

- any code change seems needed during a documentation-only batch;
- visual changes are requested without Figma/design approval;
- implementation tries to skip staging, legal, or privacy gates;
- real patient data is requested or provided;
- patient media is requested for publication without explicit publication
  consent;
- WhatsApp, uploads, medical records, payments, deployment, secrets, external
  infrastructure, or dependency changes appear necessary in the same batch.
- Codex is asked to create Figma work, visual design, mockups, colors, spacing,
  typography, animations, shadows, borders, hover effects, or layout density
  without a human/owner-approved design handoff.
