# Batch 1 Review — Django Foundation

## Status

Accepted for merge after local checks passed.

## Scope Confirmed

Batch 1 stayed within foundation scope:

- Django project scaffold.
- Split settings.
- Dev SQLite fallback.
- PostgreSQL-ready DATABASE_URL support.
- Arabic default language.
- Asia/Amman timezone.
- Initial app package structure.
- Minimal health route.
- Basic smoke test.
- No booking logic.
- No patient records.
- No WhatsApp webhook logic.
- No dashboard features.
- No secrets or patient data.

## Local Checks Reported

- python manage.py check — passed.
- python manage.py test — passed.
- 1 smoke test passed.

## Review Notes

- The dev settings correctly use SQLite fallback when DATABASE_URL is empty.
- Production settings require DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, and DATABASE_URL.
- PRIVATE_MEDIA_ROOT is configured separately from public media.
- The current health route is intentionally minimal and may be replaced later by the public homepage.

## Next Batch

Batch 2 — Core Models and Admin.

Recommended scope:

- ClinicProfile.
- Doctor.
- VisitType.
- DoctorSchedule.
- ClosedDay.
- Patient.
- Appointment.
- Payment status/minimal payment record.
- AuditLog.
- Admin registration.
- Migrations and model tests.

Do not implement public booking flow, patient portal, WhatsApp webhooks, uploads, or dashboard UI in Batch 2.
