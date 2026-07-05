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

Batch 14C-VALIDATE-02 validation update: the real Render restricted staging
host now has deeper safe public evidence. HTTPS GET checks still return HTTP
200 for `/health/`, `/`, `/book/`, and `/en/book/`; HTTP HEAD checks redirect
the same public paths to HTTPS; home-page static assets return HTTP 200; public
responses expose `X-Content-Type-Options`, `Referrer-Policy`, and
`Cross-Origin-Opener-Policy`; anonymous portal login/register forms render CSRF
inputs and set a secure CSRF cookie over HTTPS. Booking confirmation and success
browser behavior, direct Render runtime commands, managed PostgreSQL/Redis
runtime evidence, logs, backup/restore, monitoring, load/concurrency, and
legal/privacy approval remain incomplete.

Batch 15-OPS-01 planning update: production-oriented operations plans now exist
for backup/restore and monitoring/alerting. The backup plan defines
PostgreSQL backup expectations, Redis non-authoritative recovery boundaries,
synthetic-only restore drill procedure, verification criteria, rollback
boundaries, owner checklist, frequency recommendations, and retention/deletion
considerations. The monitoring plan defines uptime checks for `/health/` and
`/`, private readiness monitoring, latency thresholds including the observed
about 32.5 second `/health/` response, error-rate monitoring,
deploy/database/cache alert expectations, privacy-safe error reporting, alert
routing, severity levels, incident response, and post-incident review. This
planning update does not execute a restore drill, configure a monitoring
provider, configure alert routing, add error reporting, or approve production
launch.

Batch 15-OPS-02 operations update: a synthetic-only local PostgreSQL logical
backup/restore drill passed using the repository-approved local Docker service
harness. The drill applied migrations, seeded only public/demo setup data,
dumped a local synthetic source database, restored it into a separate local
restore-test database, verified migration state, smoke checks, safe reports,
safe row counts, and the 246-test suite, then removed the generated artifact
and local drill databases. This improves local restore-procedure evidence only.
It does not prove real Render managed PostgreSQL restore behavior, backup
retention, RPO, RTO, monitoring, alert routing, legal/privacy approval, or
production readiness.

Batch 15-OPS-03 operations update: a lightweight GitHub Actions workflow now
checks the public Render restricted staging `/health/` and `/` endpoints by
safe GET only. The workflow is manually runnable, scheduled at low frequency,
uses `curl`, follows redirects, records HTTP status, total response time, and
final URL, warns on slow responses, and fails on non-200 status, timeout, or a
hard staging latency threshold. Manual PowerShell verification commands and
recent staging latency observations are documented. This is repository-native
staging evidence only. It does not configure a full monitoring provider, alert
routing, privacy-safe error reporting, Render settings, or production launch
readiness.

Batch 15-OPS-04 operations update: dependency vulnerability scan evidence and
response ownership were documented using available safe local and GitHub
tooling only. Local Django baseline checks, the full 246-test suite, and
`python -m pip check` passed. Local `check --deploy` and strict smoke were
also run under development settings and produced only the expected local
warnings. The repository has only `requirements.txt` as a dependency manifest,
and Dependabot is already configured weekly for Python and GitHub Actions. A
complete advisory-backed vulnerability scan did not run because `pip-audit`,
`safety`, `osv-scanner`, `trivy`, and `grype` were not available locally, and
GitHub vulnerability/Dependabot alerts were disabled. This is blocker
evidence, not a clean vulnerability scan. It does not change dependencies,
install scanners, enable GitHub security settings, configure CI scanning,
change Render settings, or approve production launch readiness.

Batch 15-OPS-05 operations update: advisory-backed dependency scanning is now
repository-supported with `pip-audit`. Local baseline checks, the full
246-test suite, and `python -m pip check` passed under local development
settings. `pip-audit 2.10.1` ran against `requirements.txt` and returned no
known vulnerabilities at scan time. A dedicated `Dependency audit` GitHub
Actions workflow now runs `pip-audit` on pull requests, manual dispatch, and a
low-frequency weekly schedule. This does not guarantee security, upgrade
dependencies, generate a lockfile, enable GitHub security settings, change
Render settings, approve a named response owner, or approve production launch
readiness.

Batch 15-OPS-06 operations update: monitoring provider readiness, alert
routing readiness, privacy-safe error-reporting readiness, and the operations
signal matrix are now documented. Safe public staging GET spot checks returned
HTTP 200 for `/health/` and `/`, but both responses exceeded 30 seconds and
remain severe staging latency evidence. This is docs/evidence-only. It does
not configure a monitoring provider, route alerts, add an error-reporting SDK,
change Render settings, create credentials, run a Render managed PostgreSQL
restore drill, or approve production launch readiness.

Batch 15-OPS-07 operations update: staging latency evidence and mitigation
decision gates are now documented. BATCH-15-OPS-07 reviewed the OPS-03 and
OPS-06 severe latency evidence, inspected the staging uptime workflow, and ran
four bounded rounds of safe public GET checks for `/health/` and `/` only.
All eight BATCH-15-OPS-07 checks returned HTTP 200 and completed in under
`0.25` seconds with response bodies discarded. This reduces evidence of
persistent latency during that observed window, but it does not prove root
cause or remove the historical intermittent severe-latency blocker. No Render
settings, monitoring providers, alert routes, dependencies, application code,
migrations, secrets, POSTs, response bodies, or patient data were changed or
recorded.

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
| Public site | Partial | Bilingual public pages, legal drafts, SEO basics, PWA foundation, and safe placeholder content exist. Batch 14C-VALIDATE-02 confirmed the Render staging home page returns HTTP 200 and its four same-origin static assets return HTTP 200. Final visual approval, legal review, real content verification, monitoring, and production validation remain. |
| Public booking | Partial | Login-free booking, slot generation, UUID success URLs, rate limits, no-cache confirmation/success, and regression tests exist. Batch 14C-VALIDATE-02 confirmed the public booking entry pages return HTTP 200 by GET, but staging rendered a placeholder state with no safe slot links, so booking confirmation CSRF/cookie behavior and success-page no-cache evidence remain incomplete. Booking POST, provider database/cache behavior, and load/concurrency tests remain. |
| Staff operations | Partial | Staff-only appointment list/detail and bounded status operations exist with authorization and tests. Broader dashboard, staff access review, audit retention, and operational policies remain. |
| Patient portal | Partial | Optional account, login, logout, password change, account summary, static recovery policy, appointment linking, and linked appointment viewing exist. Identity verification, secure recovery process, abuse monitoring, legal review, and staging validation remain. |
| Account security | Partial | Password hashing/validation, CSRF, POST-only logout, no-cache portal pages, generic linking errors, and rate limits exist. Batch 14C-VALIDATE-02 confirmed anonymous portal login/register forms include CSRF inputs and set a secure CSRF cookie over HTTPS. Email/phone ownership, recovery operations, production tuning, and abuse monitoring remain. |
| Production settings | Partial | Split settings, production checks, secure-cookie defaults, PostgreSQL/Redis support, strict smoke blockers, environment contract, safe production settings report, and Render-ready Gunicorn/WhiteNoise prerequisites exist. Render staging public GET/static/header evidence is now deeper, but strict staging runtime checks, full browser/proxy/security behavior, database/cache evidence, backups, monitoring, and owner-reviewed security response remain. |
| Deployment smoke | Done | Safe smoke command exists with human/JSON/strict modes, route/security summaries, prohibited-feature checks, redaction rules, and stronger production-like blockers. It does not deploy or prove infrastructure readiness by itself. |
| Staging readiness | Partial | Staging validation plan, gap analysis, environment contract, local validation scripts, local PostgreSQL/Redis harness, manual Render setup documentation, and sanitized Batch 14C-VALIDATE-02 evidence exist. The real Render staging service returns HTTP 200 for `/health/`, `/`, `/book/`, and `/en/book/`; HTTP redirects to HTTPS; home-page static assets return HTTP 200; and safe portal form CSRF/cookie evidence exists. Full production-like staging validation remains incomplete. |
| PostgreSQL readiness | Partial | PostgreSQL expectations, migration/concurrency plans, local constraint tests, and local Docker PostgreSQL harness exist. Batch 14B-FIX-01 fixed the local PostgreSQL locking blocker and PostgreSQL-backed booking/patient portal/full-suite tests now pass locally. Render staging is reachable after operator-managed migration work, but direct safe staging database command evidence, load/concurrency, backup/restore, and provider validation have not run in this batch. |
| Redis/shared cache readiness | Partial | Redis expectations and cache-key privacy tests exist. Batch 14B-FIX-01 proved local Docker Redis cache reachability and Redis-backed booking/patient portal/full-suite tests now pass locally. Render staging cache service exists by operator context, but real multi-process quota, outage, tuning, monitoring, and safe staging command evidence have not run in this batch. |
| Backup/restore | Partial | Synthetic-only drill runbooks and the Batch 15 operations plan exist. Batch 15-OPS-02 passed a local synthetic PostgreSQL logical dump/restore drill with public/demo setup data only, zero patients, zero appointments, safe post-restore reports, and 246 tests passing. Real Render managed PostgreSQL restore evidence, backup retention, RPO, RTO, backup monitoring, and provider-specific restore evidence remain incomplete. |
| Privacy/legal | Blocked | Draft pages and privacy matrices exist. Formal legal/privacy review, retention/deletion policy, recovery policy, and patient identity verification are required before launch. |
| Monitoring | Partial | Health/readiness endpoints, endpoint privacy tests, logging foundation, and monitoring/alerting readiness docs exist. Batch 15 adds uptime, latency, error-rate, deploy, database, cache, privacy-safe error reporting, alert routing, severity, incident response, and post-incident review planning. Batch 15-OPS-03 adds a low-frequency GitHub Actions staging uptime workflow for public `/health/` and `/` checks only. Batch 15-OPS-06 documents the operations signal matrix and records public GET spot checks with HTTP 200 but severe latency over 30 seconds. Batch 15-OPS-07 records bounded repeated public GET checks that were fast, plus mitigation decision gates for the historical intermittent severe-latency evidence. No full monitoring provider, alert routing, privacy-safe error reporting, or abuse alerts are configured. |
| Dependency security | Partial | Dependabot for Python and GitHub Actions plus dependency readiness docs exist. Batch 15-OPS-05 adds a `pip-audit` workflow and records a successful local advisory-backed scan of `requirements.txt` with no known advisories returned at scan time. Named response owner approval, GitHub alert settings decision, and lockfile/hash workflow decision remain incomplete. |
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

Estimated whole-project completion after Batch 15-OPS-07 staging latency
evidence and mitigation decision gates:

- Approximately 79% unchanged.

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
- Batch 14C-VALIDATE-02 deepens public staging evidence with HTTP-to-HTTPS
  redirect checks, static asset HTTP 200 checks, visible security header
  observations, and safe portal CSRF/cookie/no-cache checks.
- Batch 14C-VALIDATE-02 does not resolve booking confirmation and success
  browser behavior, direct Render runtime commands, managed database/cache
  command evidence, backup/restore, monitoring, legal/privacy, dependency
  scan, shared-cache multi-process/outage, or load-test blockers.
- Batch 15-OPS-01 makes backup/restore and monitoring execution requirements
  more precise but does not create restore evidence, configure uptime checks,
  configure alert routing, configure privacy-safe error reporting, or change
  production readiness.
- Batch 15-OPS-02 proves the local synthetic PostgreSQL logical restore
  procedure with public/demo setup data only, but it does not prove Render
  managed backup/restore, backup policy approval, monitoring provider setup,
  alert routing, legal/privacy approval, or production readiness.
- Batch 15-OPS-03 adds repository-native public staging uptime and latency
  evidence for `/health/` and `/`, but it does not configure a full monitoring
  provider, alert routing, privacy-safe error reporting, or production
  readiness.
- Batch 15-OPS-04 documents dependency inventory, local dependency consistency,
  scanner/tooling blockers, response ownership roles, severity handling, and
  update cadence.
- Batch 15-OPS-05 adds a repository-supported `pip-audit` workflow and records
  a successful local advisory-backed scan of `requirements.txt`, but it does
  not approve a named human response owner, enable GitHub security settings, or
  close the lockfile/hash workflow decision.
- Batch 15-OPS-06 documents monitoring provider readiness, alert routing,
  privacy-safe error-reporting readiness, and the operations signal matrix, but
  it does not configure an external provider, route alerts, add error
  reporting, or resolve the severe staging latency evidence.
- Batch 15-OPS-07 adds bounded repeated public GET latency evidence and a
  mitigation decision pack. The repeated checks were fast, which argues against
  persistent latency during that observation window, but OPS-03/OPS-06 severe
  latency remains unresolved until root cause, monitoring, alert routing, and
  hosting/runtime decisions are made.
- The estimate remains below launch-ready because real staging/prod
  validation depth, production infrastructure, legal/privacy approval,
  full monitoring and alert routing, backup/restore drill, owner-reviewed
  security response, load testing, and Figma-approved future design governance
  are still unresolved.
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
- Real dependency vulnerability response without approved owner review.

## Do Not Launch Publicly Until

- Full restricted staging validation with managed PostgreSQL and shared cache
  passes beyond public GET reachability.
- `DEBUG=False` and production settings are active in staging/production.
- HTTPS, reverse proxy headers, secure cookies, CSRF origins, and HSTS behavior
  are verified.
- `python manage.py check --deploy` is reviewed in production-like settings.
- `python manage.py deployment_smoke --strict` passes in staging.
- Full tests pass in CI/local release validation.
- Real Render managed PostgreSQL restore drill with synthetic data is complete.
- Monitoring, uptime checks, log collection, and alert routing are configured.
- Dependency/security scanning is enabled, produces an advisory-backed result,
  and is reviewed by the accountable owner.
- Load/concurrency tests are completed against staging.
- Public booking duplicate/concurrency behavior is validated on PostgreSQL.
- Redis/shared-cache rate limiting is validated across app processes.
- Redis outage behavior is decided and tested.
- Legal/privacy review is complete.
- Patient identity verification policy is approved.
- Secure account recovery policy is approved.
- Staff/admin access review and offboarding policy are defined.
- Audit retention policy is defined.
- Static serving strategy is chosen and tested beyond the basic home-page
  static asset checks.
- Figma-approved visual changes, if any, are implemented and verified.

## Remaining Launch Blockers

- Real Render restricted staging is functionally reachable for public GET
  checks, HTTP-to-HTTPS HEAD redirects, and basic home-page static asset GETs;
  full production-like staging validation remains incomplete.
- Safe portal form CSRF/cookie/no-cache evidence exists, but booking
  confirmation form and success-page browser behavior remain incomplete.
- No production hosting, DNS, custom TLS/domain, or production reverse proxy
  exists in this repo.
- Local Docker PostgreSQL/Redis validation now passes for the current bounded
  test/smoke/report scope, and Render staging is externally reachable, but
  direct safe staging command evidence, provider load/concurrency validation,
  backup/restore, and shared-cache multi-process/outage evidence remain
  incomplete.
- Backup/restore planning is more precise, and a local synthetic PostgreSQL
  restore drill passed, but no real Render managed PostgreSQL restore drill
  has been completed.
- Monitoring/alerting planning is more precise, a low-frequency
  repository-native staging uptime workflow exists for public GET checks, and
  the operations signal matrix is documented, but no full monitoring provider,
  alert routing, privacy-safe error reporting, or abuse alert is configured.
  OPS-07 bounded repeated public staging GET checks returned HTTP 200 in under
  `0.25` seconds, but OPS-03/OPS-06 severe latency over 30 seconds remains
  unresolved until an owner/operator mitigation decision and provider evidence
  exist.
- No legal/privacy approval is recorded.
- No verified email/phone ownership policy is approved.
- No secure account recovery operation is approved.
- No production rate-limit tuning has been completed.
- No load/concurrency test results exist.
- Dependency vulnerability scanning is now supported by `pip-audit` locally and
  in CI, but GitHub vulnerability and Dependabot alert settings still need an
  owner decision, the lockfile/hash workflow decision remains open, and
  response ownership still needs named owner approval.
- No staff access review process is defined.
- No audit retention/access review policy is defined.
- No Figma handoff exists for future visual changes.

## Recommended Next Batches

1. Batch 14C-VALIDATE-03: operator-assisted Render runtime validation if safe
   access is available, including staging shell management commands, managed
   PostgreSQL/Redis evidence, booking confirmation/browser checks with
   synthetic data only, and sanitized targeted log review.
2. Next operations follow-up: owner/operator decision on Render latency
   mitigation and monitoring/alerting provider setup, plus operator-approved
   Render managed PostgreSQL restore drill with synthetic data only.
3. Batch 15-OPS-08: dependency response owner approval, GitHub alert settings
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

Batch 14C-VALIDATE-02 adds deeper sanitized Render staging evidence for public
HTTPS reachability, HTTP-to-HTTPS redirects, basic static assets, public
security headers, and safe portal CSRF/cookie/no-cache behavior. It does not
add product features, change code, create patient data, submit booking POSTs,
use secrets, document connection strings, run Render shell commands, fetch full
logs, or claim production launch readiness.

Batch 15-OPS-02 adds local synthetic restore evidence. It does not add product
features, change code, create patient data, use active Render staging data,
change Render settings, configure monitoring, approve retention/RPO/RTO, approve
legal/privacy, or claim production launch readiness.

Batch 15-OPS-03 adds lightweight repository-native staging uptime and latency
evidence. It does not add product features, create patient data, submit booking
POSTs, use secrets, check private routes, change Render settings, configure a
full monitoring provider, configure alert routing, add privacy-safe error
reporting, or claim production launch readiness.

Batch 15-OPS-04 adds dependency vulnerability scan attempt evidence and
response ownership documentation. It does not add product features, create
patient data, change dependencies, install scanners, enable GitHub security
settings, change Render settings, configure CI scanning, or claim production
launch readiness.

Batch 15-OPS-05 adds advisory-backed dependency scanning with `pip-audit`, a
dedicated dependency audit workflow, and updated evidence. It does not add
product features, create patient data, change dependencies, generate a
lockfile, enable GitHub security settings, change Render settings, or claim
production launch readiness.

Batch 15-OPS-06 adds monitoring provider readiness, alert-routing readiness,
privacy-safe error-reporting readiness, and operations signal matrix evidence.
It does not add product features, create patient data, submit booking POSTs,
change dependencies, configure external providers, route alerts, add
error-reporting SDKs, change Render settings, run a Render managed restore
drill, or claim production launch readiness.

Batch 15-OPS-07 adds staging latency evidence and mitigation decision gates.
It does not add product features, create patient data, submit booking POSTs,
change dependencies, configure external providers, route alerts, add
error-reporting SDKs, change Render settings, run Render shell commands, or
claim production launch readiness.

## Design Status

- Figma required for future visual changes.
- Codex must not invent colors, spacing, typography, visual hierarchy,
  animations, decorative elements, brand style, shadows, borders, or hover
  effects.
- Batch 13 status: No visual design work performed by Codex.
