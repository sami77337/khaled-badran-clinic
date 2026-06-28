# Codex Build Plan

This plan breaks the project into safe implementation batches. Do not ask Codex CLI to build the entire system in one prompt.

## Global Rules

- Work on a feature branch, not directly on `main` after initialization.
- Each batch must be small and testable.
- Run formatting and tests after each batch.
- Do not introduce WhatsApp credentials or secrets into the repo.
- Do not add real patient data.
- Do not implement medical AI responses.
- Keep Arabic/English support in public-facing models/templates.

## Target Stack

- Django
- PostgreSQL
- Django templates
- HTMX
- Alpine.js
- Tailwind CSS
- PWA support
- WhatsApp Business integration later

---

## Batch 0 — Repository Audit

Goal: inspect the repo, confirm current files, and prepare the first implementation plan.

Expected changes: none.

Checks:

- `git status`
- repository tree review

Risk: none.

---

## Batch 1 — Django Foundation

Goal: create a clean Django project foundation.

Expected files:

- `pyproject.toml` or `requirements.txt`
- `.gitignore`
- `.env.example`
- `manage.py`
- `config/settings/base.py`
- `config/settings/dev.py`
- `config/settings/prod.py`
- `config/urls.py`
- `config/wsgi.py`
- `config/asgi.py`
- initial Django apps structure

Recommended apps:

- `apps.core`
- `apps.clinic`
- `apps.accounts`
- `apps.booking`
- `apps.patients`
- `apps.records`
- `apps.whatsapp`
- `apps.dashboard`
- `apps.legal`

Checks:

- `python -m pip install -r requirements.txt` or equivalent
- `python manage.py check`
- `python manage.py test`

Risk: low.

---

## Batch 2 — Core Models and Admin

Goal: add foundational models and admin registration.

Models:

- Doctor
- ClinicProfile
- VisitType
- DoctorSchedule
- ClosedDay
- Patient
- Appointment
- PaymentRecord or payment fields
- AuditLog minimal

Checks:

- `python manage.py makemigrations --check --dry-run` before committing migrations when appropriate
- `python manage.py check`
- `python manage.py test`

Risk: medium due to data model decisions.

---

## Batch 3 — Public Website and Design System

Goal: create bilingual public pages and warm premium visual foundation.

Pages:

- home
- doctor profile
- services
- contact
- privacy
- terms

Design direction:

- warm ivory backgrounds
- wood-brown text/structure
- deep red accents
- clinic photo support
- mobile-first layout

Checks:

- `python manage.py check`
- manual page review

Risk: low/medium.

---

## Batch 4 — Booking MVP

Goal: implement public booking flow.

Features:

- visit type selection
- available slot selection
- patient name and phone
- automatic confirmation
- appointment status lifecycle
- default reminder offset setting = 3 hours
- price show/hide from dashboard/config

Checks:

- unit tests for booking availability
- validation tests for phone normalization
- `python manage.py test`

Risk: medium.

---

## Batch 5 — Patient Portal and Records

Goal: implement patient account, portal, medical record views, and uploads.

Features:

- patient login/registration
- appointments
- patient-visible summaries
- internal notes hidden by default
- private file uploads
- deletion request workflow

Checks:

- authorization tests
- file upload tests
- `python manage.py test`

Risk: medium/high due to privacy.

---

## Batch 6 — WhatsApp Integration Shell

Goal: add WhatsApp models and webhook shell without sending real messages.

Features:

- WhatsAppConversation
- WhatsAppMessage
- WhatsAppMedia
- inbound webhook endpoint shell
- signature/verification placeholder
- message status states
- inquiry types: new inquiry, follow-up, appointment issue
- no real credentials committed

Checks:

- webhook tests
- model tests
- no secrets in repo

Risk: medium/high.

---

## Batch 7 — Dashboard

Goal: build doctor/admin operational dashboard.

Features:

- today appointments
- new inquiries
- unmatched WhatsApp messages
- new attachments
- no-show/payment indicators
- visit type management
- price show/hide management
- reminder offset management

Checks:

- permission tests
- template smoke tests

Risk: medium.

---

## Batch 8 — Legal and Consent Workflows

Goal: add legal content pages and workflows.

Features:

- privacy policy page
- terms page
- WhatsApp consent text
- publication consent model/workflow
- deletion request model/workflow

Checks:

- permission tests
- legal pages render

Risk: medium.

---

## Batch 9 — PWA, Security, Deployment Prep

Goal: final hardening.

Features:

- manifest
- icons placeholders
- service worker safe minimal mode
- security settings review
- deployment docs
- backup notes
- final README

Checks:

- `python manage.py check --deploy`
- full test suite
- manual smoke test

Risk: medium.
