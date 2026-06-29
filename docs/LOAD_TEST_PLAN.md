# Load and Concurrency Test Plan

This plan defines future staging-only load and concurrency validation. It does not add heavy load-test dependencies and does not authorize production load testing.

## Rules

- Run load tests only in staging or an isolated production-like clone.
- Do not use real patient data.
- Do not load test production without explicit approval from the project owner and operator.
- Keep test data synthetic and clearly labeled.
- Do not send WhatsApp messages, upload files, process payments, or create medical records during load tests.
- Capture results outside Git if they contain logs, request samples, or operational details.

## Tooling Approach

Start with lightweight scripts, Django tests, or simple HTTP tooling chosen by the future operator. Locust, k6, or another load tool may be documented later, but no dependency is required in Batch 7.

Before adding a dependency:

- Confirm it is needed.
- Keep it out of runtime dependencies if possible.
- Document how it avoids production by default.
- Ensure it does not require secrets in Git.

## Target Metrics Placeholders

These targets must be approved later:

- Public page p95 response time: `TBD`.
- Booking slot generation p95 response time: `TBD`.
- Booking POST p95 response time under normal load: `TBD`.
- Staff appointment list p95 response time: `TBD`.
- Error-rate threshold: `TBD`.
- Maximum acceptable duplicate-booking race failures: `0 confirmed double bookings`.
- Rate-limit consistency target across app processes: `TBD`.

## Test Data Policy

Allowed:

- Demo clinic profile.
- Demo Dr. Khaled profile.
- Demo visit types.
- Synthetic schedules.
- Synthetic patients with obvious fake names and non-real phone numbers.
- Synthetic appointments in staging only.

Not allowed:

- Real patient names.
- Real phone numbers.
- Medical notes, reports, images, videos, or audio.
- WhatsApp credentials or real message sends.
- Payment credentials.

## Public Pages Load Test

Routes:

- `/`
- `/doctor/`
- `/services/`
- `/contact/`
- `/en/`
- `/en/doctor/`
- `/en/services/`
- `/en/contact/`
- `/privacy/`
- `/terms/`

Validate:

- Pages return 200.
- Static assets load.
- No database query spike from repeated public page views.
- No private or staff-only content appears.
- Health endpoints stay stable during public-page load.

## Booking Slot Generation Load Test

Routes:

- `/book/visit-type/`
- `/book/slots/?visit_type=<id>&date=<date>`
- `/en/book/visit-type/`
- `/en/book/slots/?visit_type=<id>&date=<date>`

Scenarios:

- Single active doctor with normal schedules.
- Several active visit types.
- Days with existing appointments.
- Closed days.
- High repeated slot-refresh traffic.

Validate:

- Slot generation remains within target response time.
- Existing appointment intervals are loaded efficiently.
- Closed days are respected.
- No appointment is created by GET requests.

## Booking POST and Rate-Limit Abuse Test

Route:

- `POST /book/confirm/`

Scenarios:

- Normal valid booking.
- Repeated invalid submissions from one IP.
- Repeated valid submissions for one normalized phone number.
- Distributed IP submissions.
- Trusted proxy behavior only after proxy stripping is verified.

Validate:

- IP hourly limit works.
- Phone daily limit works.
- Raw phone numbers are not stored in cache keys.
- Staff operations are not blocked by public booking rate limits.
- Public booking still creates only confirmed appointments through valid final confirmation.

## Staff Appointment List Query and Performance Test

Routes:

- `/staff/appointments/`
- `/staff/appointments/<appointment-id>/`

Scenarios:

- Upcoming appointments.
- Past appointments.
- Status filters.
- Doctor and visit-type filters.
- Patient name/phone search with synthetic data.

Validate:

- Anonymous users redirect to admin login.
- Non-staff users receive 403.
- Staff users can load list and detail.
- Query count and response time stay within targets.
- Audit logs and status history stay staff-only.

## DB Concurrency and Double-Booking Test

Scenarios:

- Two simultaneous public booking POSTs for the same doctor/start time.
- Staff reschedule race into an occupied slot.
- Public booking while staff reschedules another appointment.

Validate:

- At most one active appointment is confirmed for the same doctor/start time.
- Database uniqueness protects active statuses: confirmed, arrived, and rescheduled.
- Stale submissions receive a validation error.
- PostgreSQL behavior is validated before launch; SQLite-only results are not sufficient.

## Redis Rate-Limit Multi-Process Behavior

Staging should use Redis or another shared cache.

Scenarios:

- Two or more app processes behind the same staging proxy.
- Repeated booking POST attempts from one client identity.
- Cache key prefix unique to staging.

Validate:

- Counters are shared across app processes.
- LocMemCache is not used in staging.
- Cache outage behavior is understood.
- Redis eviction or expiry settings do not disable rate limiting unexpectedly.

## Reporting Template

Record:

- Date and environment.
- Application revision.
- Database type.
- Cache backend.
- Test data volume.
- Tool used.
- Target metrics.
- Actual metrics.
- Error samples with secrets and patient data removed.
- Decision: pass, fail, or retest required.

Do not claim production readiness until staging load and concurrency tests are completed and reviewed.
