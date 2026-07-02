# Project Release Scorecard

Batch 11 release-readiness scorecard for Dr. Khaled Badran Clinic after the
restricted staging validation operations and production-like safety harness
work.

Batch 12 planning update: the active planning direction is now the Final
Product Completion Track. DEMO_TRACK is no longer the project priority.
Synthetic demo data remains allowed only for local validation/testing. This
planning update does not change the factual readiness claims below.

Batch 13 planning update: final UX/product-flow specifications and design
handoff requirements were added for public site, booking, doctor/admin
dashboard, patient portal, bilingual content, and mobile/accessibility review.
Batch 13 did not create Figma work, visual design, application code, or launch
evidence. This planning update does not increase whole-project completion or
change the factual readiness claims below.

Batch 14 validation update: local/provisional restricted-staging validation
evidence was recorded for the current bounded system. Local checks, smoke
commands, safe reports, and 246 tests passed under development settings, and
synthetic production-settings checks correctly rejected SQLite/LocMemCache.
Real restricted staging infrastructure was not provided, so PostgreSQL,
Redis/shared cache, HTTPS, reverse proxy, host, and CSRF behavior remain
unvalidated. This validation update does not increase whole-project completion
or change the launch blockers below.

Batch 14B validation update: the repository-approved local Docker
PostgreSQL/Redis service harness ran locally with Docker Desktop and WSL2.
PostgreSQL and Redis services started, PostgreSQL migrations applied, and
combined smoke/report commands reached both services under development
settings. Redis-backed booking and patient portal app tests passed on SQLite.
PostgreSQL-backed booking, patient portal, and full-suite tests failed on a
PostgreSQL `select_for_update()` nullable outer-join blocker. This validation
update does not increase whole-project completion and does not claim real
restricted staging, HTTPS/proxy, production, backup, monitoring, legal/privacy,
or load readiness.

Batch 14B-FIX-01 validation update: the local Docker PostgreSQL
`select_for_update()` nullable outer-join blocker was fixed in staff
appointment operations and patient portal appointment linking. Default local
SQLite/LocMem validation passed; local Docker PostgreSQL-backed booking,
patient portal, and full-suite tests passed; local Docker Redis-backed booking,
patient portal, and full-suite tests passed; combined local Docker
PostgreSQL+Redis booking, patient portal, and full-suite tests passed. This
improves local service-backed evidence but does not claim real restricted
staging, HTTPS/proxy, production, backup/restore, monitoring, legal/privacy,
Redis multi-process/outage, load/concurrency readiness, or launch readiness.

Batch 14C-PREP-01 readiness update: manual Render restricted staging
prerequisites were added. The repository now declares `gunicorn` for a Render
Python web service, declares and configures WhiteNoise compressed static asset
serving, and documents exact manual Render build/start commands plus
environment variable expectations. This is deployment-readiness prep only; it
does not deploy, create Render services, validate real HTTPS/proxy/CSRF
behavior, create secrets, or prove real staging readiness.

Batch 14C-VALIDATE-01 validation update: the real Render restricted staging
web service is functionally reachable for bounded public GET evidence.
Local baseline commands passed without staging secrets, and public GET checks
returned HTTP 200 for `/health/`, `/`, `/book/`, and `/en/book/`. This confirms
restricted staging reachability only. It does not approve production launch,
legal/privacy readiness, backup/restore readiness, monitoring readiness,
load/concurrency readiness, shared-cache multi-process/outage readiness, or
future product areas.

Status labels:

- `Done` means implemented and covered by local checks for the current bounded
  scope.
- `Partial` means useful foundation exists but launch-critical work remains.
- `Blocked` means it should not proceed until an external decision, design,
  legal review, or infrastructure step is complete.
- `Not Started` means no meaningful implementation exists yet.
- `Out of Scope for Now` means intentionally absent in the current release
  boundary.

## Area Scorecard

| Area | Status | Notes |
| --- | --- | --- |
| Public site | Partial | Bilingual public pages, legal drafts, SEO basics, PWA foundation, and safe placeholder content exist. Batch 14C-VALIDATE-01 confirmed the Render staging home page returns HTTP 200. Final visual approval, legal review, real content verification, monitoring, and production validation remain. |
| Public booking | Partial | Login-free booking, slot generation, UUID success URLs, rate limits, no-cache confirmation/success, and regression tests exist. Batch 14C-VALIDATE-01 confirmed the public booking entry pages return HTTP 200 by GET only. Booking POST, provider database/cache behavior, and load/concurrency tests remain. |
| Staff operations | Partial | Staff-only appointment list/detail and bounded status operations exist with authorization and tests. Broader dashboard, staff access review, audit retention, and operational policies remain. |
| Patient portal | Partial | Optional account, login, logout, password change, account summary, static recovery policy, appointment linking, and linked appointment viewing exist. Identity verification, secure recovery process, abuse monitoring, legal review, and staging validation remain. |
| Account security | Partial | Password hashing/validation, CSRF, POST-only logout, no-cache portal pages, generic linking errors, and rate limits exist. Email/phone ownership, recovery operations, production tuning, and abuse monitoring remain. |
| Production settings | Partial | Split settings, production checks, secure-cookie defaults, PostgreSQL/Redis support, strict smoke blockers, environment contract, safe production settings report, and Render-ready Gunicorn/WhiteNoise prerequisites exist. Render staging public GET reachability is now validated, but strict staging runtime checks, proxy/security behavior, database/cache evidence, backups, monitoring, and scanning remain. |
| Deployment smoke | Done | Safe smoke command exists with human/JSON/strict modes, route/security summaries, prohibited-feature checks, redaction rules, and stronger production-like blockers. It does not deploy or prove infrastructure readiness by itself. |
| Staging readiness | Partial | Staging validation plan, gap analysis, environment contract, local validation scripts, local PostgreSQL/Redis harness, manual Render setup documentation, and sanitized Batch 14C-VALIDATE-01 evidence exist. The real Render staging service returns HTTP 200 for `/health/`, `/`, `/book/`, and `/en/book/`, so functional restricted staging is yes for bounded public GET evidence. Full production-like staging validation remains incomplete. |
| PostgreSQL readiness | Partial | PostgreSQL expectations, migration/concurrency plans, local constraint tests, and local Docker PostgreSQL harness exist. Batch 14B-FIX-01 fixed the local PostgreSQL locking blocker and PostgreSQL-backed booking/patient portal/full-suite tests now pass locally. Render staging is reachable after operator-managed migration work, but direct safe staging database command evidence, load/concurrency, backup/restore, and provider validation have not run in this batch. |
| Redis/shared cache readiness | Partial | Redis expectations and cache-key privacy tests exist. Batch 14B-FIX-01 proved local Docker Redis cache reachability and Redis-backed booking/patient portal/full-suite tests now pass locally. Render staging cache service exists by operator context, but real multi-process quota, outage, tuning, monitoring, and safe staging command evidence have not run in this batch. |
| Backup/restore | Planned | Synthetic-only drill plan and runbooks exist. No actual PostgreSQL restore drill evidence exists. |
| Privacy/legal | Blocked | Draft pages and privacy matrices exist. Formal legal/privacy review, retention/deletion policy, recovery policy, and patient identity verification are required before launch. |
| Monitoring | Partial | Health/readiness endpoints, endpoint privacy tests, logging foundation, and monitoring/alerting readiness docs exist. No real uptime checks, alert routing, error reporting, or abuse alerts are configured. |
| Dependency security | Partial | Dependabot for Python and GitHub Actions plus dependency readiness docs exist. No vulnerability scan evidence or approved response owner exists yet. |
| Staff/admin governance | Partial | Staff access governance is documented and staff route tests exist. Real staff roster, superuser minimization, and access review remain manual/pre-launch. |
| Design/Figma | Blocked | Current code has existing visual foundation from earlier batches. Batch 13 defines UX/product-flow and design handoff requirements only. Future visual changes still require human/Figma handoff and approval before Codex implementation. |
| Uploads | Out of Scope for Now | No upload routes or private media handling are implemented. Private storage, malware scanning, retention, access control, and legal design are required first. |
| Medical records | Out of Scope for Now | No medical-record routes or models are implemented. Authorization, audit, retention, patient visibility, legal, and clinical workflows are required first. |
| WhatsApp | Out of Scope for Now | No WhatsApp API sending, webhook, message model, or credential use is implemented. Consent, security, logging, provider, and medical-information boundaries are required first. |
| Payments | Out of Scope for Now | No payment routes or payment provider integration are implemented. Provider, refund, reconciliation, privacy, and accounting policy are required first. |

## Batch 11 Status

Batch 11 adds:

- staging gap analysis,
- staging environment contract,
- local validation scripts,
- optional local PostgreSQL/Redis service harness,
- safe `production_settings_report` command,
- stricter production-like `deployment_smoke` blockers,
- PostgreSQL readiness documentation and constraint tests,
- Redis/shared-cache readiness documentation and cache-key privacy tests,
- synthetic backup/restore drill plan,
- monitoring/alerting readiness documentation,
- dependency security readiness documentation,
- bounded Dependabot config,
- staff/admin governance documentation,
- legal/privacy operations documentation,
- CI gate strengthening.

Batch 11 does not add real staging infrastructure, secrets, DNS, hosting,
external monitoring, backups, restore evidence, legal approval, or production
launch.

## Conservative Completion Estimate

Estimated whole-project completion after Batch 14C-VALIDATE-01 Render staging
reachability validation:

- Approximately 77-78%.

Rationale:

- The public site, booking, staff appointment operations, and bounded patient
  portal foundations are implemented and locally tested.
- Batch 10 improved reviewability, route inventory, data exposure documentation,
  staging readiness, smoke safety, and regression coverage.
- Batch 11 improves restricted staging validation operations, local safety
  harnesses, production-like reporting, CI gates, PostgreSQL/Redis readiness,
  backup/restore planning, monitoring readiness, dependency governance,
  staff/admin governance, and legal/privacy operations documentation.
- Batch 14 confirms local/provisional validation is healthy under default
  SQLite/LocMem development settings.
- Batch 14B improved local service evidence but discovered that
  PostgreSQL-backed booking/staff/patient portal tests failed.
- Batch 14B-FIX-01 fixes that local PostgreSQL blocker and proves the current
  bounded suite under local Docker PostgreSQL, local Docker Redis, and combined
  PostgreSQL+Redis.
- Batch 14C-PREP-01 prepares the app to run as a manual Render Python web
  service with Gunicorn and WhiteNoise and documents the staging environment
  contract.
- Batch 14C-VALIDATE-01 confirms the real Render staging host is externally
  reachable and public GET checks for liveness, home, and booking entry pages
  return HTTP 200.
- Batch 14C-VALIDATE-01 does not resolve full HTTPS/proxy/browser security,
  managed database/cache command evidence, backup/restore, monitoring,
  legal/privacy, dependency scan, shared-cache multi-process/outage, or
  load-test blockers.
- The estimate remains below launch-ready because real staging/prod
  validation depth, production infrastructure, legal/privacy approval,
  monitoring, backup/restore drill, security scanning, load testing, and
  Figma-approved future design governance are still unresolved.
- Large future feature areas remain intentionally absent: uploads, medical
  records, WhatsApp API/webhooks, payments, and medical automation.

## Safe to Demo Now

Safe demo scope with synthetic data only:

- Arabic and English public website pages.
- Public booking flow through synthetic appointment creation.
- UUID public booking success page.
- Optional patient portal registration/login.
- Patient password change.
- Patient account summary.
- Static account recovery policy.
- Appointment linking using synthetic UUID token and matching phone.
- Linked appointment list/detail for the owning logged-in user.
- Staff appointment list/detail and bounded status operations using synthetic
  appointments and staff accounts.
- `deployment_smoke` human and JSON output.
- `production_settings_report` human and JSON output.
- Local validation scripts in a trusted local shell.
- Optional local PostgreSQL/Redis Docker service harness with synthetic data
  only, with Batch 14B-FIX-01 passing locally and real staging still clearly
  disclosed as unvalidated.
- Route/access, data exposure, staging, and release documentation.

Demo rules:

- Use synthetic patients only.
- Do not use real phone numbers, emails, reports, diagnoses, or appointment
  histories.
- Do not claim legal/privacy approval.
- Do not claim production readiness.
- Do not test uploads, medical records, WhatsApp API, payments, diagnosis,
  triage, treatment automation, or medical AI.

## Not Safe to Demo Yet

Not safe to demo as real or production functionality:

- Real patient onboarding.
- Real patient appointment history.
- Real account recovery.
- Real email password reset.
- Real WhatsApp sending or receiving.
- Real uploads or medical reports.
- Medical-record access.
- Payment collection.
- Diagnosis, triage, treatment automation, or medical AI.
- Production deployment.
- Provider-specific staging/production behavior not yet validated.
- Real backup/restore recovery.
- Monitoring and incident response in a live environment.
- Real dependency vulnerability response without owner review.

## Do Not Launch Publicly Until

- Full restricted staging validation with managed PostgreSQL and shared cache
  passes beyond public GET reachability.
- `DEBUG=False` and production settings are active in staging/production.
- HTTPS, reverse proxy headers, secure cookies, CSRF origins, and HSTS behavior
  are verified.
- `python manage.py check --deploy` is reviewed in production-like settings.
- `python manage.py deployment_smoke --strict` passes in staging.
- Full tests pass in CI/local release validation.
- Backup and restore drill with synthetic data is complete.
- Monitoring, uptime checks, log collection, and alert routing are configured.
- Dependency/security scanning is configured and reviewed.
- Load/concurrency tests are completed against staging.
- Public booking duplicate/concurrency behavior is validated on PostgreSQL.
- Redis/shared-cache rate limiting is validated across app processes.
- Redis outage behavior is decided and tested.
- Legal/privacy review is complete.
- Patient identity verification policy is approved.
- Secure account recovery policy is approved.
- Staff/admin access review and offboarding policy are defined.
- Audit retention policy is defined.
- Static serving strategy is chosen and tested.
- Figma-approved visual changes, if any, are implemented and verified.

## Remaining Launch Blockers

- Real Render restricted staging is functionally reachable for public GET
  checks only; full production-like staging validation remains incomplete.
- No production hosting, DNS, custom TLS/domain, or production reverse proxy
  exists in this repo.
- Local Docker PostgreSQL/Redis validation now passes for the current bounded
  test/smoke/report scope, and Render staging is externally reachable, but
  direct safe staging command evidence, provider load/concurrency validation,
  backup/restore, and shared-cache multi-process/outage evidence remain
  incomplete.
- No backup/restore drill has been completed.
- No monitoring/error reporting is configured.
- No legal/privacy approval is recorded.
- No verified email/phone ownership policy is approved.
- No secure account recovery operation is approved.
- No production rate-limit tuning has been completed.
- No load/concurrency test results exist.
- No dependency vulnerability scanning workflow is configured.
- Dependabot exists, but vulnerability scan evidence and response ownership are
  not complete.
- No staff access review process is defined.
- No audit retention/access review policy is defined.
- No Figma handoff exists for future visual changes.

## Recommended Next Batches

1. Batch 14C-VALIDATE-02: complete deeper Render staging validation if
   operator access is available, including safe staging shell checks,
   browser-level HTTPS/proxy/CSRF/cookie behavior, static asset validation, and
   sanitized log review.
2. Batch 15: backup/restore synthetic drill evidence and
   monitoring/alerting setup plan.
3. Batch 14A: dashboard implementation planning/authorization, only if the
   owner explicitly chooses planning before dashboard code.
4. Batch 16: legal/privacy/account recovery and patient identity verification
   policy.
5. Batch 17: doctor dashboard workflow completion/polish.
6. Batch 18: patient portal completion/hardening.
7. Batch 19: WhatsApp limited integration design/implementation only after
   privacy gates.
8. Batch 20: approved cases/reviews/media showcase plus private publication
   rules.
9. Batch 21: release candidate hardening.

Batch 12 adds planning documents for final product completion, doctor-managed
configuration, and authorized showcase publication-consent requirements. It
does not implement code or change launch readiness.

Batch 13 adds final UX/product-flow audit and specifications plus design
handoff requirements. It does not create Figma work, visual design, product
code, deployment, external infrastructure, real patient data, or launch
readiness.

Batch 14 adds local/provisional restricted staging validation evidence and
blocker documentation. It does not create product code, deployment, external
infrastructure, secrets, real patient data, real staging infrastructure, or
launch readiness.

Batch 14B adds local Docker PostgreSQL/Redis validation evidence. It does not
create product code, settings changes, dependency-file changes, deployment,
external infrastructure, secrets, real patient data, real staging
infrastructure, or launch readiness.

Batch 14B-FIX-01 adds a narrow PostgreSQL locking bugfix plus corrected local
Docker PostgreSQL/Redis validation evidence. It does not add product features,
models, migrations, templates, visual design, deployment, external
infrastructure, secrets, real patient data, real staging infrastructure, legal
approval, backup/restore evidence, monitoring evidence, or launch readiness.

Batch 14C-PREP-01 adds Render runtime/static serving prerequisites and manual
Render staging documentation. It does not deploy, create Render services,
create `render.yaml`, add product features, change models or migrations, use
secrets, use real patient data, validate real staging, or claim launch
readiness.

Batch 14C-VALIDATE-01 adds sanitized real Render restricted staging evidence.
It does not add product features, change code, create patient data, use
secrets, document connection strings, run full staging shell validation, or
claim production launch readiness.

## Design Status

- Figma required for future visual changes.
- Codex must not invent colors, spacing, typography, visual hierarchy,
  animations, decorative elements, brand style, shadows, borders, or hover
  effects.
- Batch 13 status: No visual design work performed by Codex.
