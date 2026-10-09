# Clinical reply least-privilege gate — controlled rollout

Scope: owner-approved legal/privacy remediation #113, B03/T11, **clinical writes only**.
This is an implementation and verification plan, not an assertion that licensing,
provider identity, healthcare consent or real-world staff roles have been approved.

## Confirmed baseline defect

Both `dashboard_consultation_detail` (registered/guest POST) and
`consultation_services.update_consultation_reply` authorize any active
`is_staff` user to change clinical text, audio and consultation status.
Django Admin model permissions are not currently checked by those operations.

## Narrow code change

Reuse the two existing Django Groups provisioned in PR #120 and their
model permissions; no new roles, migrations or third-party dependencies:
- Clinicians must have the exclusive `KBC Doctor` classification (or the
  documented, strictly scoped authorized superuser exception). A `KBC Clinic
  Staff` account, unassigned user or dual-group account cannot write a
  clinical reply even when a model permission was granted directly.

- Registered clinical reply/status/audio writes require
  `patients.change_consultation`.
- Guest clinical reply/status/audio writes require
  `patients.change_transientconsultation`.
- Request authorization is checked before form validation/file processing;
  the service layer enforces it independently to stop API/internal bypass.
- Authorized clinician and active superuser behavior require both role
  and Django model-permission checks. Staff without privileges receive HTTP 403 on POST and
  a read-only, localized state on the existing detail page; the existing
  audio recorder/form is not rendered.
- Existing patient/guest access, OTP, booking, attachments, visibility and
  clinical storage behavior are not rewritten.

## Production activation gate — not yet verified

**Do not merge/deploy this branch until a named clinic operator validates
actual production staff accounts privately.** Required evidence:

1. Confirm the active treating doctor's individual account has the
   exclusive `KBC Doctor` group plus `patients.change_consultation` and
   `patients.change_transientconsultation`, or has documented authorized
   superuser status. Verify with the exact authenticated account used for replies.
2. Confirm receptionist/administrative-only accounts have exclusive
   `KBC Clinic Staff` membership and neither clinical model permission;
   if a non-doctor requires a clinical write, that delegation needs a documented
   owner/clinical decision before granting it.
3. Verify a synthetic registered and guest reply using an authorized account
   in a controlled environment; verify non-clinical staff POST denial, no
   clinical/status/file/notification write, and recorder visibility.
4. Check AR/EN pages and mobile/desktop regression, including existing audio
   replacement/rollback and guest read access.
5. Do not publish staff names, usernames, phones, real consultations, role
   screenshots, connection strings, or other account data in Git/PR/chat.

The hosted Render connector cannot perform an SQL query against the private
production Postgres database while external allowlisting is disabled; never
weaken its network isolation just to inspect account permissions.

## Remaining permissions work (not claimed completed here)

Current consultation detail GET, attachments/audio downloads, patient medical
records and other Dashboard actions retain legacy staff-only read/manage access.
They require a separate owner-validated role-by-action mapping and bounded
verification before changing existing clinic workflows. No broad Django
Admin permission or global staff setting is changed by this PR.

No code migration, existing staff-role assignment, private-data query or
production change should occur until the activation gate is approved.

## Acceptance / test plan

- Staff-only no-change-permission user cannot submit clinical text/audio/status.
- Registered-only permission cannot write guest replies, and vice versa.
- Authorized clinician can save existing registered and guest text/audio/status.
- Inactive staff and patient users cannot write; superuser retains usual
  Django permission behavior.
- Existing CSRF, row locks, transaction rollback and privacy no-store remain.
- Add synthetic test fixtures with the Doctor group and scoped native model
  permissions, including direct-permission and conflicting-group bypass tests.
- Django checks, migration check, full CI and production-like PostgreSQL/Redis
  gate required; create PR and leave unmerged until account validation.
