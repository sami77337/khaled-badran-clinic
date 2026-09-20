# Patient self-service rescheduling

Base: `main` at `137c7cb1b229f2901b9e4de34e4dc08375193649`.

The anonymous flow opens the existing booking slot picker for one NO_SHOW
appointment. It displays the confirmation reference, previous date/time, doctor
and visit type. No patient identity/contact form or account is required. Arabic
is the default; English routes are under `/en/`.

## Link integration boundary

Trusted application code can use:

```python
from apps.booking.rescheduling import reschedule_url

relative_url = reschedule_url(appointment, language="ar")
```

The caller must supply the specific persisted Appointment. There is no public
token-issuance endpoint or phone-based appointment lookup. PR2 can consume this
helper; this change does not send messages or change WhatsApp APIs/templates.

Tokens use Django timestamped signing with a dedicated rescheduling purpose.
The payload contains the appointment's public UUID and an HMAC of its current
version; it contains no patient/contact details or internal numeric identifiers.
Links expire after 30 days and are invalidated by appointment updates, including
successful rescheduling. They cannot be reused if a later visit becomes NO_SHOW.
The read-only success receipt uses a separate purpose and a one-hour lifetime.

These are bearer links. Responses use no-store, no-referrer and noindex headers.
Application console logging redacts the token path and strips request/traceback
objects for this route. Infrastructure access logs are outside Django's filter.

## Writes and invariants

Slot selection, review and success are read-only GETs. Confirmation requires POST
and CSRF, uses the existing public-booking IP limit, and rechecks the signed
capability while holding the appointment lock. Invalid links/statuses and stale
or conflicting slots produce a generic page without appointment details.

The existing availability engine and extracted shared reschedule-slot validator
retain booking enablement, active doctor/visit type, weekly/special hours, closure,
lead-time, horizon, grid, duration, exact collision and overlap rules. The signed
appointment supplies doctor and visit type; client identity/service fields are
ignored. The selected start must differ from the previous start.

One transaction updates starts_at/ends_at, NO_SHOW to RESCHEDULED, and resets
reminder_sent_at. It appends status history and sanitized audit evidence with the
fixed patient-self-service message. Previous history, row ID, public_token,
patient, doctor, visit type, contacts and reminder preferences remain intact.
Linked accounts see the updated row through the existing portal queries.

NO_SHOW remains terminal for staff operations and is not added to the global
RESCHEDULE_ALLOWED_FROM set. The new transition is isolated to the signed flow.

Public booking, staff rescheduling and self-service rescheduling acquire the same
Doctor row lock before checking slots. This prevents concurrent overlapping
reservations with different start times on PostgreSQL, beyond the existing exact
slot unique constraint. The new flow rolls back on integrity or database-lock
failures. No schema changes, migrations or dependencies are needed.

## Validation

```text
python manage.py test apps.booking apps.dashboard.test_appointment_closeout apps.dashboard.test_patient_cancellation_setting --noinput
python manage.py check
python manage.py makemigrations --check --dry-run
```

Run the tests with the existing local PostgreSQL DATABASE_URL to exercise all six
real concurrency cases. Those tests skip on SQLite, where row locks are absent;
integrity/contention rollback tests also run on SQLite.

The Chromium fixture test uses the existing browser launcher and installed Node,
without adding a dependency. It checks AR/EN slots, selected slots, confirmation,
success, empty and failure pages, plus original booking, at widths
320/390/768/1024/1440 (70 rendered cases). It checks overflow, visible text,
action size/obstruction, language direction, date/time selection, capability
preservation, and the confirmation form's method/fields. Set
KBC_RESCHEDULE_QA_OUTPUT to a local directory to save review screenshots.
