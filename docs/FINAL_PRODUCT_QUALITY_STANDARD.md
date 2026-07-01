# Final Product Quality Standard

Batch 12 defines the quality bar for final product completion. This is a
planning standard only; it does not authorize implementation or launch.

## Product Experience Standard

The final product should feel like a professional clinic system that is ready
for repeated real use by patients, the doctor, and authorized staff.

Required qualities:

- professional visual experience, governed by approved Figma/design handoff;
- smooth patient booking with clear steps and low friction;
- comfortable doctor/admin workflow for daily operations;
- high-quality Arabic and English copy;
- mobile-first patient experience;
- predictable desktop dashboard behavior for the doctor/admin;
- clear patient-facing explanations without exposing internal operations;
- fast, calm, and reliable interactions;
- privacy and security by default.

## Patient Booking Quality

The booking flow should remain:

- login-free for public booking;
- clear about visit type, date, time, and patient contact fields;
- resilient to accidental duplicate submissions;
- safe on public success URLs by using non-enumerable UUID tokens;
- free from internal IDs, staff notes, audit logs, medical records, uploads,
  WhatsApp messages, payment details, and private files;
- fully bilingual where patient-facing text appears;
- mobile-first and accessible.

## Doctor/Admin Workflow Quality

The doctor/admin dashboard should be:

- comfortable for repeated daily use;
- grouped by real clinic workflows;
- validated before saving risky changes;
- reversible where practical;
- auditable for operational and publication-sensitive changes;
- not visually destructive or cluttered;
- clear about draft, preview, and published states;
- safe by default for privacy, publication, and patient data exposure.

## Arabic/English Quality

Arabic and English product text should:

- use clear clinic-appropriate wording;
- avoid mixed-language confusion in the same control unless intentional;
- keep equivalent meaning across languages;
- preserve right-to-left and left-to-right behavior;
- avoid medical claims that need legal or clinical approval;
- avoid diagnosis, triage, treatment automation, or clinical decision support
  wording.

## Mobile-First Quality

Patient-facing pages should be designed and verified mobile-first:

- booking steps must remain usable on small screens;
- tap targets must be comfortable;
- text must not overlap controls or adjacent content;
- forms must show validation clearly;
- public content should remain readable without horizontal scrolling;
- language direction must remain correct in Arabic and English.

Dashboard pages may prioritize desktop efficiency, but they should still have a
usable responsive behavior for reasonable tablet/mobile access.

## Privacy and Security by Default

The final product must preserve:

- UUID-only public booking success URLs;
- staff-only appointment operations;
- CSRF protection on state-changing forms;
- no-cache behavior on confirmation, staff, and patient portal pages;
- patient portal ownership filtering;
- hashed rate-limit identities;
- no raw secrets or connection strings in command output;
- no real patient data in Git, docs, test fixtures, screenshots, logs, or seed
  commands;
- prohibited routes absent until approved future batches.

## Launch Evidence Standard

No public launch is acceptable without evidence for:

- restricted staging validation;
- legal/privacy approval;
- backup and restore drill;
- monitoring and alerting;
- load and concurrency validation;
- dependency/security scan review;
- PostgreSQL and Redis/shared-cache production-like behavior;
- HTTPS/proxy/security-header validation;
- patient identity and account recovery policy;
- staff/admin access review;
- data exposure review.

## Visual Governance

Figma remains the source of truth for visual design. Codex must not invent or
independently change colors, spacing systems, typography systems, visual
hierarchy, animations, decorative elements, brand style, shadows, borders,
radius systems, hover effects, layout density, illustration style, icon style,
image direction, or marketing composition.

The doctor/admin may manage content and approved assets from the dashboard, but
that does not authorize Codex to invent visual redesigns without Figma/design
approval.

## Exclusions Preserved

The current implemented scope still excludes:

- WhatsApp API sending and webhooks;
- uploads and private media handling;
- medical records;
- payments;
- deployment and external infrastructure;
- real patient data;
- diagnosis automation;
- triage automation;
- treatment automation;
- clinical decision support;
- medical AI.
