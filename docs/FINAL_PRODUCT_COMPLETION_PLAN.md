# Final Product Completion Plan

Batch 12 establishes the final product completion planning track for Dr. Khaled
Badran Clinic. This document is planning alignment only. It does not implement
application code, models, migrations, templates, CSS, JavaScript, settings,
dependencies, CI, Docker, deployment, secrets, external infrastructure, uploads,
WhatsApp, medical records, payments, or visual design changes.

## Owner Decisions

- DEMO_TRACK is no longer the project priority.
- The project must continue toward a highly professional, smooth, comfortable,
  secure, production-ready clinic system.
- Almost all routine clinic content and operational settings must be manageable
  by the doctor/admin from the dashboard.
- The final product must include an Authorized Cases & Positive Reviews
  Showcase for explicitly approved cases, images, videos, and positive reviews.
- Synthetic demo data and seed commands may remain only for local
  validation/testing. They are not the delivery goal.

## Current Factual Baseline

- Batch 11 completed repository-local restricted staging validation operations.
- Batch 11 reported 246 tests passing.
- The project is not production launched.
- Real staging infrastructure has not yet been validated.
- Legal/privacy approval remains blocked.
- WhatsApp, uploads, medical records, and payments remain outside the current
  implemented scope.
- No diagnosis, triage, treatment automation, clinical decision support, or
  medical AI is implemented or authorized.

## Product Completion Direction

The final product should be a professional clinic system, not a temporary demo.
The target experience is:

- patient-friendly public information and booking;
- smooth bilingual Arabic/English flows;
- mobile-first behavior;
- a comfortable and efficient doctor/admin dashboard;
- dashboard-managed clinic operations and public content;
- conservative privacy and security defaults;
- clear consent boundaries for publication, WhatsApp, portal features, and any
  future private media;
- restricted staging and release evidence before launch.

## Required Completion Standards

Before public launch, the project must have evidence for:

- final Figma/design approval where visual changes are involved;
- restricted staging validation with production-like settings;
- PostgreSQL validation for migrations and booking concurrency;
- Redis/shared-cache validation for rate limits across processes;
- HTTPS, reverse proxy, secure cookie, CSRF origin, and HSTS behavior;
- backup and restore drill with synthetic data;
- monitoring, alerting, safe error reporting, and abuse signals;
- dependency/security scanning and owner response process;
- legal/privacy review;
- account recovery and patient identity verification policy;
- staff/admin least-privilege review;
- load and concurrency testing;
- data exposure review for all patient-facing surfaces.

No real production launch is permitted until these items are complete and
reviewed.

## Dashboard-Managed Completion Principle

The final product must minimize routine programmer dependency. The doctor/admin
should be able to manage ordinary clinic-operational settings and approved
public content from the dashboard, with validation, auditability, safe defaults,
and reversible changes.

The detailed standard is defined in
`docs/DOCTOR_MANAGED_CONFIGURATION_STANDARD.md`.

## Authorized Showcase Principle

The final product must support a dashboard-managed public showcase for approved
cases, approved images/videos, and positive reviews, but only with explicit
publication consent. Publication consent is separate from appointment consent,
patient account consent, upload consent, and WhatsApp consent.

The detailed requirement is defined in
`docs/AUTHORIZED_SHOWCASE_REQUIREMENTS.md`.

## Synthetic Data Policy

Allowed only for local validation/testing:

- synthetic public clinic content;
- synthetic visit types and schedules;
- synthetic staff/admin test accounts;
- synthetic patients and appointments only where test isolation requires them;
- seed commands that do not create real patient data.

Not allowed in Git, docs, screenshots, logs, tests, staging demos, or PRs:

- real patient names;
- real phone numbers;
- real emails;
- real appointment histories;
- medical notes;
- diagnoses;
- reports;
- patient images, videos, audio, or private media;
- WhatsApp messages;
- payment data;
- credentials, secrets, tokens, database dumps, or private logs.

## Recommended Batch Order

1. Batch 13: Figma/UX final handoff or final design specification alignment.
2. Batch 14: restricted staging validation with PostgreSQL/Redis/HTTPS/proxy.
3. Batch 15: backup/restore synthetic drill evidence and
   monitoring/alerting setup plan.
4. Batch 16: legal/privacy/account recovery and patient identity verification
   policy.
5. Batch 17: doctor dashboard workflow completion/polish.
6. Batch 18: patient portal completion/hardening.
7. Batch 19: WhatsApp limited integration design/implementation only after
   privacy gates.
8. Batch 20: approved cases/reviews/media showcase plus private publication
   rules.
9. Batch 21: release candidate hardening.

## Stop Rules

Stop and report if:

- any code change seems needed during a planning-only batch;
- visual changes are requested without Figma/design approval;
- implementation tries to skip staging, legal, privacy, backup, monitoring,
  load, or security gates;
- real patient data is requested, supplied, committed, logged, or seeded;
- patient media or reviews are requested for publication without explicit
  publication consent;
- WhatsApp, uploads, medical records, payments, deployment, secrets, external
  infrastructure, dependency, CI, Docker, settings, model, migration, template,
  CSS, or JavaScript work is pulled into a documentation-only batch.
