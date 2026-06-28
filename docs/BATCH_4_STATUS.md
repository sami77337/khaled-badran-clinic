# Batch 4 Status — Booking MVP

## Scope Implemented

- Public booking engine for the active public doctor.
- Public booking flow without login:
  - visit type selection
  - slot selection
  - patient contact confirmation
  - confirmed appointment creation
  - success page
- Service layer under `apps.booking`:
  - active doctor and visit-type resolution
  - slot generation from active `DoctorSchedule`
  - closed-day exclusion
  - existing appointment overlap exclusion
  - visit-type duration handling
  - minimum lead time
  - max days ahead
  - booking enabled/disabled setting
  - slot interval setting
  - reminder offset setting
- Jordan-first phone normalization helper.
- Public booking form with server-side validation.
- Admin refinements for appointment list/search/filter behavior.
- Safe booking demo seed command.
- Expanded test coverage.

## Routes

Arabic/default:

- `/book/`
- `/book/visit-type/`
- `/book/slots/`
- `/book/confirm/`
- `/book/success/<public_token>/`

English:

- `/en/book/`
- `/en/book/visit-type/`
- `/en/book/slots/`
- `/en/book/confirm/`
- `/en/book/success/<public_token>/`

## Batch 4B Security Hardening

- `Appointment.public_token` was added as a UUID public lookup token.
- Public success URLs now use `public_token` instead of numeric appointment IDs.
- Public success views look up appointments by `public_token`.
- Numeric appointment success URLs no longer resolve.
- Public success templates show a short confirmation reference derived from the UUID, not the database ID.
- `AppointmentAdmin` keeps `public_token` readonly and supports exact token search.
- A cross-database exact-slot uniqueness constraint was added for `doctor + starts_at + status`.
- Duplicate exact-slot public POSTs are still blocked at service/form level by stale-slot validation.

## Services

Created:

- `apps/booking/services.py`
- `apps/booking/forms.py`
- `apps/booking/selectors.py`
- `apps/booking/phone.py`
- `apps/booking/views.py`

## Settings Keys

The booking service reads these `SystemSetting` keys:

- `booking_enabled`
- `booking_min_lead_minutes`
- `booking_max_days_ahead`
- `booking_slot_interval_minutes`
- `appointment_reminder_offset_minutes`

Default behavior:

- booking enabled: `true`
- minimum lead time: `180` minutes
- max days ahead: `30`
- slot interval: `15` minutes
- reminder offset: `180` minutes

## Management Commands

Public content seed:

```bash
python manage.py seed_public_content
```

Booking demo setup:

```bash
python manage.py seed_booking_demo
```

`seed_booking_demo` is idempotent and may create/update:

- clinic/doctor/visit types through the public content seed
- booking `SystemSetting` defaults
- demo `DoctorSchedule` records

It must not create:

- real patients
- appointments
- WhatsApp messages
- uploads
- secrets
- payments

## Explicitly Left Out

- WhatsApp API sending.
- WhatsApp webhook logic.
- Patient portal.
- Patient file uploads.
- Online payment processing.
- Medical AI, diagnosis automation, triage automation, or treatment suggestions.
- Full dashboard UI.
- Real patient seed data.
- Secrets or API keys.

## Notes

- Booking creates a `Patient` only on valid final confirmation.
- Booking creates an `Appointment` only on valid final confirmation.
- Duplicate stale submissions are rejected by rechecking slot availability.
- Public pages and intermediate booking steps do not create appointments.
- Success pages show appointment confirmation details through public UUID tokens.
- Success pages may show appointment date/time, doctor name, visit type, patient name, and a safe short confirmation reference.
- Success pages must not show internal notes, audit logs, internal numeric IDs, private medical data, staff-only fields, uploads, or future medical-record content.
- WhatsApp, patient portal, uploads, payments, and medical automation remain excluded because they require separate privacy, security, authorization, and operational design.

## Recommended Next Batch

Batch 5 should focus on patient portal and records only after confirming privacy and authentication rules:

- patient account access
- appointment lookup rules
- patient-visible summaries
- private medical record boundaries
- authorization tests
- no file uploads until private-storage workflow is explicitly designed
