# Local Setup Notes

هذه ملاحظات أولية لتجهيز العمل المحلي قبل تشغيل Codex CLI.

## Clone

```bash
git clone https://github.com/sami77337/khaled-badran-clinic.git
cd khaled-badran-clinic
```

## Suggested Branch

```bash
git checkout -b feat/django-foundation
```

## Python Environment

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
```

## Codex CLI First Step

ابدأ بفحص المستودع قبل تنفيذ أي كود:

```text
Read README.md and all docs. Inspect the repository. Do not modify files yet. Report the safest first implementation batch.
```

## Important

- Do not commit `.env`.
- Use `.env.example` as a template only.
- Do not add real WhatsApp credentials.
- Do not add real patient data.

## Current Local Commands

Run checks and tests:

```bash
python manage.py check
python manage.py test
```

Seed safe public content and booking demo setup:

```bash
python manage.py seed_public_content
python manage.py seed_booking_demo
```

Run the server:

```bash
python manage.py runserver
```

Booking URLs:

- Arabic: `/book/`, `/book/visit-type/`, `/book/slots/`, `/book/confirm/`
- English: `/en/book/`, `/en/book/visit-type/`, `/en/book/slots/`, `/en/book/confirm/`

Staff booking operation URLs:

- Appointment list: `/staff/appointments/`
- Appointment detail: `/staff/appointments/<appointment-id>/`
- Cancel: `POST /staff/appointments/<appointment-id>/cancel/`
- Reschedule: `POST /staff/appointments/<appointment-id>/reschedule/`
- Mark arrived: `POST /staff/appointments/<appointment-id>/arrived/`
- Mark completed: `POST /staff/appointments/<appointment-id>/complete/`
- Mark no-show: `POST /staff/appointments/<appointment-id>/no-show/`

Create a local staff user through Django admin tooling when needed:

```bash
python manage.py createsuperuser
```

Staff access rules:

- Anonymous users are redirected to admin login for `/staff/appointments/`.
- Authenticated users must have `is_staff=True`.
- Non-staff authenticated users receive 403.
- Staff pages may show internal IDs, status history, audit logs, and operational notes.
- Public booking and success pages must not show those staff-only fields.

Safety boundaries:

- Do not add real patient data.
- Do not add WhatsApp credentials.
- Do not expose private medical data.
- Booking demo setup creates schedules/settings only, not appointments.
- Do not use local demo data as real clinic data.
- Do not add patient portal, uploads, WhatsApp API/webhooks, payments, or medical automation in the booking operations batch.

## Batch 6 Local Development Notes

Local development still uses:

```bash
python manage.py check
python manage.py test
python manage.py runserver
```

`manage.py` defaults to:

```text
DJANGO_SETTINGS_MODULE=config.settings.dev
```

Local defaults:

- Empty `DATABASE_URL` uses `db.sqlite3`.
- Empty `CACHE_URL` uses Django LocMemCache.
- `DJANGO_DEBUG` defaults to true in development settings.
- HTTPS redirect, HSTS, and secure cookies are disabled for local simplicity.
- `BOOKING_TRUST_X_FORWARDED_FOR` is false by default.

Use `.env.example` as a template only. Keep `.env` out of Git.

New documentation:

- `docs/ENVIRONMENT.md`
- `docs/PRODUCTION_READINESS.md`
- `docs/DEPLOYMENT_CHECKLIST.md`
- `docs/SECURITY_HARDENING.md`
- `docs/BATCH_6_STATUS.md`

Health checks:

- Public liveness: `/health/`
- Internal/private readiness: `/health/ready/`

The readiness endpoint checks database connectivity but intentionally does not expose database details or exception text.

Production planning notes:

- SQLite is local/CI only.
- PostgreSQL is required for production.
- LocMemCache is local only.
- Redis or another shared cache is required for production rate limiting.
- Do not enable `BOOKING_TRUST_X_FORWARDED_FOR` unless a trusted reverse proxy strips incoming client-supplied `X-Forwarded-For` and sets its own.
