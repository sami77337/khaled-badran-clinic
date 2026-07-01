# Doctor-Managed Configuration Standard

Batch 12 establishes the standard that routine clinic content and operational
settings should be manageable by the doctor/admin from the dashboard. This is a
planning standard only. It does not add models, migrations, views, templates,
settings, permissions, uploads, WhatsApp, payments, or dashboard code.

## Core Principle

The final product must reduce routine dependency on the programmer. The
doctor/admin should be able to update ordinary clinic-operational settings,
patient-facing copy, and approved public content from the dashboard without a
code change.

This principle does not apply to secrets, infrastructure, security-sensitive
settings, dependencies, or code-level behavior.

## Dashboard-Manageable Areas

At minimum, the dashboard should eventually manage:

- clinic profile;
- doctor profile content;
- services;
- visit types;
- visit durations;
- visit prices and price visibility;
- working days and hours;
- holidays and closed days;
- booking rules;
- reminder timing and message text;
- pre-visit instructions;
- public page content sections;
- gallery images and ordering;
- contact, location, and social links;
- patient-facing copy;
- legal/privacy draft text where safe;
- WhatsApp menu/message templates after privacy gates;
- patient portal explanatory text/settings;
- reports and operational dashboard preferences.

## Not Dashboard-Managed by the Doctor

The doctor/admin dashboard must not manage:

- secrets;
- API credentials;
- deployment settings;
- DNS/TLS;
- database/cache settings;
- security headers;
- dependency versions;
- code-level behavior;
- infrastructure;
- backup provider configuration.

These areas require technical operator control, review, and change management.

## Dashboard Design Principles

Settings must be:

- comfortable to use;
- grouped by workflow and risk level;
- validated before save;
- reversible where practical;
- auditable when they affect operations, public content, pricing, legal text,
  reminders, publication, or patient data exposure;
- not visually destructive;
- protected by safe defaults;
- clear about effective dates where scheduling or policy changes are involved;
- clear about draft, preview, and published state for public-facing content
  where appropriate.

## Draft, Preview, Publish

Public-facing content should support draft, preview, and publish where
appropriate, especially for:

- home page sections;
- doctor profile content;
- services;
- gallery items;
- authorized cases and positive reviews;
- patient-facing explanatory copy;
- legal/privacy draft text when safe for dashboard editing.

Published content must never expose private patient data, internal notes, raw
WhatsApp messages, private files, phone numbers, full patient names, medical
identifiers, audit logs, internal IDs, or staff-only operational data.

## Legal and Privacy Text

Some legal/privacy text may be dashboard-editable as draft operational copy only
if the implementation preserves review workflow and avoids accidental launch of
unreviewed legal claims.

The dashboard should make clear when legal/privacy text is:

- draft;
- pending review;
- approved;
- published;
- superseded.

Legal/privacy approval remains blocked until qualified review is completed.

## WhatsApp Templates

WhatsApp menu/message templates may become dashboard-managed only after privacy
gates are satisfied. Before any WhatsApp implementation:

- consent and opt-out rules must be approved;
- message content boundaries must be approved;
- credential handling must be approved;
- webhook verification must be approved;
- logging boundaries must be approved;
- incident response and token rotation must be approved.

Dashboard-managed WhatsApp text must not become a path for sending diagnoses,
triage decisions, treatment plans, reports, images, or sensitive records through
automated WhatsApp flows.

## Design Governance

The doctor/admin may manage content and approved assets. The doctor/admin
configuration standard does not authorize visual redesign by Codex.

Figma remains the source of truth for:

- colors;
- spacing;
- typography;
- visual hierarchy;
- animation;
- decorative elements;
- brand style;
- shadows;
- borders;
- hover effects;
- layout density;
- image direction and crop rules.

Any future implementation must preserve `docs/FIGMA_DESIGN_HANDOFF.md`.

## Audit and Review Expectations

Future implementation should record audit history for changes to:

- clinic profile;
- doctor profile;
- services and visit types;
- prices and price visibility;
- booking rules;
- working hours and closed days;
- reminder text and timing;
- legal/privacy text;
- public page sections;
- gallery and showcase publication status;
- WhatsApp templates after privacy gates;
- patient portal explanatory text/settings.

Audit records must remain staff/admin-only and must not appear on patient-facing
pages.

## Stop Rules

Stop and report if a proposed dashboard setting would require:

- committing secrets or credentials;
- changing deployment or infrastructure;
- weakening security headers, CSRF, no-cache behavior, or route authorization;
- publishing patient media without explicit publication consent;
- exposing internal notes, patient identifiers, private files, raw WhatsApp
  messages, phone numbers, or medical identifiers;
- bypassing Figma/design approval for visual changes;
- implementing uploads, WhatsApp, records, payments, or external integrations
  without their required gates.
