# Patient Portal review publication — consent and withdrawal

Owner-approved, bounded implementation under #113 (L42 / T18 / B02 + B07).
This is code behavior, not final legal certification or Google content approval.

## Publication

- Only an authenticated, active non-staff account can author its own PATIENT_PORTAL review.
- An explicit **unchecked** AR/EN checkbox identifies what will be published:
  chosen display name (or the existing generic patient label), star rating
  and review text, on the clinic's public website.
- A missing consent checkbox rejects creation/editing without changing existing
  text, status or consent evidence; editing still republishes immediately only
  after renewed affirmative consent (existing owner-approved product behavior).
- The backend records server time, language and immutable code-level copy version
  `portal-review-publication-v1`, plus a minimal AuditLog event for each
  accepted publication. No review body, patient phone, email or medical detail
  is copied into consent audit metadata.

## Withdrawal / moderation

- The patient's own POST + CSRF action `/portal/review/<id>/withdraw/`
  (English: `/en/portal/review/<id>/withdraw/`) records the first withdrawal
  timestamp and immediately hides the review from Home/Reviews and their
  published aggregates. The private review remains available to the patient
  for editing or deletion; a repeated withdrawal does not overwrite the
  original withdrawal time or create duplicate audit events.
- Public review queries reject rows marked withdrawn even if stale publication
  flags are accidentally set true.
- Staff may Hide/Show reviews as before **except** that withdrawn reviews cannot
  be shown by Dashboard or Django Admin; neither surface renders a Show control,
  and forged Show POSTs fail. Ownership and signed revision/row-lock rules remain.
- The patient alone may re-publish with a new explicit checked consent on a valid
  edit; this resets the withdrawal marker, records new evidence, and makes a
  revised review public. Existing permanent delete remains separate.
- No extra Google/OTHER moderation or import controls are altered.

## Existing data and constraints

- Migration `core.0008_publicreview_publication_consent` adds only nullable or
  empty evidence columns; **no retroactive consent backfill** and no bulk hide
  or deletion of legacy reviews. Existing owner-approved published legacy rows
  stay visible unless already hidden/withdrawn; their evidence is **unknown**,
  not claimed to be proven. Verification of historical authority is an
  administrative/legal follow-up, not a fabricated database field.
- The approved public case media feature, Figma design tokens, booking, OTP,
  storage and medical records are unchanged.
- Google-sourced review dataset rights and publication policy remain GATE-06
  and the owner's later source-specific decision; no imported row is modified.
- Retention of audit evidence is subject to the separate approved retention
  schedule (GATE-05); this patch does not invent deletion periods.

## Verification

- AR/EN GET/POST, unchecked vs checked consent, exact evidence, tampering,
  staff/other-patient isolation, CSRF, POST-only withdrawal and idempotence.
- Public visibility and rating/count, immediate withdrawal, staff Show block,
  safe re-consent and old review preservation.
- Django migrations/checks and existing patient/staff/admin responsive tests.
- Document actual CI SHA and Render production deploy evidence before marking
  this subset runtime-verified. Use synthetic identities only.
