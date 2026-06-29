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

## Development Policy

Work must be delivered in small auditable batches. Do not ask Codex or any AI agent to implement the entire system in one step.

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
- English home: `http://127.0.0.1:8000/en/`
- English doctor: `http://127.0.0.1:8000/en/doctor/`
- English services: `http://127.0.0.1:8000/en/services/`
- English contact: `http://127.0.0.1:8000/en/contact/`
- English booking: `http://127.0.0.1:8000/en/book/`
- English booking visit type: `http://127.0.0.1:8000/en/book/visit-type/`
- English booking slots: `http://127.0.0.1:8000/en/book/slots/`
- English booking confirm: `http://127.0.0.1:8000/en/book/confirm/`
- English booking success: `http://127.0.0.1:8000/en/book/success/<public-token>/`
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
- No patient portal, uploads, online payments, or medical automation are implemented.
- Demo seed commands do not create real patients or appointments.

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
