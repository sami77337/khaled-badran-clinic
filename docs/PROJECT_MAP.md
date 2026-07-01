# Project Map

Batch 10 consolidation snapshot for Dr. Khaled Badran Clinic.

This document describes the current implemented project shape after Batch 9.
It does not approve new patient medical features. Figma remains the source of
truth for visual design; this map is operational and security documentation
only.

## Installed Local Django Apps

The local apps installed in `config/settings/base.py` are:

| App | Current responsibility |
| --- | --- |
| `apps.core` | Shared public-site views, health/readiness views, system settings, audit log model, production-readiness checks, and deployment smoke command. |
| `apps.clinic` | Clinic profile, doctor, visit type, doctor schedule, closed day models, admin registration, and safe public-content seed command. |
| `apps.accounts` | Placeholder installed app for future account-specific expansion. It has no custom model or route surface in the current implementation. |
| `apps.booking` | Public booking flow, slot generation, phone normalization, booking rate limits, appointment model, status history, staff appointment operations, audit helper, and safe booking demo seed command. |
| `apps.patients` | Patient model, optional portal registration/login/logout, password change, account summary, clinic-assisted account recovery policy, appointment linking, linked appointment list/detail, and portal rate limits. |
| `apps.records` | Placeholder installed app. No medical-record model, view, URL, upload, or patient data surface is implemented. |
| `apps.whatsapp` | Placeholder installed app. No WhatsApp API sending, webhook, message model, or credential use is implemented. |
| `apps.dashboard` | Placeholder installed app. No broad dashboard UI is implemented beyond the bounded staff appointment operation routes in `apps.booking`. |
| `apps.legal` | Placeholder installed app for legal-page ownership. Current legal pages are rendered by `apps.core.views` using `templates/legal/`. |

## Public Website Modules

Implemented modules:

- `config/urls.py` defines Arabic/default and English public routes.
- `apps/core/views.py` renders home, doctor, services, contact, legal pages,
  `robots.txt`, `sitemap.xml`, `/health/`, and `/health/ready/`.
- `templates/core/` contains public content templates.
- `templates/legal/` contains legal/privacy/disclaimer policy templates.
- `templates/partials/` contains shared semantic template pieces.
- `static/img/placeholders/` and `static/img/icons/` contain existing safe local
  placeholder assets.
- `static/js/site.js`, `static/sw.js`, and `static/site.webmanifest` support the
  existing static/PWA foundation.

Current public website behavior:

- Arabic is the default language.
- English routes live under `/en/`.
- Public content can show public clinic, doctor, service, and legal draft
  information only.
- Public pages must not show internal IDs, audit logs, staff notes, private
  medical data, uploads, WhatsApp messages, payment details, or staff operation
  controls.

## Booking Modules

Implemented modules:

- `apps/booking/models.py`
  - `Appointment`
  - `AppointmentStatusHistory`
- `apps/booking/services.py`
  - booking settings lookup,
  - slot generation,
  - closed-day checks,
  - overlap checks,
  - public appointment creation,
  - active appointment status constants.
- `apps/booking/forms.py`
  - public booking form,
  - staff note/cancel/no-show/reschedule forms.
- `apps/booking/selectors.py`
  - active doctor and visit type selectors.
- `apps/booking/phone.py`
  - Jordan-first phone normalization.
- `apps/booking/rate_limits.py`
  - cache-backed public booking IP and phone quotas.
- `apps/booking/audit.py`
  - bounded appointment audit metadata.
- `apps/booking/views.py`
  - public booking flow,
  - public UUID success view,
  - staff-only operation views.
- `templates/booking/`
  - public booking templates,
  - staff appointment templates.

Current booking behavior:

- Public booking does not require login.
- Public appointment success uses `Appointment.public_token` UUID routes only.
- Numeric public appointment success URLs are not routed.
- Public booking creates `Patient` and `Appointment` records only on valid final
  confirmation.
- Public booking POSTs are rate limited by IP and normalized phone hash through
  Django cache.
- Booking success may show patient name, doctor, visit type, appointment time,
  and a short confirmation reference derived from the UUID.

## Staff Appointment Operations

Implemented in `apps/booking/views.py`, `apps/booking/operations.py`, and
`templates/booking/staff/`.

Routes:

- `GET /staff/appointments/`
- `GET /staff/appointments/<appointment-id>/`
- `POST /staff/appointments/<appointment-id>/cancel/`
- `POST /staff/appointments/<appointment-id>/reschedule/`
- `POST /staff/appointments/<appointment-id>/arrived/`
- `POST /staff/appointments/<appointment-id>/complete/`
- `POST /staff/appointments/<appointment-id>/no-show/`

Current access model:

- Anonymous users redirect to Django admin login.
- Authenticated users require `is_staff=True`.
- Authenticated non-staff users receive `403`.
- Staff operation POSTs use CSRF protection.
- Staff numeric appointment IDs remain behind staff authorization only.
- Staff pages may show status history, audit logs, internal appointment IDs,
  operational notes, and patient contact search fields.

Staff operations are intentionally bounded to appointment list/detail and status
operations. They are not a broad dashboard.

## Patient Portal Modules

Implemented modules:

- `apps/patients/models.py`
  - `Patient`
- `apps/patients/forms.py`
  - phone/password login,
  - registration,
  - appointment linking.
- `apps/patients/services.py`
  - patient display helpers,
  - masked identifiers,
  - patient appointment querysets,
  - patient-safe status labels,
  - appointment linking service.
- `apps/patients/rate_limits.py`
  - cache-backed portal login, registration, and appointment-link rate limits.
- `apps/patients/views.py`
  - portal dashboard,
  - login,
  - POST-only logout,
  - registration,
  - account summary,
  - password change,
  - static account recovery policy,
  - appointment linking,
  - appointment list/detail.
- `templates/patients/`
  - bounded portal templates.

Current portal behavior:

- Portal accounts are optional.
- Public booking still works without login.
- Appointment detail uses UUID `public_token` URLs plus authenticated ownership
  filtering.
- Appointment linking requires a public token and matching booking phone.
- User A cannot view User B's linked appointment.
- Portal pages are marked no-cache.
- Portal pages must not show internal IDs, staff notes, booking notes, status
  history notes, audit logs, medical records, uploads, WhatsApp messages,
  payment administration details, or staff operation URLs.

## Account-Security Modules

Implemented in `apps/patients`.

Current account-security surface:

- Registration stores passwords through Django `create_user`.
- Login uses Django authentication with normalized phone as username.
- Password change uses Django `PasswordChangeForm`, Django password validators,
  password hashing, `sensitive_post_parameters`, CSRF protection, no-cache
  responses, and `update_session_auth_hash`.
- Logout is POST-only and CSRF protected.
- Account recovery is a GET-only static clinic-assisted policy page.
- Email password reset is not implemented because safe production email
  ownership, delivery, and recovery policy are not configured.
- Portal rate-limit cache keys hash sensitive identities and do not store raw
  public tokens, raw phone numbers, or passwords.

## Production Readiness Modules

Implemented modules:

- `config/settings/base.py`
- `config/settings/dev.py`
- `config/settings/prod.py`
- `config/settings/helpers.py`
- `apps/core/checks.py`
- `apps/core/views.py`
- `apps/core/management/commands/deployment_smoke.py`
- `.env.example`
- `.github/workflows/django.yml`
- `.github/dependabot.yml`
- `docker-compose.staging-validation.yml`
- `scripts/validate_local_release.ps1`
- `scripts/validate_local_release.sh`
- `scripts/validate_staging_env.ps1`
- `scripts/validate_staging_env.sh`

Current production-readiness behavior:

- Local development remains simple with SQLite and LocMemCache defaults.
- Production uses `config.settings.prod`, requires a generated secret, exact
  allowed hosts, and `DATABASE_URL`.
- PostgreSQL is the production database expectation.
- Redis/shared cache is the staging/production rate-limit expectation.
- HTTPS redirect, secure cookies, and HSTS are production defaults.
- Production checks flag unsafe production combinations.
- Health/readiness endpoints avoid internal details.
- No real deployment has been performed.
- Batch 11 adds a safe `production_settings_report` command, local validation
  scripts, local-only PostgreSQL/Redis service harness, and stricter
  production-like smoke blockers.

## Deployment Smoke Modules

Implemented command:

```bash
python manage.py deployment_smoke
python manage.py deployment_smoke --json
python manage.py deployment_smoke --strict
python manage.py production_settings_report
python manage.py production_settings_report --json
```

Implementation file:

- `apps/core/management/commands/deployment_smoke.py`

Current smoke behavior:

- Checks Django startup, settings summary, local-only warnings, production
  readiness checks, HTTPS flags, database connectivity, migration state, cache
  reachability, active public content, booking settings, health imports,
  readiness DB behavior, public booking security summary, and patient portal
  security summary.
- Does not require patient accounts.
- Does not print raw application secrets, database URLs, cache URLs, passwords,
  tokens, cookies, or raw environment dumps.
- Batch 11 strict-mode checks explicitly fail unsafe production-like DEBUG,
  SQLite, LocMemCache, HTTPS/cookie/HSTS, CSRF origin, host, and booking proxy
  attestation combinations.

## Management Commands

Current custom management commands:

| Command | File | Current behavior |
| --- | --- | --- |
| `deployment_smoke` | `apps/core/management/commands/deployment_smoke.py` | Safe read-only deployment/staging smoke checks with human, JSON, and strict modes. |
| `project_status_report` | `apps/core/management/commands/project_status_report.py` | Safe read-only project status snapshot with counts, feature-disabled summary, route/security categories, and JSON mode. |
| `production_settings_report` | `apps/core/management/commands/production_settings_report.py` | Safe read-only production-like settings snapshot with booleans, counts, backend categories, and JSON mode. |
| `seed_public_content` | `apps/clinic/management/commands/seed_public_content.py` | Idempotently upserts safe clinic profile, doctor, and visit types. |
| `seed_booking_demo` | `apps/booking/management/commands/seed_booking_demo.py` | Runs public content seed, then upserts safe booking settings and demo doctor schedules. |

## Batch 11 Validation Scripts and Harnesses

Local validation scripts:

- `scripts/validate_local_release.ps1`
- `scripts/validate_local_release.sh`
- `scripts/validate_staging_env.ps1`
- `scripts/validate_staging_env.sh`

Script behavior:

- detect the repository root,
- show current branch and `HEAD`,
- run safe Django validation commands,
- redact environment-like output,
- do not deploy, commit, push, merge, provision resources, or print secret
  values.

Optional local service harness:

- `docker-compose.staging-validation.yml`

Harness behavior:

- service-only PostgreSQL and Redis,
- localhost bindings only,
- obvious local placeholder credentials,
- no Django production deployment container,
- no public launch behavior.

## Batch 11 Operational Documents

Added Batch 11 documents:

- `docs/STAGING_GAP_ANALYSIS.md`
- `docs/STAGING_ENVIRONMENT_CONTRACT.md`
- `docs/LOCAL_STAGING_SIMULATION.md`
- `docs/POSTGRESQL_READINESS.md`
- `docs/REDIS_RATE_LIMIT_READINESS.md`
- `docs/BACKUP_RESTORE_DRILL.md`
- `docs/MONITORING_ALERTING_READINESS.md`
- `docs/DEPENDENCY_SECURITY_READINESS.md`
- `docs/STAFF_ACCESS_GOVERNANCE.md`
- `docs/LEGAL_PRIVACY_OPERATIONS.md`
- `docs/BATCH_11_PROGRESS.md`
- `docs/BATCH_11_STATUS.md`

## Seed Commands

### `seed_public_content`

Creates or updates:

- one active clinic profile,
- one active Dr. Khaled doctor profile,
- nine active visit types,
- public placeholder contact/address fields.

Does not create:

- patients,
- appointments,
- WhatsApp messages,
- uploads,
- files,
- prices,
- booking slots,
- secrets,
- credentials.

### `seed_booking_demo`

Creates or updates:

- public content through `seed_public_content`,
- booking `SystemSetting` rows,
- demo `DoctorSchedule` rows.

Does not create:

- patients,
- appointments,
- WhatsApp messages,
- uploads,
- secrets,
- payments,
- real patient data.

## Current Tests by App

The baseline before Batch 10 was 212 passing tests.

Practical test layout:

- `apps/core/tests.py`
  - health/readiness safety,
  - settings helpers,
  - production-readiness checks,
  - deployment smoke output and JSON safety,
  - operational documentation checks,
  - public page smoke/content tests,
  - prohibited route checks.
- `apps/clinic/tests.py`
  - visit type patient-visible price behavior,
  - doctor display names,
  - `seed_public_content` idempotence and no patient/appointment creation.
- `apps/booking/tests.py`
  - slot generation,
  - phone normalization,
  - public booking form/view behavior,
  - UUID success routes,
  - numeric success route absence,
  - staff authorization,
  - staff status operations,
  - rescheduling,
  - booking settings safety,
  - booking rate limiting,
  - query behavior,
  - public privacy boundaries,
  - prohibited route checks.
- `apps/patients/tests.py`
  - patient model behavior,
  - portal registration/login,
  - password change,
  - account page safety,
  - static account recovery,
  - appointment linking,
  - portal rate limits,
  - portal navigation/logout,
  - portal privacy and ownership,
  - no-cache and CSRF checks,
  - prohibited route checks.
- Placeholder app tests currently exist for `apps.accounts`, `apps.dashboard`,
  `apps.legal`, `apps.records`, and `apps.whatsapp`; these apps do not expose
  implemented feature surfaces today.

## Explicitly Out of Scope Now

The following modules or feature areas must remain absent until separately
approved, designed, reviewed, implemented, and tested:

- uploads,
- private media handling,
- medical records,
- WhatsApp API sending,
- WhatsApp webhooks,
- WhatsApp message storage,
- online payments,
- diagnosis automation,
- triage automation,
- treatment automation,
- medical AI,
- broad dashboard operations beyond the bounded staff appointment routes.
