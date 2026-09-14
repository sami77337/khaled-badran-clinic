# Temporary OTP outage mode

This change is for the owner-approved WhatsApp OTP outage only. The setting is
`PATIENT_OTP_TEMPORARY_MODE=false` by default. Setting it to `true` activates the
temporary behavior below. No deployment or environment change is part of this PR.

## Behavior

| Flow | Temporary mode enabled |
| --- | --- |
| New patient registration | Existing form/password validation and IP/phone rate limits; atomic creation of the auth User, a new linked Patient with the submitted name/normalized phone, and the unverified marker, without OTP. The Patient is immediately available to staff and its authenticated owner. |
| Registration identity conflicts | Neutral failure for existing account identities, linked or unlinked patient records, and matching legacy raw-phone records. No medical record is claimed. |
| Guest consultation | Normalize and retain the submitted phone in session, validate and privately store the submission/attachments, schedule the existing `new-consultation` staff event, then clear submission state and show a generic receipt. |
| Guest private detail, attachments and audio | Existing browser-bound verified grant remains required. Requests without that grant return 404 in temporary mode. A supplied phone or UUID confers no access. |
| Account/password recovery, account phone change, appointment-link recovery | Server-side refusal before processing any start, resend, verify, reset or link action. AR/EN notices and unavailable UI actions. |
| Guest OTP verification/re-verification | Unavailable. Existing legitimate, unexpired grants can still access their own consultation. |
| Authenticated password change | Available, with existing password validation and session handling. |
| Public booking, authenticated consultations, staff dashboards and Web Push | Available. Existing ownership, notification and private-media boundaries remain in use. |
| Linking with an existing appointment confirmation token | Existing token-plus-phone flow remains available; it does not use OTP and has not been changed. |

## Persistent verification state and rollback

Temporary accounts belong to the permission-free Django auth group
`patient_phone_unverified_temporary`. Registration fails closed if this group has
permissions. The group is a marker, never an authorization grant. The account
page identifies these phones as unverified even after the flag is disabled.
The staff Patients list also displays `الهاتف غير موثّق` / `Unverified phone`
using the existing dashboard status pill. Group membership supplies status only.

See [Temporary patient profile lifecycle](TEMPORARY_PATIENT_PROFILE_LIFECYCLE.md)
for the counts-only backfill command and the supported current/new-phone OTP
verification paths after service returns. These paths preserve the linked
Patient and remove the marker only after successful real OTP verification.

Guest submission creates no challenge, OTP, `verified_at` timestamp or access
grant. Staff views identify the phone as unverified at submission unless a
matching challenge contains verification evidence from before creation. Later
legitimate re-verification does not retroactively change that submission label.

Disable/unset the flag to restore the existing OTP registration, guest entry and
sensitive-operation routes. Temporary guest form state cannot satisfy the
restored OTP requirement. No database migration, dependency, route deletion or
sender/provider change is required. Keep the account marker and stored guest
submissions on rollback: disabling the mode does not verify a phone. Existing
OTP challenges retain their original expiry and verification requirements.

## Security tradeoffs and limits

- Without phone proof, someone can submit a new account or guest question using
  an incorrect or someone else's previously unused number. Rate limits constrain
  abuse but cannot establish phone ownership. Clinic staff must treat the phone
  as unverified when handling the request.
- Direct signup necessarily distinguishes successful new registration from
  unavailable registration. Conflict responses are neutral and disclose no
  account/patient details or conflict type; existing rate limits remain active.
- Existing medical records are never automatically linked by temporary
  registration or backfill. Both reuse profile resolution's normalized and legacy
  raw-phone conflict checks.
  Public booking's existing phone matching is unchanged, as requested; this
  mode does not provide a new guarantee of phone ownership for booking.
- Unverified guests receive no online private follow-up access from submitting.
  When OTP service is restored, the existing legitimate verification flow is
  required to access a consultation through a known detail link.
- The marker is intentionally conservative. This change adds no bulk verification
  or automatic removal of the unverified account tag.

## Verification

The dedicated regression suite is `apps.patients.test_temporary_otp_mode` and
uses only synthetic identities, medical text and uploads. It covers both
languages, flag rollback, stale OTP state, identity conflicts, private detail/
media/audio denial, CSRF, rate limits, storage rollback, staff events and the
flows that remain available. The PR report records the executed commands,
results and local database limitations.

Local verification on Windows, Python 3.14 / Django 5.2.15, 2026-09-13:

- `python manage.py test apps.patients.test_temporary_otp_mode apps.patients.test_account_otp apps.patients.test_transient_consultations --noinput --verbosity 1`: **88 passed** (final run, 39.671s).
- `python manage.py test --noinput --verbosity 1`: **1,021 tests; 1,015 passed, 5 skipped, 1 existing Windows-specific failure** (395.888s). The failure is `ProductionVapidAutoProvisionTests.test_auto_provision_persists_private_key_and_exposes_only_public_key`: the existing test expects POSIX mode `0600`, while Windows reports `0666`. Running that single test on an untouched detached checkout of base `57777f82f15de9777a4e675ab9c917d0abe3461c` reproduced the identical failure. No notification implementation or test was changed.
- With `PATIENT_OTP_TEMPORARY_MODE=true`, the existing security/available-flow selection below: **309 passed** (75.731s). An initial 310-test selection also included the default-mode phone-picker visibility test, which intentionally conflicts with temporary mode; its two language subcases failed. That test remains unchanged and passed in the full default-mode suite. Dedicated temporary-mode tests assert the disabled UI and server-side refusal.
- `python manage.py makemigrations --check --dry-run`: **No changes detected**.
- `python manage.py check`: **No issues**.
- `git diff --check`: **Passed**.
- `python manage.py check --deploy` under local development settings: **6 warnings** for local HSTS/HTTPS redirect, development secret, secure session/CSRF cookies, and DEBUG configuration. No production environment was modified.

The five full-suite skips were two PostgreSQL account-OTP concurrency tests,
one PostgreSQL reminder-concurrency test, one Redis worker-coordination test,
and an optional owner-data review test. No owner data was supplied. Docker's
Linux engine was unavailable locally, so PostgreSQL/Redis integration was not
claimed as verified.

The exact enabled-mode selection (set the environment flag to `true` for this
test process only):

```text
python manage.py test
  apps.patients.test_expansion.ConsultationExpansionTests
  apps.patients.test_expansion.AuthenticatedBookingExpansionTests
  apps.patients.test_expansion.SafeProfileResolutionTests
  apps.patients.tests.PatientPortalMedicalRecordVisibilityTests
  apps.patients.tests.PatientPortalPrivacyTests
  apps.patients.tests.PatientPortalPasswordChangeTests.test_anonymous_password_change_redirects_to_portal_login
  apps.patients.tests.PatientPortalPasswordChangeTests.test_authenticated_user_can_change_password_and_keep_session
  apps.patients.tests.PatientPortalPasswordChangeTests.test_password_change_uses_django_password_validation
  apps.patients.tests.PatientPortalPasswordChangeTests.test_password_change_page_is_no_cache
  apps.patients.tests.PatientPortalPasswordChangeTests.test_csrf_is_enforced_for_password_change_post
  apps.records
  apps.booking
  apps.notifications.tests.SubscriptionTests
  apps.notifications.tests.DeliveryTests
  --noinput --verbosity 1
```

The line breaks above are for readability; the labels were passed as arguments
to one command. All generated uploads and test databases used synthetic data.
