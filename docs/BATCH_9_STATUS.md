# Batch 9 Status - Portal Account Security and Patient Portal Polish

## Scope Implemented

Batch 9 strengthens the Batch 8 patient portal foundation without expanding into uploads, medical records, WhatsApp, payments, diagnosis, triage, treatment, or medical automation.

Implemented:

- Authenticated patient password-change flow.
- Authenticated patient account/profile summary page.
- Static account recovery policy page.
- Consistent portal navigation across authenticated portal pages.
- Clear patient-facing portal limits and emergency reminders.
- Cache-backed portal rate limiting for appointment linking, login, and registration.
- Deployment smoke summary for portal account-security routes.
- Security/privacy regression tests for account security, navigation, rate limiting, and route boundaries.

## Routes Added

Arabic/default:

- `GET /portal/account/`
- `GET|POST /portal/password/change/`
- `GET /portal/account-recovery/`

English:

- `GET /en/portal/account/`
- `GET|POST /en/portal/password/change/`
- `GET /en/portal/account-recovery/`

Existing portal and booking routes remain unchanged. Public booking still works without login.

## Password Change Behavior

- Login is required.
- Responses are no-cache.
- POST uses CSRF protection.
- Password fields are marked with `sensitive_post_parameters`.
- Django `PasswordChangeForm` is used, including Django password validation.
- Password storage uses Django password hashing.
- Successful password change calls `update_session_auth_hash`, so the current session remains valid.
- The success message is generic and does not expose internal user IDs.
- Email password reset is not implemented in this batch.

## Account Page Behavior

The account page shows patient-safe account information only:

- display name,
- masked username/phone,
- email if provided,
- linked appointment count.

Phone and email self-service editing is not implemented. Account updates require clinic support for now until a verified ownership policy is approved.

The account page does not show:

- internal user IDs,
- internal appointment IDs,
- appointment public tokens,
- staff notes,
- booking notes,
- status history notes,
- audit logs,
- medical records,
- uploads/private media,
- WhatsApp messages,
- payment administration details.

## Account Recovery Behavior

Account recovery is a static policy page for now.

It does not:

- collect sensitive medical data,
- ask for phone/email through a form,
- send email,
- send WhatsApp messages,
- create support tickets,
- expose whether an account exists.

Recovery is clinic-assisted until a secure production recovery process is approved.

## Rate Limiting

Patient portal rate limits use Django cache:

- Appointment linking throttles authenticated user/IP and normalized phone hash when available.
- Login throttles IP and normalized phone hash when available.
- Registration throttles IP and normalized phone hash when available.
- Cache keys hash sensitive identities.
- Raw public tokens, raw phone numbers, and passwords are not stored in portal cache keys.
- Defaults are intentionally light for local development and require staging/production tuning with Redis or another shared cache.

Public booking rate limiting remains separate and unchanged. Public booking still uses UUID `public_token` success URLs and does not require login.

## Portal Navigation and Polish

Authenticated portal pages now consistently include:

- Dashboard,
- Appointments,
- Link Appointment,
- Account,
- Change Password,
- Logout.

Logout remains POST-only with CSRF protection.

Portal copy now repeats key patient-facing boundaries:

- the portal is not for emergencies,
- uploads are not available yet,
- medical records are not available yet,
- WhatsApp is not implemented,
- payments are not implemented.

## Deployment Smoke

`deployment_smoke` now summarizes account-security routes as importable without requiring patient accounts and without printing patient data.

It does not require email backend configuration because email password reset is not implemented.

## Explicitly Out of Scope

- Deployment.
- Commits, pushes, or merges.
- Real secrets or credentials.
- Real patient data.
- File uploads.
- Medical records.
- Doctor/staff internal notes in patient pages.
- Audit logs in patient pages.
- Status history notes in patient pages.
- WhatsApp API sending.
- WhatsApp webhooks.
- Online payments.
- Diagnosis, triage, treatment, or medical AI.
- Weakening public booking UUID token security.
- Numeric public appointment success URLs.
- Weakening staff-only appointment operations.
- CSRF bypasses.
- Cacheable portal pages.

## Remaining Production Requirements

Before public portal launch:

- verified email or phone ownership policy,
- secure account recovery process,
- patient identity verification policy,
- legal/privacy review,
- production rate-limit tuning,
- abuse monitoring,
- monitoring and alerting,
- PostgreSQL staging validation,
- Redis/shared-cache staging validation,
- reverse proxy and HTTPS validation,
- backup/restore drill with synthetic data.

## Recommended Next Batch

Validate the portal account-security foundation in restricted staging with PostgreSQL and Redis/shared cache before adding any new patient data surface.

Recommended next work:

- tune portal login, registration, appointment-link, and public booking rate limits against Redis,
- define verified email/phone ownership policy,
- design secure account recovery operations,
- add monitoring and alerting for portal abuse,
- complete legal/privacy review,
- keep uploads, medical records, WhatsApp, payments, and medical automation out of scope until their security designs are approved.
