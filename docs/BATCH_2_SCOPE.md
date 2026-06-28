# Batch 2 Scope — Core Models and Admin

## Goal

Add foundational data models and Django admin registration only.

## Out of Scope

- No public booking UI.
- No patient portal UI.
- No WhatsApp webhook logic.
- No file upload handling.
- No dashboard UI.
- No real patient data.
- No medical AI.

## Models

### apps.clinic

- ClinicProfile
- Doctor
- VisitType
- DoctorSchedule
- ClosedDay

### apps.patients

- Patient

### apps.booking

- Appointment
- AppointmentStatusHistory only if it stays simple.

### apps.core

- AuditLog
- SystemSetting if needed for reminder defaults.

## Required Decisions

- Arabic clinic name: عيادة الدكتور خالد بدران.
- English clinic name: Dr. Khaled Badran Clinic.
- Initial visible scope: Dr. Khaled only.
- Keep Doctor model flexible for future.
- VisitType supports Arabic/English names.
- VisitType supports duration_minutes.
- VisitType supports optional price.
- VisitType supports show_price_to_patient.
- VisitType supports is_active.
- Default appointment reminder offset: 3 hours.
- Appointment statuses: CONFIRMED, ARRIVED, COMPLETED, NO_SHOW, CANCELLED, RESCHEDULED.
- Patient phone stores raw input and normalized E.164 placeholder fields.
- Do not link medical records by name alone.

## Admin

Register all new models with basic list_display, filters, and search fields.

## Tests

Add model tests for:

- VisitType price visibility behavior.
- Appointment default status.
- Reminder default equals 3 hours where implemented.
- Patient raw and normalized phone fields.
- Doctor Arabic/English display fields.

## Commands

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py check
python manage.py test
```
