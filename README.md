# عيادة الدكتور خالد بدران / Dr. Khaled Badran Clinic

نظام وموقع عيادة ثنائي اللغة عربي/إنجليزي لعيادة الدكتور خالد بدران، مبني مبدئيًا على Django + PostgreSQL + Django Templates + HTMX + Alpine.js + Tailwind CSS + PWA.

## Project Type

Web + PWA clinic system, not a generic website and not a full hospital EMR.

## Scope Summary

- Public bilingual website: Arabic/English.
- Warm premium medical design inspired by the real clinic interior.
- Fast online booking.
- Visit types managed from dashboard.
- Appointment schedules managed later from dashboard.
- WhatsApp Business integration for menu, booking entry, appointment confirmation, reminders, and patient inquiries.
- Default appointment reminder: 3 hours before appointment, editable from dashboard.
- Patient portal.
- Simplified medical record.
- Private file uploads and WhatsApp media intake.
- Doctor/admin dashboard.
- Privacy, consent, publication approval, and deletion-request workflows.

## Official Clinic Name

Arabic: `عيادة الدكتور خالد بدران`

English: `Dr. Khaled Badran Clinic`

## Current Doctor Scope

Only Dr. Khaled Hassan Badran is in scope for the initial version. No second doctor is included in the current project scope.

## Key Documents

- `docs/PROJECT_SPECIFICATION_AR.md` — Arabic project specification.
- `docs/DECISIONS.md` — locked decisions and open decisions.
- `docs/CODEX_BUILD_PLAN.md` — phased implementation plan for Codex CLI.
- `docs/CODEX_START_HERE.md` — Codex CLI starting instructions.
- `docs/NEXT_BATCH.md` — current recommended implementation batch.

- `docs/ENVIRONMENT.md` - environment variables and local/production settings behavior.
- `docs/PRODUCTION_READINESS.md` - current deployment-readiness status and known gaps.
- `docs/DEPLOYMENT_CHECKLIST.md` - future deployment checklist; no deployment has been performed.
- `docs/SECURITY_HARDENING.md` - Batch 6 security posture and remaining security work.
- `docs/BATCH_6_STATUS.md` - production-readiness batch status.
- `docs/BACKUP_RESTORE_RUNBOOK.md` - backup, restore, retention, and restore-drill expectations.
- `docs/BACKUP_RESTORE_DRILL.md` - Batch 11 synthetic-only backup and restore drill procedure.
- `docs/INCIDENT_RESPONSE_RUNBOOK.md` - incident severity, containment, recovery, and review outline.
- `docs/RELEASE_CHECKLIST.md` - local/staging/production release validation checklist and pre-portal gates.
- `docs/LOAD_TEST_PLAN.md` - staging-only load and concurrency test plan.
- `docs/SECURITY_REGRESSION_CHECKLIST.md` - security regression checklist for booking, staff, proxy, and smoke gates.
- `docs/BATCH_7_STATUS.md` - staging-readiness validation batch status.
- `docs/BATCH_8_STATUS.md` - patient portal foundation status.
- `docs/BATCH_9_STATUS.md` - portal account security and patient portal polish status.
- `docs/PROJECT_MAP.md` - current app/module/test/command inventory.
- `docs/ROUTE_ACCESS_MATRIX.md` - route access, CSRF, cache, ownership, and prohibited route matrix.
- `docs/DATA_EXPOSURE_MATRIX.md` - public, portal, staff-only, internal, and never-on-patient-page data boundaries.
- `docs/STAGING_VALIDATION_PLAN.md` - production-like restricted staging validation plan.
- `docs/STAGING_GAP_ANALYSIS.md` - Batch 11 gap analysis against the staging validation plan.
- `docs/STAGING_ENVIRONMENT_CONTRACT.md` - required staging environment variable contract without secret values.
- `docs/LOCAL_STAGING_SIMULATION.md` - optional local-only PostgreSQL/Redis service harness for validation.
- `docs/POSTGRESQL_READINESS.md` - PostgreSQL migration, constraint, and concurrency validation plan.
- `docs/REDIS_RATE_LIMIT_READINESS.md` - Redis/shared-cache rate-limit readiness and cache-key privacy plan.
- `docs/MONITORING_ALERTING_READINESS.md` - health, alerting, logging, and abuse monitoring readiness plan.
- `docs/DEPENDENCY_SECURITY_READINESS.md` - dependency scanning and update governance plan.
- `docs/STAFF_ACCESS_GOVERNANCE.md` - staff/admin least-privilege and access review plan.
- `docs/LEGAL_PRIVACY_OPERATIONS.md` - legal/privacy operations and review blockers.
- `docs/FIGMA_DESIGN_HANDOFF.md` - Figma source-of-truth rule for future visual changes.
- `docs/PROJECT_RELEASE_SCORECARD.md` - conservative release-readiness scorecard and next batches.
- `docs/BATCH_10_STATUS.md` - Batch 10 consolidation summary.
- `docs/BATCH_11_STATUS.md` - Batch 11 restricted staging validation operations summary.

## Development Policy

Work must be delivered in small auditable batches. Do not ask Codex or any AI agent to implement the entire system in one step.

## Design Governance

Figma is the source of truth for visual design. Codex must not invent or independently change colors, spacing systems, typography systems, visual hierarchy, animations, decorative elements, shadows, borders, hover effects, brand style, or layout density. Future visual changes require an approved Figma handoff before implementation. See `docs/FIGMA_DESIGN_HANDOFF.md`.

Design approval cannot bypass security or privacy requirements. Public booking, UUID-only public success URLs, staff-only appointment operations, CSRF, portal no-cache behavior, patient ownership filtering, and prohibited feature boundaries must remain intact.

Recommended order:

1. Repository audit and foundation.
2. Django project foundation.
3. Public website and design system.
4. Booking system.
5. Patient portal and records.
6. WhatsApp integration.
7. Dashboard.
8. Privacy/consent/deletion workflows.
9. Tests, security hardening, and deployment preparation.

## Local Development Commands

Install dependencies in an activated Python environment:

```bash
python -m pip install -r requirements.txt
```

Run Django checks and tests:

```bash
python manage.py check
python manage.py test
```

Run the safe local deployment smoke check:

```bash
python manage.py deployment_smoke
```

Run the safe read-only project status report:

```bash
python manage.py project_status_report
python manage.py project_status_report --json
```

Run the safe read-only production-like settings report:

```bash
python manage.py production_settings_report
python manage.py production_settings_report --json
```

Run the Batch 11 local validation script from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/validate_local_release.ps1
```

Run the Batch 11 local validation script from Bash when Bash is available:

```bash
bash scripts/validate_local_release.sh
```

Run the Batch 11 restricted staging environment validation script only from a
trusted operator shell with staging environment variables set outside Git:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/validate_staging_env.ps1 -Strict -Json
```

```bash
bash scripts/validate_staging_env.sh --strict --json
```

These scripts do not deploy, commit, push, merge, provision resources, or print
environment secret values. They are validation harnesses only.

Seed safe public clinic content:

```bash
python manage.py seed_public_content
```

Seed safe local booking demo setup:

```bash
python manage.py seed_booking_demo
```

Run the local development server:

```bash
python manage.py runserver
```

## Environment and Production Readiness

Local development uses `config.settings.dev` by default through `manage.py`.

Local defaults:

- Empty `DATABASE_URL` uses `db.sqlite3`.
- Empty `CACHE_URL` uses Django LocMemCache.
- `DJANGO_DEBUG` defaults to true in development settings.
- HTTPS redirect, HSTS, and secure cookies are disabled for local simplicity.
- `BOOKING_TRUST_X_FORWARDED_FOR` is false by default.

Production uses `config.settings.prod`.

Staging should also use `config.settings.prod` unless a future reviewed staging wrapper is added. Staging must be production-like but non-public or access-restricted, with its own generated application secret, exact allowed hosts, CSRF trusted HTTPS origins, PostgreSQL, shared Redis/cache, HTTPS, no real patient data, and secure uncommitted admin credentials. Staging setup should use only `seed_public_content` and `seed_booking_demo` for clinic/public/booking demo data.

Production behavior:

- `DJANGO_SECRET_KEY` is required and must be environment-driven.
- `DJANGO_DEBUG` is environment-driven and defaults to false.
- `DJANGO_ALLOWED_HOSTS` is required and environment-driven.
- `DJANGO_CSRF_TRUSTED_ORIGINS` is environment-driven.
- `DATABASE_URL` is required and should point to PostgreSQL.
- `CACHE_URL` should point to a shared cache such as Redis for rate limiting.
- HTTPS redirect, secure cookies, and HSTS are enabled by default only in production settings.
- `SECURE_PROXY_SSL_HEADER` is enabled only when `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true`.
- `BOOKING_TRUST_X_FORWARDED_FOR` remains false unless a trusted reverse proxy strips client-supplied `X-Forwarded-For`.

Batch 6 added production-readiness checks for unsafe production combinations:

- `DEBUG=True`.
- Missing/placeholder `SECRET_KEY`.
- Empty or wildcard `ALLOWED_HOSTS`.
- Empty `CSRF_TRUSTED_ORIGINS`.
- LocMemCache in production.
- SQLite in production.
- Trusted forwarded IPs without proxy attestation.

Health endpoints:

- `/health/` is a public liveness endpoint with no internals.
- `/health/ready/` is a readiness endpoint intended for private/internal monitoring; it checks database connectivity and returns no detailed failures.

This project is not deployed and is not fully launch-ready. Remaining launch work includes real hosting, TLS/proxy setup, PostgreSQL and Redis provisioning, backups and restore drills, monitoring/error reporting, legal/privacy review, static serving strategy, private media design before uploads, vulnerability scanning, and load testing. See `docs/PRODUCTION_READINESS.md` and `docs/DEPLOYMENT_CHECKLIST.md`.

## Current Status and Next Steps

After Batch 11, the project has restricted staging validation operations,
production-like settings reporting, local validation scripts, a local-only
PostgreSQL/Redis service harness, backup/restore drill planning, monitoring and
alerting readiness documentation, dependency governance, staff access
governance, legal/privacy operations documentation, strengthened CI release
gates, and expanded security regressions.

Current safe demo scope remains limited to synthetic data:

- public bilingual pages,
- login-free public booking,
- UUID public booking success,
- bounded staff appointment operations,
- optional patient portal account/login/password/account recovery policy,
- patient appointment linking and linked appointment viewing.

Still not launch-safe:

- real staging/prod infrastructure has not been validated,
- legal/privacy review is not complete,
- monitoring and alerting are not configured,
- backup/restore drills have not been completed,
- production rate limits have not been tuned against Redis/shared cache,
- uploads, medical records, WhatsApp API/webhooks, payments, diagnosis, triage,
  treatment automation, and medical AI remain absent.

Recommended next batch: execute a restricted, non-public staging validation
against real PostgreSQL, Redis/shared cache, HTTPS/reverse proxy settings,
synthetic seed data, monitoring/error-reporting placeholders, dependency scan
evidence, and a synthetic backup/restore drill. That work must remain
restricted and must not launch the site publicly.

Deployment smoke command:

- `python manage.py deployment_smoke` runs safe startup, database, migration, cache, public-content, booking-settings, health import, readiness, public-booking safety, and patient-portal account-security route-summary checks.
- `python manage.py deployment_smoke --json` emits safe machine-readable JSON.
- `python manage.py deployment_smoke --strict` is intended for staging/production-like validation and fails on hard failures or strict staging/production blockers.
- The command does not print application secrets, database connection strings, cache connection strings, passwords, tokens, cookies, or raw environment dumps.

Useful local public pages:

- Arabic home: `http://127.0.0.1:8000/`
- Arabic doctor: `http://127.0.0.1:8000/doctor/`
- Arabic services: `http://127.0.0.1:8000/services/`
- Arabic contact: `http://127.0.0.1:8000/contact/`
- Arabic booking: `http://127.0.0.1:8000/book/`
- Arabic booking visit type: `http://127.0.0.1:8000/book/visit-type/`
- Arabic booking slots: `http://127.0.0.1:8000/book/slots/`
- Arabic booking confirm: `http://127.0.0.1:8000/book/confirm/`
- Arabic booking success: `http://127.0.0.1:8000/book/success/<public-token>/`
- Arabic patient portal: `http://127.0.0.1:8000/portal/`
- Arabic patient portal login: `http://127.0.0.1:8000/portal/login/`
- Arabic patient account: `http://127.0.0.1:8000/portal/account/`
- Arabic patient password change: `http://127.0.0.1:8000/portal/password/change/`
- Arabic patient account recovery policy: `http://127.0.0.1:8000/portal/account-recovery/`
- Arabic patient appointment linking: `http://127.0.0.1:8000/portal/link-appointment/`
- English home: `http://127.0.0.1:8000/en/`
- English doctor: `http://127.0.0.1:8000/en/doctor/`
- English services: `http://127.0.0.1:8000/en/services/`
- English contact: `http://127.0.0.1:8000/en/contact/`
- English booking: `http://127.0.0.1:8000/en/book/`
- English booking visit type: `http://127.0.0.1:8000/en/book/visit-type/`
- English booking slots: `http://127.0.0.1:8000/en/book/slots/`
- English booking confirm: `http://127.0.0.1:8000/en/book/confirm/`
- English booking success: `http://127.0.0.1:8000/en/book/success/<public-token>/`
- English patient portal: `http://127.0.0.1:8000/en/portal/`
- English patient portal login: `http://127.0.0.1:8000/en/portal/login/`
- English patient account: `http://127.0.0.1:8000/en/portal/account/`
- English patient password change: `http://127.0.0.1:8000/en/portal/password/change/`
- English patient account recovery policy: `http://127.0.0.1:8000/en/portal/account-recovery/`
- English patient appointment linking: `http://127.0.0.1:8000/en/portal/link-appointment/`
- Staff appointment list: `http://127.0.0.1:8000/staff/appointments/`
- Staff appointment detail: `http://127.0.0.1:8000/staff/appointments/<appointment-id>/`
- Legal pages: `/privacy/`, `/terms/`, `/medical-disclaimer/`, `/whatsapp-policy/`
- SEO basics: `/robots.txt`, `/sitemap.xml`

Booking safety boundaries:

- Public booking creates confirmed appointments without requiring login.
- The current public scope resolves the active doctor automatically.
- Public success pages use non-enumerable UUID public tokens, not numeric appointment IDs.
- Public success pages may show appointment time, doctor, visit type, patient name, and a short confirmation reference.
- Public success pages must not show internal notes, audit logs, internal IDs, private medical data, staff-only fields, or future medical-record data.
- Staff appointment pages require an authenticated active user with `is_staff=True`.
- Anonymous users are redirected to the admin login before staff appointment pages load.
- Authenticated non-staff users receive 403 for staff appointment pages and staff operations.
- Staff appointment operations are intentionally bounded to booking list/detail, cancel, reschedule, arrived, complete, and no-show workflows.
- Staff operations use internal numeric appointment IDs only behind staff-only authorization; public appointment confirmation remains UUID token based.
- Rescheduled appointments keep the same database row and `public_token`; the appointment status becomes `rescheduled`, which is treated as an active operational status.
- Terminal booking statuses are `completed`, `cancelled`, and `no_show`; restore/undo is intentionally not implemented until a reviewed correction workflow exists.
- Public booking POSTs have lightweight Django-cache rate limiting by IP and normalized phone hash.
- No WhatsApp API sending or webhook is implemented.
- Patient portal foundation is implemented as an optional account, login, password change, account summary, clinic-assisted recovery policy, appointment linking, and appointment viewing flow only.
- No patient uploads, online payments, medical records, WhatsApp API/webhook integration, or medical automation are implemented.
- Demo seed commands do not create real patients or appointments.

## Patient Portal Foundation and Account Security

Patient portal routes:

- `GET /portal/` dashboard for authenticated patients.
- `GET|POST /portal/login/` phone/password login using Django authentication.
- `POST /portal/logout/` logout with CSRF protection.
- `GET|POST /portal/register/` optional patient account registration.
- `GET /portal/account/` authenticated account summary.
- `GET|POST /portal/password/change/` authenticated password change.
- `GET /portal/account-recovery/` static clinic-assisted recovery policy.
- `GET|POST /portal/link-appointment/` appointment linking.
- `GET /portal/appointments/` linked appointment list.
- `GET /portal/appointments/<public-token>/` linked appointment detail.
- English equivalents exist under `/en/portal/`.

Portal behavior:

- The portal is optional. Public booking still works without login.
- Patient accounts use Django's built-in password hashing.
- Logged-in patients can change their password with Django password validation and hashing.
- Successful password changes keep the current session valid with Django session hash rotation.
- The login username is the normalized phone number captured at registration.
- Registration collects full name, phone, optional email, password, and password confirmation.
- The account page shows display name, masked username/phone, optional email, and linked appointment count only.
- Phone and email updates require clinic support for now; no self-service contact editing is implemented in this batch.
- Account recovery is clinic-assisted for now. Email password reset is not implemented because no safe production email ownership and delivery policy is configured yet.
- Appointment linking requires a logged-in account, the appointment `public_token`, and a phone number matching the appointment patient's normalized phone.
- If the token is missing, wrong, nonexistent, or the phone does not match, the portal uses a generic error and does not link the appointment.
- If the appointment patient is already linked to another user, the portal blocks linking with the same generic error.
- If the appointment is already linked to the same user, linking is a safe no-op.
- Appointment linking, login, and registration have lightweight Django-cache rate limits by IP and, where practical, normalized phone hash.
- Patient portal pages are marked no-cache.
- Portal navigation consistently links to dashboard, appointments, link appointment, account, change password, and POST-only logout.

Patient-visible appointment fields are limited to:

- visit type,
- appointment date/time,
- patient-safe status label,
- doctor display name,
- clinic name/address,
- created date.

Patient-visible account fields are limited to:

- display name,
- masked username/phone,
- email if provided,
- linked appointment count.

The portal does not show:

- internal appointment IDs,
- staff notes,
- booking notes,
- doctor internal notes,
- status history notes,
- audit logs,
- medical records,
- uploads or private media,
- WhatsApp messages,
- payment administration details.

Remaining production needs before a public patient portal launch:

- verified email or phone ownership policy,
- secure account recovery process beyond the current clinic-assisted placeholder,
- patient identity verification policy,
- privacy/legal review,
- production rate-limit tuning against Redis/shared cache,
- abuse monitoring and alerting,
- staging validation with PostgreSQL and Redis/shared cache.

## Staff Booking Operations

Staff booking operations added in Batch 5:

- `GET /staff/appointments/` lists appointments with filters for status, range, doctor, visit type, date range, and patient name/phone search.
- `GET /staff/appointments/<appointment-id>/` shows staff-only appointment detail, status history, audit events, and operation forms.
- `POST /staff/appointments/<appointment-id>/cancel/` cancels a confirmed, arrived, or rescheduled appointment. A cancellation note is required.
- `POST /staff/appointments/<appointment-id>/reschedule/` moves a confirmed or rescheduled appointment to a validated available slot. The same `public_token` is preserved.
- `POST /staff/appointments/<appointment-id>/arrived/` marks a confirmed or rescheduled appointment as arrived.
- `POST /staff/appointments/<appointment-id>/complete/` marks an arrived appointment as completed.
- `POST /staff/appointments/<appointment-id>/no-show/` marks a confirmed or rescheduled appointment as no-show. A no-show note is required.

Audit policy:

- Public booking creation writes an `AuditLog` entry and initial `AppointmentStatusHistory`.
- Staff cancel/reschedule/arrived/complete/no-show operations write `AppointmentStatusHistory` and `AuditLog` entries.
- Audit metadata stores operational identifiers and short operational notes only: internal appointment ID, public token, old/new status, old/new start times, actor user ID, and a trimmed operation note.
- Audit logs and status history are visible on staff detail pages only.

Rate limiting:

- `booking_post_rate_limit_per_hour` defaults to `10` public booking POST attempts per IP per hour.
- `booking_phone_rate_limit_per_day` defaults to `5` public booking attempts per normalized phone per day.
- Patient portal login, registration, and appointment-link throttles use Django cache with hashed identities. Defaults are intentionally light for local development and must be tuned in staging/production.
- Public booking IP rate limits trust `REMOTE_ADDR` by default.
- `X-Forwarded-For` is ignored unless `BOOKING_TRUST_X_FORWARDED_FOR=True` is explicitly set in Django settings.
- In production, enable `BOOKING_TRUST_X_FORWARDED_FOR` only when Django is behind a trusted reverse proxy that strips untrusted incoming `X-Forwarded-For` headers.
- Cache keys hash IP/phone identities and do not store raw phone numbers in cache keys.
- Staff operations are not rate limited by the public booking guard.

Database and concurrency hardening:

- `Appointment.public_token` remains the only public success lookup.
- Appointment operations use `transaction.atomic()`.
- Staff rescheduling revalidates schedule availability, closed days, min lead time, max days ahead, inactive doctor/visit type, exact duplicates, and overlaps.
- Duplicate exact active slots are protected by a conditional unique constraint on `doctor + starts_at` for active statuses: `confirmed`, `arrived`, and `rescheduled`.
- Useful appointment operation indexes include `doctor + starts_at`, `doctor + status + starts_at`, `status + starts_at`, `patient + starts_at`, `starts_at`, and the unique/indexed `public_token`.

## Production Hardening Checklist

- HTTPS and HSTS configured at the edge and in Django production settings.
- Secure cookies enabled: `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, and appropriate SameSite settings.
- CSRF trusted origins configured for production domains.
- `ALLOWED_HOSTS` locked to production domains.
- `DJANGO_SECRET_KEY` stored outside Git with a documented rotation policy.
- PostgreSQL used for production with tested migrations.
- Database connection pooling planned and tested.
- Automated database backups configured.
- Restore drills completed and scheduled.
- Shared production cache backend configured for rate limiting.
- Rate limit behavior tested against the shared cache backend.
- `BOOKING_TRUST_X_FORWARDED_FOR` left disabled unless a trusted reverse proxy strips untrusted incoming `X-Forwarded-For`.
- Backup and restore policy documented and tested.
- Structured application logging enabled.
- Monitoring and uptime checks configured.
- Error reporting configured without leaking patient data.
- Static files served through a production static pipeline or CDN.
- Media/private storage designed before uploads are implemented.
- No sensitive medical files cached publicly.
- Audit retention and access review policy defined.
- Least-privilege admin/staff accounts configured and reviewed.
- Data protection and legal review completed before launch.
- Load testing completed before launch.
- Dependency update policy defined.
- Vulnerability scanning configured.
- Incident response and secret-rotation notes documented.
