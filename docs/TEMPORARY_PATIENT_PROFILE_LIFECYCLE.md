# Temporary OTP patient profile lifecycle

Owner-approved outage behavior, based on GitHub main
`1b0c288eb82200a7b16b8117b4e5e9f3cf8219a3`.

## Registration and ownership

With `PATIENT_OTP_TEMPORARY_MODE=true`, successful registration creates the User,
a NEW Patient linked to that exact User, and membership in
`patient_phone_unverified_temporary` in one database transaction. The Patient
retains the full submitted name even when Django's auth first-name field is
shorter. Its phone is normalized from the submitted number. No OTP challenge,
verification timestamp, or proof of phone ownership is created.

The existing staff Patients list shows the Patient immediately and displays
`الهاتف غير موثّق` / `Unverified phone`. Its normal user relationship governs
portal ownership, consultations and medical records. The group does not grant
permissions. A group with any permissions causes registration to fail closed;
existing membership in a permission-free marker group is expected and allowed.

The shared profile resolver rejects User identity conflicts, normalized Patient
phone conflicts, and matching raw-only legacy Patient phones. A conflict never
authorizes claiming or attaching an existing Patient. Registration returns the
existing neutral unavailable response, with no partial User/Patient creation.

## One-time backfill: prepared only, not executed in production

After owner authorization, run the following in the intended application
environment. The default is a read-only preview:

```sh
python manage.py backfill_temporary_patient_profiles
```

Review the counts, then use this command only when the owner has authorized
production execution:

```sh
python manage.py backfill_temporary_patient_profiles --apply
```

The command emits one JSON object containing integer counts only:

| Count | Meaning |
| --- | --- |
| `candidates` | Marked, active, non-staff, non-superuser accounts initially found without a linked Patient. |
| `would_create` | Conflict-free candidates in preview mode; preview creates nothing. |
| `created` | New linked Patients committed by `--apply`. |
| `skipped_conflict` | Invalid account phones or existing identity/Patient ownership conflicts. |
| `skipped_ineligible` | Candidates whose eligibility changed before their locked recheck. |
| `failed` | Candidate transactions that rolled back because of another error. |

Each candidate is locked and rechecked in its own transaction. New profiles use
the account's stored full name and normalized current username. The command
does not claim phone matches, overwrite linked profiles, remove markers, send
OTP, or grant verification. It prints no identities, phone numbers, record
identifiers, or exception text. No per-account logging is added.

Rerunning is safe: successful candidates now have a profile and are excluded.
Conflicts remain skipped until independently resolved through an authorized
ownership process. A nonzero `failed` count means some candidates rolled back;
do not interpret command completion as success for those candidates. Review
aggregate outcomes before retrying. The command also works after the outage
flag is disabled; its selection always requires the persistent marker.

## When real OTP delivery returns

With `PATIENT_OTP_TEMPORARY_MODE=false` and the existing
`ACCOUNT_PHONE_CHANGE_OTP_SENDER` delivering real OTP, marked users can open
Account → `تأكيد رقم الهاتف` / `Verify phone number`. The action sends a real
code to the authenticated account's current phone; a client-supplied replacement
number cannot change this target. The existing account security page hosts the
send, verify and resend actions with authentication, CSRF and phone-change rate
limits.

Users can instead use the existing Change Account Phone form, which still
requires the current password and sends OTP to the NEW phone. The old,
unverified phone requires no OTP. Both paths reuse
`AccountPhoneChangeChallenge` and `apps/patients/phone_change.py`.

Start, resend and final verification reject ambiguous or mismatched profile
ownership and phone conflicts. A marked account must already have a consistent
linked Patient; missing older profiles should go through the authorized
backfill first. Verification never creates or relinks a Patient.

Only successful OTP verification removes the marker. Current-phone success
leaves the entire Patient row unchanged. New-phone success changes the User
username and the SAME Patient's phone fields through the existing service,
including its existing optional upcoming-appointment propagation and historical
record behavior. Both keep Patient.id, medical history and ownership intact.

Invalid, expired, exhausted, conflicting or failed-send requests grant no
verification and preserve the marker. Resend uses the existing cooldown and
challenge invalidation. Normal verified accounts retain their OTP registration,
recovery and new-phone behavior, and have no temporary status badge.

## Rollback and scope

Disabling the outage flag restores normal OTP registration. It does not delete
Patients or clear existing markers. Switching the flag back on blocks phone
verification/change at both the view and service boundaries. No migration,
dependency, provider, deployment or Render change is required by this PR.

Medical/media ACLs, public booking, consultation ACLs and recovery code are
unchanged. Issue #62 media durability files are outside this change.

## Focused regression coverage

`apps.patients.test_temporary_patient_lifecycle` covers registration/profile
atomicity, submitted names, both staff badge languages, safe backfill and
counts-only output, real current/new-phone verification, failure paths,
ownership conflicts, authentication/CSRF/rate limits and the existing appointment
propagation contracts applied to marked accounts. Existing outage, account OTP,
profile resolution, phone change, dashboard and privacy suites are run alongside
it. All test identities, uploads and clinical content are synthetic. Exact
commands and results are recorded in the PR verification report.
