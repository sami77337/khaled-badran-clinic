# Legal and Privacy Operations

Batch 11 legal/privacy operations plan for Dr. Khaled Badran Clinic.

This document is not legal advice and is not legal approval. It does not approve
public launch, patient onboarding, medical records, uploads, WhatsApp
automation, payments, or clinical automation.

## Legal Pages Are Drafts

Current legal pages are operational drafts:

- privacy policy,
- terms of use,
- medical disclaimer,
- WhatsApp use policy.

They require qualified legal/privacy review before public launch.

## Privacy Review Requirement

Before launch, review:

- what personal data is collected,
- what appointment data is shown publicly through bearer-style UUID success
  links,
- what patient portal data is shown after login,
- what staff-only data exists,
- log and monitoring data,
- retention and deletion processes,
- backup and restore data handling,
- incident response and notification obligations.

Use `docs/DATA_EXPOSURE_MATRIX.md` as the technical data-surface inventory.

## Medical Disclaimer Review Requirement

The medical disclaimer must be reviewed before launch.

It must remain clear that:

- the site is informational and operational,
- the site is not for emergencies,
- the site does not provide diagnosis,
- the site does not provide triage,
- the site does not provide treatment automation,
- the site does not replace medical consultation.

## WhatsApp Policy Review

WhatsApp sending and webhooks are not implemented.

Before any WhatsApp feature:

- review consent,
- review opt-out,
- review message content boundaries,
- prohibit detailed automated medical advice,
- define logging boundaries,
- define credential handling,
- define webhook verification,
- define incident response and token rotation.

Do not implement WhatsApp API sending or webhooks in Batch 11.

## Account Recovery Policy Review

Current account recovery is clinic-assisted and informational only.

Before self-service recovery or password reset:

- define verified phone/email ownership,
- define identity verification process,
- define support staff procedure,
- define abuse controls,
- define patient privacy checks,
- document failure and escalation paths.

Email password reset remains disabled until this policy exists.

## Identity Verification Policy

Before broader patient portal launch:

- define how a patient proves identity,
- define what staff may ask,
- define what staff must not ask in insecure channels,
- define how appointment linking is verified,
- define how contact changes are handled,
- define how suspected account takeover is escalated.

Do not link medical records by name alone.

## Deletion and Retention Process

Before launch, define:

- retention periods,
- deletion request intake,
- identity verification for deletion requests,
- what records can be deleted,
- what records must be retained,
- what records can be restricted or anonymized,
- audit log retention,
- backup retention,
- legal hold process.

Do not implement automated deletion of clinical or operational records without
legal/privacy approval.

## Consent Requirements for Future Publication or Testimonials

Future publication of testimonials, photos, videos, case descriptions, or
before/after material requires:

- separate explicit consent,
- scope of publication,
- withdrawal process,
- retention period,
- approved wording,
- review before posting.

No publication/testimonial workflow is implemented in Batch 11.

## No Real Patient Data in Demos

Demos must use synthetic data only.

Do not use:

- real patient names,
- real phone numbers,
- real emails,
- real appointment history,
- medical notes,
- diagnoses,
- reports,
- images,
- audio,
- video,
- WhatsApp messages,
- payment data.

## Data Incident Escalation Placeholders

Incident contacts are placeholders until owner approval:

- Project owner: `TBD`
- Technical operator: `TBD`
- Legal/privacy reviewer: `TBD`
- Communications owner: `TBD`

Follow `docs/INCIDENT_RESPONSE_RUNBOOK.md` for incident handling and escalation.

## Cross-Links

Related documents:

- `docs/DATA_EXPOSURE_MATRIX.md`
- `docs/SECURITY_REGRESSION_CHECKLIST.md`
- `docs/INCIDENT_RESPONSE_RUNBOOK.md`
- `docs/BACKUP_RESTORE_DRILL.md`
- `docs/STAFF_ACCESS_GOVERNANCE.md`

## Current Batch 11 Status

Legal/privacy operations are documented as blocked pending qualified review.
Batch 11 does not provide legal advice, final legal approval, or launch
approval.

Design status: No design work performed by Codex.
