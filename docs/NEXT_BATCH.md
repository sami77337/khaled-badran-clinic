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
- Real staging infrastructure is not yet validated.
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
  asserted when `CACHE_URL` is absent, while documented Redis override
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

The next recommended validation batch is:

```text
Batch 14C: real restricted HTTPS/proxy/staging-host validation
```

Batch 14C should provision or provide a restricted, synthetic-data-only staging
environment; use `config.settings.prod` or a reviewed production-safe staging
wrapper; use PostgreSQL, Redis/shared cache, HTTPS, exact host/CSRF settings,
and reviewed proxy behavior; and archive safe evidence without secret values or
patient data.

Batch 14A remains a valid later planning-only option:

```text
Batch 14A: dashboard implementation planning/authorization
```

Use Batch 14A only if the owner explicitly pauses staging validation to plan
dashboard implementation scope. Do not start dashboard code in Batch 14A unless
a separate implementation batch authorizes it.

Must read before Batch 14C:

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
- `docs/POSTGRESQL_READINESS.md`
- `docs/REDIS_RATE_LIMIT_READINESS.md`
- `docs/SECURITY_REGRESSION_CHECKLIST.md`
- `docs/BATCH_14_STATUS.md`
- `docs/BATCH_14B_STATUS.md`
- `docs/BATCH_14B_FIX_01_STATUS.md`
- `docs/RESTRICTED_STAGING_VALIDATION_EVIDENCE.md`
- `docs/POSTGRESQL_REDIS_VALIDATION_EVIDENCE.md`
- `docs/LOCAL_DOCKER_POSTGRES_REDIS_VALIDATION_EVIDENCE.md`
- `docs/HTTPS_PROXY_CSRF_VALIDATION_EVIDENCE.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`

## Ordered Recommended Batches

1. Batch 14C: real restricted HTTPS/proxy/staging-host validation after local
   Docker PostgreSQL/Redis validation passed in Batch 14B-FIX-01.
2. Batch 14A: dashboard implementation planning/authorization, only if the
   owner explicitly chooses planning before dashboard code.
3. Batch 15: backup/restore synthetic drill evidence and
   monitoring/alerting setup plan.
4. Batch 16: legal/privacy/account recovery and patient identity verification
   policy.
5. Batch 17: doctor dashboard workflow completion/polish.
6. Batch 18: patient portal completion/hardening.
7. Batch 19: WhatsApp limited integration design/implementation only after
   privacy gates.
8. Batch 20: approved cases/reviews/media showcase plus private publication
   rules.
9. Batch 21: release candidate hardening.

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
