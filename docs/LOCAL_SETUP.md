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

Safety boundaries:

- Do not add real patient data.
- Do not add WhatsApp credentials.
- Do not expose private medical data.
- Booking demo setup creates schedules/settings only, not appointments.
