# Release Checklist

This checklist is for future local, staging, and production release validation. It does not deploy anything by itself.

## Environment Command Sequences

### Local Development

```bash
python manage.py check
python manage.py test
python manage.py deployment_smoke
```

Expected local smoke warnings are acceptable when they identify local-only settings such as DEBUG, SQLite, LocMemCache, or disabled HTTPS redirect.

### Staging

Staging must be production-like, restricted, and free of real patient data.

```bash
python manage.py migrate --check
python manage.py check
python manage.py check --deploy
python manage.py deployment_smoke --strict
python manage.py seed_public_content
python manage.py seed_booking_demo
```

Run tests in staging only when the staging database is disposable or the tests use a separate CI clone:

```bash
python manage.py test
```

If `migrate --check` is unavailable in the deployed Django version, use an equivalent reviewed migration-plan check.

### Production

```bash
python manage.py check --deploy
python manage.py deployment_smoke --strict
```

Production migration must happen only with a backup and rollback plan. Do not run destructive seed commands in production unless explicitly approved by the project owner.

## Pre-Merge Checklist

- Scope matches the approved batch.
- No patient portal expansion beyond the approved batch, uploads, WhatsApp API sending/webhooks, online payments, medical records, or medical automation were added unless the batch explicitly approves them.
- No real secrets, credentials, patient data, logs, private files, or database dumps are committed.
- Route changes are reviewed against `docs/ROUTE_ACCESS_MATRIX.md`.
- Patient/public/staff data exposure changes are reviewed against `docs/DATA_EXPOSURE_MATRIX.md`.
- Future visual changes have an approved Figma handoff and do not bypass security/privacy requirements. Figma implementation is temporarily deferred by owner decision during the patient record foundation work.
- Public booking success URLs still use UUID `public_token` values.
- Numeric appointment success routes remain absent.
- Staff appointment pages and operations remain staff-only.
- Patient portal pages remain no-cache.
- Portal logout remains POST-only.
- Account recovery remains GET-only/static unless a secure recovery process is separately approved.
- Prohibited upload, medical-record, WhatsApp API/webhook, and payment routes remain absent.
- Tests were added for changed behavior.
- `python manage.py makemigrations --check --dry-run` passes.
- `python manage.py check` passes.
- `python manage.py test` passes.
- Dependency/security batches document either an advisory-backed scan result or
  the exact scanner/tooling blocker.
- Dependency/security batches using the repository-supported scanner run and
  document `pip-audit -r requirements.txt --progress-spinner off`.
- Dependency/security batches identify the response owner role, severity
  handling, and remaining owner-approval blocker.
- Dependency upgrades, lockfiles, or scanner workflow additions are absent
  unless the batch explicitly approves them.
- Monitoring/alerting batches review
  `docs/OPERATIONS_MONITORING_ALERTING_PLAN.md` and
  `docs/OPERATIONS_SIGNAL_MATRIX.md`.
- Monitoring/alerting batches do not claim provider readiness, alert-routing
  readiness, or privacy-safe error-reporting readiness unless a provider and
  alert route were configured and tested outside Git with secret-safe evidence.
- Staging latency evidence batches compare new public GET timings against
  OPS-03/OPS-06 severe latency evidence and document likely causes, production
  impact, mitigation options, and owner/operator decision gates.
- Extended staging observation batches remain low frequency, use public GET
  only, discard response bodies, and do not become keep-alive polling.
- Restore-readiness batches do not claim Render managed restore readiness
  unless an owner-approved isolated restore drill was actually executed and
  sanitized evidence was reviewed.
- Operations governance batches do not claim blocker closure from decision
  packs alone; owner assignments, provider setup, alert route tests, GitHub
  alert setting decisions, legal/privacy approval, and production go/no-go must
  be actual decisions.
- No private owner contact details, webhook URLs, provider credentials, or
  private GitHub settings dumps are committed.

## Commercial Handoff Checklist

Use `docs/CLINIC_DELIVERY_V1_SCOPE_LOCK.md` as the source of truth for
Commercial Delivery v1 scope unless a later approved scope-lock document
supersedes it.

Commercial handoff readiness requires:

- final Figma implementation audited and implemented within approved design
  governance;
- public booking works from the website without required login, with
  confirmation and patient-safe success/error states;
- WhatsApp quick link exists without WhatsApp Business API automation unless
  separately approved;
- patient record v1 exists as a practical clinic record, not a full hospital
  EMR;
- private image and short-video media handling exists with type/size
  validation, no public medical-file URLs, and dashboard-controlled
  deletion/hiding;
- patient portal shows only doctor/staff-approved record content and remains
  read-only for medical record content in v1;
- public cases/achievements display uses only active `approved_public_case`
  media with confirmed consent through controlled public media routes.

Current BATCH-16-DELIVERY-04 status:

- patient medical record foundation is backend-only model/admin/test
  groundwork governed by `docs/CLINIC_DELIVERY_V1_SCOPE_LOCK.md`;
- private media storage/access-control foundation is implemented with local
  private filesystem storage, UUID-based private file paths, allowed
  image/short-MP4 type and size validation, metadata capture, and a staff-only
  private download route by media `public_id`;
- patient portal approved record visibility foundation is implemented with a
  read-only authenticated portal page for the linked patient only;
- patient portal records show only doctor/staff-approved visits and notes
  marked `is_visible_to_patient=True` and active media marked
  `visible_to_patient`;
- patient-facing media access uses an authenticated patient-owned route by
  `RecordMedia.public_id` and does not expose public media URLs or local file
  paths;
- public cases/achievements media foundation is implemented with `/cases/` and
  `/en/cases/` public pages showing sanitized metadata only for active
  `approved_public_case` media with `consent_confirmed=True`;
- public approved media access uses controlled
  `/cases/media/<uuid:public_id>/` and `/en/cases/media/<uuid:public_id>/`
  routes and does not expose direct private file URLs or local file paths;
- patient-visible media remains separate from public cases, and private-only,
  inactive, and unconsented media are not public;
- private medical record content, patient identity, appointment details,
  doctor notes, diagnosis/plan, instructions, and follow-up notes are not
  exposed by public cases;
- production-ready remains `no`;
- Figma implementation is temporarily deferred by owner decision;
- next delivery batch: `BATCH-16-DELIVERY-05: doctor/staff dashboard record
  workflow polish`.

Commercial handoff readiness does not mean production launch readiness.
Production launch blockers, including legal/privacy approval, staging runtime
validation, managed backup/restore, monitoring provider setup, alert routing,
load/concurrency validation, production DNS/custom domain/TLS, dependency
governance decisions, and final go/no-go approval remain separate.

## Dependency Audit Checklist

- `.github/workflows/dependency-audit.yml` remains manually runnable.
- The dependency audit workflow runs on pull requests.
- The dependency audit workflow uses a low-frequency schedule only.
- The workflow installs `pip-audit` as CI tooling only.
- The workflow does not upgrade project dependencies.
- The workflow does not modify `requirements.txt`.
- The workflow does not generate a lockfile.
- The workflow uses no secrets, Render access, external application endpoints,
  response bodies, logs, or patient data.
- `pip-audit -r requirements.txt --progress-spinner off` passes before a
  release candidate and before production promotion.
- A result of `No known vulnerabilities found` means no known advisories were
  returned by the scanner at scan time, not a guarantee of security.
- Critical/high dependency advisories block release until owner triage,
  patch/mitigation, and validation are complete.
- A named dependency response owner and backup owner must be approved before
  production launch.
- GitHub vulnerability and Dependabot alert settings still need an owner
  decision if not enabled.
- The GitHub vulnerability/Dependabot settings decision must be recorded
  safely without private settings dumps or tokens.
- The bounded-ranges versus lockfile/hash workflow decision remains open until
  explicitly approved.

## Operations Monitoring and Error Reporting Checklist

- `docs/OPERATIONS_SIGNAL_MATRIX.md` is reviewed before claiming operations
  monitoring readiness.
- Public `/health/` and `/` checks record status, latency, and final URL only.
- Public monitoring checks do not print response bodies.
- Private `/health/ready/` monitoring is configured only through a private or
  trusted internal path where possible.
- Severe staging latency over 30 seconds is treated as a blocker requiring
  review, even when HTTP status is 200.
- Fast bounded repeated public GET checks do not remove earlier severe latency
  blockers unless root cause is proven or an owner-approved mitigation/risk
  acceptance is documented.
- Extended observation evidence is still not a production SLA, not a load test,
  and not proof of database/cache readiness.
- External monitoring provider selection is owner-approved before
  configuration.
- Monitoring provider must be approved, configured, and tested before
  monitoring provider readiness is claimed.
- Alert recipients and escalation paths are approved outside Git.
- Alert routes are tested before launch.
- Primary and backup alert routes must be tested with safe synthetic payloads
  before alert-routing readiness is claimed.
- Alert payloads do not include secrets, patient data, request bodies, cookies,
  raw tokens, database URLs, cache URLs, private keys, or provider keys.
- Privacy-safe error reporting is not enabled until request-body capture is
  disabled, required scrubbers are configured, retention is approved, and a
  synthetic event is reviewed.
- No monitoring DSNs, webhook URLs, API keys, tokens, private contacts, or
  provider environment dumps are committed.

## Pre-Deploy Checklist

- Release revision is identified.
- Environment variables are configured outside Git.
- Staging validation follows `docs/STAGING_VALIDATION_PLAN.md`.
- Staging has its own generated application secret.
- Staging and production use exact allowed hosts.
- CSRF trusted origins are set to HTTPS origins.
- PostgreSQL is configured for staging/production.
- Shared cache such as Redis is configured for staging/production.
- HTTPS and proxy behavior are reviewed.
- `BOOKING_TRUST_X_FORWARDED_FOR` remains false unless trusted proxy stripping is verified.
- Backup and rollback plan exists.
- Named roles are approved outside Git, including project owner, technical
  operator, backup technical operator, monitoring owner, alert-routing owner,
  incident commander, backup owner, backup owner backup, restore drill owner,
  dependency response owner, dependency response backup, legal/privacy
  reviewer, release/go-no-go approver, and doctor/admin business reviewer.
- Repository docs contain no private contact details for those roles.
- Backup retention, RPO, and RTO have owner approval, or the missing approval
  is recorded as a launch blocker.
- A Render managed PostgreSQL restore drill has completed in an isolated target
  with sanitized evidence, or the missing drill is recorded as a launch
  blocker.
- Monitoring owner is assigned.
- Operations signal matrix has been reviewed and any incomplete provider,
  alert-routing, or privacy-safe error-reporting item is recorded as a launch
  blocker.
- Monitoring provider selection is approved, configured, tested, and recorded
  with sanitized evidence.
- Alert routes are approved and tested, with no webhook URLs or private contact
  details in repository docs.
- Dependency owner and backup owner are assigned outside Git.
- GitHub vulnerability alert, Dependabot alert, dependency update strategy,
  and bounded-ranges versus lockfile/hash decisions are recorded safely.
- Historical severe staging latency has a documented owner/operator decision:
  mitigated by hosting/runtime/provider changes, proven not applicable to
  production, or explicitly risk-accepted before launch.
- Dependency vulnerability scan source is enabled and reviewed, or a launch
  blocker is explicitly recorded.
- Critical/high dependency advisories have an accountable owner decision,
  patch or mitigation plan, and validation evidence.
- Legal/privacy review status is known.

## Migration Checklist

- Migration files are reviewed.
- Backup is completed or verified within the approved recovery window.
- Restore path is known.
- `python manage.py migrate --check` or equivalent is reviewed before migration.
- Migration is run as a controlled step.
- Post-migration smoke checks run before traffic is considered validated.

## Smoke Checklist

- `python manage.py check` passes.
- `python manage.py check --deploy` is reviewed in production-like settings.
- `python manage.py deployment_smoke --strict` passes in production-like settings.
- `python manage.py deployment_smoke --json` emits only safe keys and values.
- `/health/` returns safe liveness.
- `/health/ready/` returns safe readiness through the private/internal path.
- Public booking pages render.
- Staff appointment pages require authentication and staff status.
- Smoke output does not print secrets, database connection strings, cache connection strings, passwords, tokens, cookies, or raw environment dumps.
- Smoke output does not print patient names, emails, phone numbers, appointment
  tokens, or patient data.
- Smoke output includes public booking, patient portal, project consolidation,
  and prohibited-feature summaries.
- `python manage.py project_status_report` and
  `python manage.py project_status_report --json` remain read-only and print
  counts, booleans, and route/security categories only.

## Batch 10 Route, Security, and Staging Gates

- `docs/PROJECT_MAP.md` is current for apps, modules, tests, and commands.
- `docs/ROUTE_ACCESS_MATRIX.md` is current for implemented and prohibited routes.
- `docs/DATA_EXPOSURE_MATRIX.md` is current for patient-safe, staff-only,
  internal-only, and never-on-patient-page fields.
- `docs/STAGING_VALIDATION_PLAN.md` is followed before claiming staging
  readiness.
- `docs/FIGMA_DESIGN_HANDOFF.md` is followed before any future visual change.
- Public booking remains login-free.
- Public booking success remains UUID `public_token` based.
- Numeric public appointment success URLs remain 404.
- Staff appointment operations require authenticated staff.
- Patient appointment detail requires authenticated ownership filtering.
- Patient account/dashboard pages do not expose raw appointment public tokens
  except where an explicit linking/detail flow requires a UUID URL.
- Portal pages remain no-cache.
- Account recovery remains GET-only/static.
- Seed commands do not create patients or appointments.
- Upload, medical-record, WhatsApp API/webhook, and payment routes remain 404.

## Batch 11 CI and Local Validation Gates

- CI remains local-only and does not require external PostgreSQL, Redis, Docker,
  DNS, TLS, cloud resources, or secrets.
- CI runs `python manage.py makemigrations --check --dry-run`.
- CI runs `python manage.py check`.
- CI runs `python manage.py check --deploy`; local development warnings are
  reviewed as warnings and do not prove production readiness.
- CI applies local SQLite migrations for smoke validation.
- CI runs `python manage.py deployment_smoke`.
- CI runs `python manage.py deployment_smoke --json`.
- CI runs `python manage.py project_status_report`.
- CI runs `python manage.py project_status_report --json`.
- CI runs `python manage.py production_settings_report`.
- CI runs `python manage.py production_settings_report --json`.
- CI runs `python manage.py test`.
- Batch 11 validation scripts remain operator-run harnesses and do not deploy,
  commit, push, merge, or provision resources.
- `docker-compose.staging-validation.yml` is local-only and not a CI service.

## Rollback Checklist

- Last known good revision is identified.
- Database migration rollback strategy is reviewed before use.
- Restore from backup is available if data integrity is affected.
- Staff and patient-facing impact is communicated through approved channels.
- Rollback validation includes `check`, `check --deploy`, and `deployment_smoke --strict`.

## Monitoring Checklist

- Application logs are collected.
- Request errors are visible.
- Security warnings are visible.
- Backup failures alert an operator.
- `/health/` uptime monitoring is configured.
- `/health/ready/` private readiness monitoring is configured.
- Error reporting, if added later, has privacy scrubbing before activation.
- Alert routing is tested.
- Slow public HTTP 200 responses trigger warning/critical policy through the
  approved provider; HTTP 200 alone is not treated as readiness.
- Monitoring provider readiness is not claimed from repository-native staging
  GET evidence alone.
- Alert routing readiness is not claimed until primary and backup routes are
  tested.
- Privacy-safe error reporting readiness is not claimed until a scrubbed
  synthetic event is reviewed.
- Production latency readiness is not claimed from one fast manual check
  window. Historical severe public latency must be measured through approved
  monitoring and addressed by an owner/operator decision.

## Post-Deploy Checklist

- Smoke checks passed after deployment.
- Error rate is normal.
- Public pages render.
- Public booking flow loads through confirmation without creating test patient data in production.
- Staff appointment list/detail access rules are intact.
- No unexpected routes are exposed.
- Release notes and incident timeline are updated if anything failed.

## Patient Portal Account Security Gates

- patient portal remains bounded to account security, linked-appointment
  viewing, and read-only approved medical-record visibility
- logged-in password change uses Django validation/hashing and keeps the session valid after success
- email password reset is not implemented unless production email ownership and recovery policy are approved
- account recovery is clinic-assisted and informational only for now
- public booking still works without login
- portal appointment access uses UUID `public_token` URLs and authenticated ownership checks
- appointment linking requires `public_token` plus matching booking phone
- portal pages are no-cache
- portal login, registration, password change, and appointment linking keep CSRF protection
- portal rate limits use hashed identities and do not store raw public tokens, raw phone numbers, or passwords in cache keys
- no patient-facing uploads until private media design and access control are
  approved for that surface
- no WhatsApp until consent/logging/cost/security design exists
- patient-facing medical records are limited to read-only doctor/staff-approved
  visits, notes, and active patient-visible media for the linked authenticated
  patient only
- BATCH-16-DELIVERY-01 adds model/admin/test groundwork for patient records;
  BATCH-16-DELIVERY-02 adds private storage plus staff-only private media
  download access; BATCH-16-DELIVERY-03 adds the approved read-only patient
  visibility route and patient-owned media route; BATCH-16-DELIVERY-04 adds
  approved public cases/achievements display only for active public-case media
  with confirmed consent through controlled public routes.
- no payments until a payment provider, privacy, refund, and reconciliation policy is reviewed

These gates are intentional blockers for future batches beyond the Batch 9 portal account-security polish.
