# Project Release Scorecard

Batch 10 release-readiness scorecard for Dr. Khaled Badran Clinic after the
Batch 10 consolidation work.

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
| Public site | Partial | Bilingual public pages, legal drafts, SEO basics, PWA foundation, and safe placeholder content exist. Final visual approval, legal review, real content verification, hosting, static strategy, monitoring, and production validation remain. |
| Public booking | Partial | Login-free booking, slot generation, UUID success URLs, rate limits, no-cache confirmation/success, and regression tests exist. Staging PostgreSQL/Redis validation and load/concurrency tests remain. |
| Staff operations | Partial | Staff-only appointment list/detail and bounded status operations exist with authorization and tests. Broader dashboard, staff access review, audit retention, and operational policies remain. |
| Patient portal | Partial | Optional account, login, logout, password change, account summary, static recovery policy, appointment linking, and linked appointment viewing exist. Identity verification, secure recovery process, abuse monitoring, legal review, and staging validation remain. |
| Account security | Partial | Password hashing/validation, CSRF, POST-only logout, no-cache portal pages, generic linking errors, and rate limits exist. Email/phone ownership, recovery operations, production tuning, and abuse monitoring remain. |
| Production settings | Partial | Split settings, production checks, secure-cookie defaults, PostgreSQL/Redis support, and environment docs exist. Real hosting, TLS, proxy, database, cache, backups, monitoring, and scanning remain. |
| Deployment smoke | Done | Safe smoke command exists with human/JSON/strict modes, route/security summaries, prohibited-feature checks, and redaction rules. It does not deploy or prove infrastructure readiness by itself. |
| Staging readiness | Partial | Staging validation plan and operational runbooks exist. Actual restricted staging infrastructure has not been provisioned or validated. |
| Privacy/legal | Blocked | Draft pages and privacy matrices exist. Formal legal/privacy review, retention/deletion policy, recovery policy, and patient identity verification are required before launch. |
| Monitoring | Not Started | Health/readiness endpoints and logging foundation exist, but no real monitoring, uptime checks, alert routing, error reporting, or abuse alerts are configured. |
| Design/Figma | Blocked | Current code has existing visual foundation from earlier batches. Future visual changes require Figma handoff and approval before Codex implementation. |
| Uploads | Out of Scope for Now | No upload routes or private media handling are implemented. Private storage, malware scanning, retention, access control, and legal design are required first. |
| Medical records | Out of Scope for Now | No medical-record routes or models are implemented. Authorization, audit, retention, patient visibility, legal, and clinical workflows are required first. |
| WhatsApp | Out of Scope for Now | No WhatsApp API sending, webhook, message model, or credential use is implemented. Consent, security, logging, provider, and medical-information boundaries are required first. |
| Payments | Out of Scope for Now | No payment routes or payment provider integration are implemented. Provider, refund, reconciliation, privacy, and accounting policy are required first. |

## Conservative Completion Estimate

Estimated whole-project completion after successful Batch 10:

- Approximately 68-70%.

Rationale:

- The public site, booking, staff appointment operations, and bounded patient
  portal foundations are implemented and locally tested.
- Batch 10 improves reviewability, route inventory, data exposure documentation,
  staging readiness, smoke safety, and regression coverage.
- The estimate remains below launch-ready because real staging/prod
  infrastructure, legal/privacy approval, monitoring, backup/restore drill,
  security scanning, load testing, and Figma-approved future design governance
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

## Do Not Launch Publicly Until

- Restricted staging with PostgreSQL and Redis/shared cache passes validation.
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
- Legal/privacy review is complete.
- Patient identity verification policy is approved.
- Secure account recovery policy is approved.
- Staff/admin access review and offboarding policy are defined.
- Audit retention policy is defined.
- Static serving strategy is chosen and tested.
- Figma-approved visual changes, if any, are implemented and verified.

## Remaining Launch Blockers

- No real staging infrastructure has been validated.
- No production hosting, DNS, TLS, or reverse proxy exists in this repo.
- No PostgreSQL/Redis staging validation has been completed.
- No backup/restore drill has been completed.
- No monitoring/error reporting is configured.
- No legal/privacy approval is recorded.
- No verified email/phone ownership policy is approved.
- No secure account recovery operation is approved.
- No production rate-limit tuning has been completed.
- No load/concurrency test results exist.
- No dependency vulnerability scanning workflow is configured.
- No staff access review process is defined.
- No audit retention/access review policy is defined.
- No Figma handoff exists for future visual changes.

## Recommended Next 5 Batches

1. Restricted staging validation with PostgreSQL, Redis/shared cache, HTTPS,
   reverse proxy review, `check --deploy`, `deployment_smoke --strict`, seed
   commands, and synthetic backup/restore drill.
2. Legal/privacy and account recovery policy batch: verified email/phone
   ownership, patient identity verification, retention/deletion process, privacy
   copy review workflow, and no new patient data surfaces.
3. Monitoring and abuse operations batch: uptime checks, structured safe log
   review, alert routing, portal/booking abuse monitoring, dependency scanning,
   and incident exercise using synthetic data.
4. Figma-approved design implementation batch: implement only approved Figma
   tokens/components/responsive behavior, with no independent Codex visual
   design decisions.
5. Staff operations hardening batch: least-privilege staff/admin review,
   operational audit retention policy, appointment correction workflow design,
   and staff runbook refinement without adding medical records or uploads.

## Design Status

- Figma required for future visual changes.
- Codex must not invent colors, spacing, typography, visual hierarchy,
  animations, decorative elements, brand style, shadows, borders, or hover
  effects.
- Batch 10 status: No visual design work performed by Codex.
