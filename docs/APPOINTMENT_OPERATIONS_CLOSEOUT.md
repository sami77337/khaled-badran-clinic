# Appointment operations closeout

Branch: `feat/batch2-appointment-closeout`

Pull request: [#80](https://github.com/sami77337/khaled-badran-clinic/pull/80)

## Staff workflow

The dashboard follow-up queue lists past confirmed and rescheduled appointments
that still need classification. Reading the queue does not change appointment
status. Staff can mark arrival, record a no-show with an internal reason, or
complete an arrived visit. No-show is blocked before the appointment start time;
completed, cancelled, and no-show appointments remain terminal.

After recording arrival or no-show, staff choose No Message, Ready Message, or
Custom Message. Ready messages support Arabic and English. Both message choices
open a validated `wa.me` link for staff to review and send manually. Opening a
link does not record a sent or delivered message. Custom text does not overwrite
the saved ready-message settings.

## Default messages and migration

Migration `booking.0006_approved_appointment_message_defaults` adds an active
setting for each missing event:

| Event | Arabic | English |
| --- | --- | --- |
| Arrived | تم تسجيل وصولك إلى العيادة. شكرًا لك. | Your arrival at the clinic has been recorded. Thank you. |
| No-show | لم يتم تسجيل حضورك للموعد. إذا كنت بحاجة إلى إعادة الجدولة، يرجى التواصل مع العيادة. | Your attendance was not recorded for this appointment. Please contact the clinic if you need to reschedule. |

Existing rows are preserved exactly, including edited text, blank settings,
disabled settings, timestamps, and editor attribution. Reapplying the migration
does not duplicate or reset settings. Reversing the data migration deliberately
retains rows so it cannot delete settings that staff have edited.

Staff can edit or disable these messages at
`/dashboard/appointments/messages/`. New rows created outside the migration
still default to inactive, and activation requires both languages.

## Template validation

The only accepted placeholders are `{patient_name}`, `{appointment_date}`,
`{appointment_time}`, and `{clinic_phone}`. Attribute access, indexing,
conversions, format specifications, unknown names, escaped braces, and malformed
braces are rejected.

Validation runs when settings are saved and again before previews or ready
messages are rendered. Invalid stored text cannot expose a ready-message link
or break the settings/compose page. No Message and Custom Message remain
available when a stored ready template is invalid. Invalid recipient phone
numbers do not produce WhatsApp links.

Settings and operational routes require an active staff account. Mutations use
POST and CSRF protection. Audit records identify changed fields without copying
message bodies into metadata.

## Validation evidence

Resumed local validation on 2026-09-18:

- Django system checks and migration drift check passed.
- Ruff lint passed for all changed Python files. The seven formatted appointment
  messaging, migration, and closeout files also passed `ruff format --check`.
- A fresh disposable SQLite database applied all migrations and contained the
  two active defaults. A repeated migration run left exactly two rows.
- Deployment smoke completed with 13 passes, 7 warnings, 0 failures, and
  0 strict blockers under development settings on that empty temporary database.
  Warnings cover debug mode, SQLite, local memory cache, disabled HTTPS redirect,
  and the absent clinic, doctor, and visit-type content in the empty database.
- Project status and production settings reports completed in text and JSON
  formats on the temporary database.
- Recorded full suite: `python manage.py test --parallel 4 --noinput` completed
  **1,199 tests in 112.215 seconds, OK (6 skipped)**. The log is saved locally at
  `.cache/batch2-resumed-final-tests.log`.

That successful local run included a temporary Windows-only Web Push test
adjustment. The unrelated adjustment was restored before committing Batch 2 and
is excluded from PR #80. The validated Batch 2 implementation is unchanged, so
the full suite was not rerun during finalization. CI validates the final pushed
commit on Linux.

The temporary smoke database is removed after validation. These checks do not
apply migrations to the existing local database or validate a production
deployment. Local `check --deploy` reports six development-configuration
warnings for HTTPS/HSTS, secure cookies, the development secret, and debug mode.
