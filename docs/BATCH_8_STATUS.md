# Batch 8 Status - Patient Portal Foundation

## Scope Implemented

Batch 8 adds the first patient portal foundation after public booking. It is intentionally limited to optional account registration, phone/password login, logout, appointment linking, and viewing linked appointments.

Implemented:

- Optional patient portal routes under `/portal/`.
- English equivalents under `/en/portal/`.
- Patient registration with full name, phone, optional email, password, and password confirmation.
- Patient login using normalized phone as the Django auth username.
- Django password hashing through `create_user`.
- POST-only logout with CSRF protection.
- Appointment linking using appointment `public_token` plus matching booking phone.
- Patient dashboard with display name, linked appointment count, upcoming appointments, and recent appointments.
- Patient appointment list and detail pages using UUID `public_token` URLs.
- Patient-safe status labels:
  - `confirmed` -> `Confirmed`
  - `arrived` -> `Arrived`
  - `completed` -> `Completed`
  - `no_show` -> `Missed`
  - `cancelled` -> `Cancelled`
  - `rescheduled` -> `Rescheduled`
- No-cache behavior for portal pages.
- Lightweight per-user/IP appointment-link rate limiting using Django cache.
- Optional portal linking CTA from the public booking success page.
- Safe `deployment_smoke` patient-portal route summary that does not require accounts and does not print patient data.

## Existing Model Relationship

No model migration was needed. `apps.patients.Patient` already had:

- nullable `user = OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=SET_NULL)`.

This keeps public booking login-free while allowing one linked patient profile per account.

## Routes Added

Arabic/default:

- `GET /portal/`
- `GET|POST /portal/login/`
- `POST /portal/logout/`
- `GET|POST /portal/register/`
- `GET|POST /portal/link-appointment/`
- `GET /portal/appointments/`
- `GET /portal/appointments/<public-token>/`

English:

- `GET /en/portal/`
- `GET|POST /en/portal/login/`
- `POST /en/portal/logout/`
- `GET|POST /en/portal/register/`
- `GET|POST /en/portal/link-appointment/`
- `GET /en/portal/appointments/`
- `GET /en/portal/appointments/<public-token>/`

Numeric portal appointment URLs are not routed.

## Appointment Linking Behavior

Allowed:

- Logged-in patient submits a public appointment token and the booking phone.
- If the token exists and the phone matches the appointment patient's normalized phone, the appointment's Patient record is linked to the authenticated user.
- If the appointment is already linked to the same user, linking is a safe no-op.

Blocked:

- Anonymous linking attempts redirect to portal login.
- Wrong phone does not link and uses a generic error.
- Nonexistent token does not link and uses the same generic error.
- A Patient already linked to another user cannot be stolen.
- A user already linked to another Patient record cannot link a second Patient record.
- Numeric appointment IDs are not accepted for portal appointment detail.

## Patient-Visible Data

Portal appointment pages show only:

- visit type,
- appointment date/time,
- patient-safe status label,
- doctor display name,
- clinic name/address,
- created date.

Portal pages do not show:

- internal appointment IDs,
- staff notes,
- booking notes,
- doctor internal notes,
- status history notes,
- audit logs,
- medical records,
- uploads/private media,
- WhatsApp messages,
- payment administration details.

## Intentionally Out of Scope

- Deployment.
- Commits, pushes, or merges.
- File uploads.
- Medical records.
- WhatsApp API sending.
- WhatsApp webhooks.
- Online payments.
- Diagnosis, triage, treatment, or medical AI.
- Email verification.
- Password reset/account recovery flow.
- Real secrets.
- Real patient data.

## Tests Added or Updated

The suite now covers:

- anonymous users cannot access portal dashboard or appointment detail,
- registered patient can access dashboard,
- phone/password login,
- password hashing,
- duplicate registration phone handling,
- appointment linking requires login,
- linking requires matching phone,
- wrong phone uses generic error and does not link,
- nonexistent token uses generic error,
- already-linked appointment to another user cannot be stolen,
- already-linked appointment to the same user is a no-op,
- User A cannot access User B's appointment,
- appointment detail uses `public_token`,
- numeric portal appointment URL returns 404,
- portal appointment detail hides booking notes, status history notes, audit logs, staff URLs, and token text,
- no-show is shown to patients as `Missed`,
- portal pages are no-cache,
- CSRF is enforced for login, registration, and appointment linking POSTs,
- upload, WhatsApp webhook/API, and medical-record routes remain absent,
- previous portal-404 tests were updated to authenticated portal behavior,
- public booking success still uses UUID tokens and now offers optional portal linking,
- staff-only route tests remain intact.

Final test count:

```bash
python manage.py test
# Found 193 test(s).
# Ran 193 tests.
# OK
```

## Verification

```bash
python manage.py makemigrations --check --dry-run
# No changes detected
```

```bash
python manage.py makemigrations
# No changes detected
```

```bash
python manage.py migrate
# Operations to perform:
#   Apply all migrations: admin, auth, booking, clinic, contenttypes, core, patients, sessions
# Running migrations:
#   No migrations to apply.
```

```bash
python manage.py check
# System check identified no issues (0 silenced).
```

```bash
python manage.py deployment_smoke
# Result: WARNING (14 pass, 4 warning, 0 failure, 0 strict blocker)
```

Local smoke warnings are expected under `config.settings.dev`:

- `local_debug_enabled`
- `local_sqlite_database`
- `local_locmem_cache`
- `local_https_redirect_disabled`

```bash
python manage.py deployment_smoke --json
# status=warning
# exit_code=0
# passes=14
# warnings=4
# failures=0
# strict_blockers=0
```

```bash
python manage.py test
# Found 193 test(s).
# Ran 193 tests.
# OK
```

```bash
python manage.py seed_public_content
# Seeded public content: clinic=updated, doctor=updated, visit_types_created=0, visit_types_updated=9.
# No patients, appointments, WhatsApp messages, files, prices, or booking slots were created.
```

```bash
python manage.py seed_booking_demo
# Seeded public content: clinic=updated, doctor=updated, visit_types_created=0, visit_types_updated=9.
# No patients, appointments, WhatsApp messages, files, prices, or booking slots were created.
# Seeded booking demo setup: settings_created=0, settings_updated=7, schedules_created=0, schedules_updated=5.
# No patients, appointments, WhatsApp messages, uploads, secrets, or payments were created.
# Current patient_count=0, appointment_count=0.
```

```bash
python manage.py test
# Found 193 test(s).
# Ran 193 tests.
# OK
```

## Remaining Risks and Production Needs

- Email verification policy is not implemented.
- Password reset/account recovery is not implemented.
- Patient identity verification policy is not defined.
- Privacy/legal review is still required before public launch.
- Portal auth and linking rate limits should be reviewed against real staging traffic and shared cache behavior.
- Abuse monitoring and alerting are not implemented.
- PostgreSQL and Redis/shared-cache staging validation is still required.

## Recommended Next Batch

Use restricted staging with PostgreSQL and Redis/shared cache to validate the Batch 8 portal foundation under production-like settings before expanding the portal. The next feature batch should focus on account recovery, email verification/reset policy, identity verification policy, and abuse monitoring rather than uploads or medical records.
