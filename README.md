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
- `docs/CODEX_PROMPTS.md` — ready-to-use Codex CLI prompts.

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
