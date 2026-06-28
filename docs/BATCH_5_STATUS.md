# Batch 5 Status - Booking Operations and Hardening

## Scope Implemented

Batch 5 hardened the booking MVP for bounded clinic operations without adding patient portal, uploads, WhatsApp API/webhooks, payments, records, or medical automation.

Implemented:

- Staff-only appointment list and detail pages under `/staff/appointments/`.
- Staff-only appointment operations:
  - cancel
  - reschedule
  - mark arrived
  - mark completed
  - mark no-show
- Booking operation service layer in `apps.booking.operations`.
- Audit helper in `apps.booking.audit`.
- Public booking cache rate-limit helper in `apps.booking.rate_limits`.
- Initial appointment creation audit logging.
- Status history for public creation and staff status operations.
- Safer `SystemSetting` helpers for boolean, integer, and duration values.
- Per-day appointment interval loading for slot generation to avoid per-slot appointment queries.
- Additional appointment indexes and active-slot uniqueness.
- Staff templates for appointment list/detail, operation forms, status history, and audit events.
- Expanded tests from 78 to 137 tests.

## Staff Routes

- `GET /staff/appointments/`
- `GET /staff/appointments/<appointment-id>/`
- `POST /staff/appointments/<appointment-id>/cancel/`
- `POST /staff/appointments/<appointment-id>/reschedule/`
- `POST /staff/appointments/<appointment-id>/arrived/`
- `POST /staff/appointments/<appointment-id>/complete/`
- `POST /staff/appointments/<appointment-id>/no-show/`

These routes are not a broad dashboard. They are limited to booking operations.

## Staff Access Rules

- Anonymous users are redirected to the Django admin login.
- Authenticated users must have `is_staff=True`.
- Authenticated non-staff users receive 403.
- Staff pages may show internal appointment IDs, status history, audit logs, and operational notes.
- Public pages must not show staff URLs, internal IDs, audit logs, staff-only notes, or private medical data.

## Status Transition Policy

Allowed staff transitions:

- `confirmed -> arrived`
- `confirmed -> cancelled`
- `confirmed -> rescheduled`
- `confirmed -> no_show`
- `rescheduled -> arrived`
- `rescheduled -> cancelled`
- `rescheduled -> rescheduled`
- `rescheduled -> no_show`
- `arrived -> completed`
- `arrived -> cancelled`

Terminal statuses:

- `completed`
- `cancelled`
- `no_show`

Restore/undo is intentionally not implemented in this batch. Terminal state correction needs a reviewed staff workflow with explicit reason capture and audit policy.

Reschedule approach:

- Rescheduling keeps the same `Appointment` row and preserves `public_token`.
- The moved appointment status becomes `rescheduled`.
- `rescheduled` is treated as an active operational status for slot blocking and staff arrival/no-show/cancellation.
- The public success URL continues to work because the public token is unchanged.

Completed appointments do not create medical records in this batch.

## Forms Added

- `StatusNoteForm`
- `CancelAppointmentForm`
- `MarkNoShowForm`
- `RescheduleAppointmentForm`

Validation behavior:

- Cancellation note is required.
- No-show note is required.
- Reschedule target time is required.
- Reschedule uses the current appointment visit type and rejects inactive doctor or inactive visit type.
- Reschedule respects schedule availability, closed days, minimum lead time, max days ahead, exact active duplicates, and overlaps.
- No hidden staff override was added.

## Audit Logging Policy

Uses `apps.core.models.AuditLog`.

Audited actions:

- Public appointment created.
- Appointment cancelled by staff.
- Appointment rescheduled by staff.
- Appointment marked arrived.
- Appointment marked completed.
- Appointment marked no-show.

Audit metadata is operational and limited:

- internal appointment ID
- public token string
- old status
- new status
- old/new appointment start time where relevant
- actor user ID where present
- trimmed operation note

Audit logs are shown on staff appointment detail pages only.

Public pages must never render audit logs or status history.

## Rate Limiting

Implemented lightweight Django-cache public booking rate limiting.

Defaults:

- `booking_post_rate_limit_per_hour = 10` per IP
- `booking_phone_rate_limit_per_day = 5` per normalized phone

Behavior:

- Public booking POST attempts increment an IP-hour counter.
- Valid public booking forms increment a normalized-phone daily counter before appointment creation.
- Phone identities are hashed before use in cache keys.
- Staff operations are not blocked by public booking rate limits.
- Production should use a shared cache backend such as Redis or Memcached. LocMemCache is acceptable for local development only.

## Database and Concurrency Hardening

Added migration:

- `apps/booking/migrations/0003_appointment_booking_app_doctor__2b7f9b_idx_and_more.py`

Added indexes:

- `doctor + status + starts_at`
- `starts_at`

Already present useful indexes:

- `doctor + starts_at`
- `patient + starts_at`
- `status + starts_at`
- unique/indexed `public_token`

Added constraint:

- Conditional unique constraint on `doctor + starts_at` for active statuses:
  - `confirmed`
  - `arrived`
  - `rescheduled`

Operations use `transaction.atomic()` for state changes.

Reschedule catches database `IntegrityError` and reports a validation error when duplicate/overlap protection triggers late.

SQLite compatibility is preserved. PostgreSQL remains the production recommendation.

## Settings Safety

Safe helpers now exist for:

- `get_boolean_setting`
- `get_integer_setting`
- `get_duration_setting`

Invalid stored values fall back to safe defaults instead of crashing public booking pages.

Covered settings:

- `booking_enabled`
- `booking_min_lead_minutes`
- `booking_max_days_ahead`
- `booking_slot_interval_minutes`
- `appointment_reminder_offset_minutes`
- `booking_post_rate_limit_per_hour`
- `booking_phone_rate_limit_per_day`

## Tests

Expanded test coverage includes:

- Staff authorization.
- Staff operation workflows.
- Status transition validation.
- Terminal state protection.
- Rescheduling.
- Audit logging.
- Public creation audit.
- Duplicate exact active slots.
- IntegrityError handling.
- Query behavior for staff list/detail.
- Settings fallback behavior.
- Public booking rate limiting.
- Public privacy boundaries.
- Confirmation token behavior.
- No patient portal/upload/WhatsApp API routes.

Current result during implementation:

```bash
python manage.py test
# Found 137 test(s).
# Ran 137 tests.
# OK
```

## Explicitly Left Out

- Patient portal.
- Patient file uploads.
- WhatsApp API sending.
- WhatsApp webhooks.
- Online payments.
- Medical records.
- Medical AI, diagnosis automation, triage automation, or treatment automation.
- Broad dashboard.
- Restore/undo workflow for terminal appointment states.
- Real patient data.
- Secrets or API keys.

## Remaining Production Gaps

- Use PostgreSQL in production and test migrations there.
- Configure a shared cache backend for rate limiting.
- Confirm reverse proxy IP handling before trusting `X-Forwarded-For`.
- Add production structured logging.
- Add monitoring, error reporting, and uptime checks.
- Define backup and restore procedures.
- Define audit retention and access review policy.
- Complete legal/privacy review.
- Configure HTTPS/HSTS and secure cookies.
- Configure static files/CDN.
- Design private media storage before uploads are implemented.
- Load test before launch.

## Production Hardening Checklist

- HTTPS/HSTS.
- Secure cookies.
- CSRF trusted origins.
- Trusted hosts.
- PostgreSQL.
- Connection pooling.
- Shared caching backend.
- Rate limiting backend.
- Backups and restore tests.
- Structured logging.
- Monitoring.
- Error reporting.
- Static files/CDN.
- Media/private storage.
- Audit retention.
- Data protection/legal review.
- Load testing before launch.

## Recommended Next Batch

Recommended Batch 6:

- Keep patient portal and uploads out until authentication/privacy rules are explicitly designed.
- Add a small staff settings workflow only if needed for booking settings, with audit logging and staff authorization.
- Or implement a production deployment readiness batch focused on PostgreSQL, cache backend, security settings, logging, and deploy checks.

