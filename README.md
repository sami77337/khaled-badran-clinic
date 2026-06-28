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
- Legal pages: `/privacy/`, `/terms/`, `/medical-disclaimer/`, `/whatsapp-policy/`
- SEO basics: `/robots.txt`, `/sitemap.xml`

Booking safety boundaries:

- Public booking creates confirmed appointments without requiring login.
- The current public scope resolves the active doctor automatically.
- Public success pages use non-enumerable UUID public tokens, not numeric appointment IDs.
- Public success pages may show appointment time, doctor, visit type, patient name, and a short confirmation reference.
- Public success pages must not show internal notes, audit logs, internal IDs, private medical data, staff-only fields, or future medical-record data.
- No WhatsApp API sending or webhook is implemented.
- No patient portal, uploads, online payments, or medical automation are implemented.
- Demo seed commands do not create real patients or appointments.
