# Owner closeout #48

Repository: `sami77337/khaled-badran-clinic`.
Branch: `owner-closeout-batch-48`.
Base reviewed: `main` at `a0b53e657c33da141f9c35d8c5cef15e2e38a9b2`.
Original PR head reviewed: `3a75ce935ae7726630d2c2648186b2d2d5efff16`.

This batch implements the owner's account OTP, immediate patient reviews,
password control, doctor text, and existing-logo integration requirements.
Production data, dependencies, public-case architecture, private media controls,
and `revuse/` are outside the changes. No production data operations were run.

## Issues corrected

| Original issue | Result |
| --- | --- |
| `PatientsConfig.ready()` replaced functions at runtime and retained password-only registration for development/tests. | Explicit AR/EN URL callbacks use `account_views`; OTP is required in every environment. The obsolete view and form account-creation paths are removed. |
| Cache read/modify/write allowed verification/reset races. Failed attempts refreshed expiry and resend reset the attempt count. | A small `AccountOtpChallenge` model holds temporary state. PostgreSQL row locks serialize attempts and one-time consumption. Expiry and the five-attempt budget never slide on resend/failure. |
| Recovery disclosed account status through send failures and different resend messages. Registration rejected known phones before verifying possession. | Valid phone inputs follow the same initial, resend, and failure response path. A neutral OTP is sent for either account state; eligibility is checked after possession is proved. Unknown, inactive, staff, and superuser accounts cannot receive recovery grants. |
| Combined phone/IP counters could be bypassed by changing one value; cache errors allowed requests. | Independent IP and phone counters plus a phone-wide cooldown; cache failures deny new sends, verification, and resets. |
| Recovery grants were reusable during concurrent requests and survived other password changes. | The session-bound grant is checked against the current account identifier/password, locked with the user, and deleted after reset. Password change, phone change, deactivation, or staff/superuser promotion invalidates it. |
| Doctor content assignment ran outside a rendered template block; custom existing Doctor bio was ignored by fallback, and credential text was not editable. | Content is resolved inside the existing doctor-page content block. Blank fields preserve approved text and the existing Doctor biography. Credential text is editable in both languages. |
| Recovery password buttons were outside the script's initialization selector. | Login, registration, and recovery initialize the same accessible toggle behavior and preserve input clearance in RTL/LTR. |
| A rate-limited reset added an error to an unbound password form and raised a server error. | Both rate exhaustion and cache outages return the localized retry message without changing the password or consuming the valid grant. Regression tests reproduce the original error and verify recovery after the block clears. |
| Logo styling presented the old placeholder SVG as the approved logo and omitted the dashboard stylesheet. | A single exact optional asset path is shared by public/auth/dashboard marks and favicon links; the existing identity remains until the actual file is supplied. |
| Tests/copy still required approval after patient review saves. | Submission and valid edits are immediately public; staff moderation and revision checks remain intact. |
| The new case regression found that metadata edits swapped the validated form instance for an unchanged locked row. Titles and consent changes were silently discarded. | The case row is locked before the form is bound and validated. Edited text and consent now persist, and withdrawing case consent unpublishes the case. |

## Account behavior and configuration

- Registration collects name, phone, optional email, and a validated password.
  Only the password hash is held in temporary challenge state. Neither a User
  nor a linked Patient account is created until the six-digit OTP succeeds.
- The normalized phone is the unique account username. A phone already linked
  to another Patient account also prevents duplicate registration. Unlinked
  booking records are never automatically claimed by registration.
- Challenges expire after 10 minutes. Resends require 60 seconds, including
  restarts in a different session. The challenge permits five total verification
  attempts. Send/start operations share independent IP/phone limits of six per
  hour; existing registration start limits still apply. Verification and reset
  each allow 20 attempts per hour per IP and per phone.
- Each challenge is bound to a cryptographically random browser-session secret
  and to its registration/recovery purpose. Pending profile details, the hash,
  intended phone, and safe return URL are held server-side. Verification ignores
  client attempts to replace these values.
- Recovery grants expire 10 minutes after OTP verification. Django's existing
  `SetPasswordForm` and configured password validators validate the replacement.
  Reset does not log the user in. Django invalidates old authenticated sessions
  when the password changes.
- The shared sender abstraction is unchanged. Optional
  `PATIENT_ACCOUNT_OTP_SENDER` selects a callable; when blank it falls back to
  `GUEST_CONSULTATION_OTP_SENDER` (the existing WhatsApp authentication OTP
  template). No live sender credentials or provider messages were used in tests.
- Failure/timeout invalidates the generated code and retains a generic response.
  A new code can be requested after cooldown. An unavailable provider never
  permits password-only registration or recovery.
- Completed challenges are deleted atomically. Expired temporary records are
  deleted when another account challenge starts; their timestamps enforce
  expiry even when no new request arrives. They are not exposed in admin.
- Production uses the existing PostgreSQL/shared Redis deployment requirements.
  No local-memory cache or development-only authentication bypass is introduced.

## Staff content and moderation

Use **Doctor Profile** / **الملف التعريفي للطبيب** in the staff dashboard to open
the existing Django admin **Doctor public page content** surface at
`/admin/core/doctorpagecontent/`. The dashboard link is shown only to staff with
view or change permission. An owner/superuser can grant authorized staff
`view`, `add`, and `change` permissions for that model. No production permissions
were changed during this work.

Choose the existing Doctor and edit AR/EN hero summary, credential label,
professional biography, experience, education/training, boards/certifications,
memberships, awards, languages, specialties, and conditions. List sections use
one item per line. Memberships accept `Label | ACRONYM`. Blank fields preserve
the current public text. Existing Doctor admin fields continue to own name,
title, and specialty. The public layout, section structure, and CSS are preserved;
staff text is escaped by Django templates.

Patient portal reviews set `is_approved_for_publication=True` and `is_active=True`
on each valid submission/edit. A later valid patient edit republishes the review,
as specified by the owner. Staff can hide it by clearing approval, deactivate it,
or delete it through `/admin/core/publicreview/`. Existing signed revision checks
prevent a stale moderation form from overwriting a newer patient edit. Imported
reviews retain their existing moderation requirements.

## Exact logo asset path

The owner-approved logo binary is absent from the branch. Supply it without
redrawing or changing its visual identity at:

`static/img/brand/kb-approved.png`

Its static URL is `/static/img/brand/kb-approved.png`. The shared template tag
uses this file when present. Header, auth, dashboard, and favicon references
switch together. Images use `object-fit: contain` inside responsive slots so
the original proportions are retained. Until then, the existing text identity
and existing SVG favicon remain; there is no broken logo request or fabricated
replacement. The pre-existing untracked `map.png` was not modified or committed.

## Migrations

- `core/0004_doctorpagecontent.py`: already present on the PR; creates the editable
  Doctor page content model.
- `core/0005_doctorpagecontent_credential_label_ar_and_more.py`: adds the two
  editable credential labels.
- `patients/0008_accountotpchallenge.py`: creates temporary account OTP/grant
  state. No account or patient data is migrated or seeded.

All migrations were applied only to disposable test databases. Production must
apply these schema migrations through its normal release process.

## Existing public cases

The existing staff create/edit/add-assets/publish/unpublish flow is retained.
Regression coverage exercises before images, after images, MP4 uploads, case
consent, separate asset consent, publication, unpublishing, missing files,
staff-only access, and unchanged private medical-media visibility. No public
case was imported, and no real patient/media data was used.

## Validation

Validation uses the existing disposable local PostgreSQL 16 and Redis 7 services,
development settings, synthetic accounts, and mocked OTP senders. No production
connection, dataset, private media, or provider credential is used.

| Check | Result |
| --- | --- |
| `python -B manage.py check` | PASS; no issues. |
| `python -B manage.py makemigrations --check --dry-run` | PASS; no missing migrations. |
| Focused OTP, PostgreSQL concurrency, password layout, doctor content, and public-case tests | PASS; 55 tests. The added consent-withdrawal regression also passes separately on SQLite. |
| Full suite on PostgreSQL + Redis | 946 tests. The final local result is recorded in `.cache/owner48-verified-postgres.log`; pushed-revision results are recorded in PR #48 Checks. |
| Staff query budgets and row-growth regressions | PASS; seven focused tests. Counts include the two fixed permission lookups for the doctor editor link, and row-growth comparisons use fresh user instances for equal cache conditions. |
| `python -m pip check` | PASS; no broken requirements. |
| Ruff on changed account handlers, dashboard handlers, and their new regressions | PASS. |
| `git diff --check` and staged diff check | PASS. |
| `python -B manage.py check --deploy` under development settings | Six expected local security warnings for development HTTPS/cookies/HSTS/debug and the synthetic secret; not a production deployment check. |

The browser regression covers 48 password-visibility cases across AR/EN,
login patient/staff modes, registration, and recovery at 320, 360, 390, 430,
768, and 1024 pixels. It checks working show/hide controls, input clearance,
accessible names/states, focus, and page overflow. The existing wider rendered
suite also covers reviews, maps, cases, medical text, attachments, notifications,
phone controls, and consultation layouts.

The first resumed full run found the public-case metadata persistence bug above.
The fix keeps the consent gate and is covered by both the complete
upload/edit/publish/unpublish workflow and explicit consent withdrawal.

Local run logs are under `.cache/owner48-*.log`; they are excluded from Git.
[PR #48's Checks](https://github.com/sami77337/khaled-badran-clinic/pull/48/checks)
and the PR description record the final results for the pushed revision. The
optional owner-data test is skipped when no external review dataset is supplied.

## Remaining owner deployment work

This code batch does not complete the separate production data operations in
`docs/project-handoff/OWNER_PRODUCTION_CLOSEOUT_REQUESTS_AR.md`:

- Install the exact approved logo asset at the path above.
- Load the 57 owner-approved Google reviews into the identified production
  database using the existing importer; keep the dataset outside Git.
- Load owner-provided public case assets only with confirmed case and asset
  publication consent, through the existing manager.
- Complete the scoped synthetic demo reset after the production target and
  exact records eligible for replacement are established.
- Apply release migrations and verify the configured live WhatsApp OTP sender.

PR #48 remains unmerged while these closeout items are outstanding. Local
validation uses synthetic identities and mocked senders; it is not evidence
of production deployment or successful live WhatsApp delivery.
