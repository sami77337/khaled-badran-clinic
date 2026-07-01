# Authorized Cases and Positive Reviews Showcase Requirements

Batch 12 defines the future requirement for an Authorized Cases & Positive
Reviews Showcase. This document is planning only. It does not implement upload,
media storage, publication, public showcase routes, dashboard forms, models,
migrations, templates, CSS, JavaScript, WhatsApp, medical records, or review
imports.

## Purpose

The final product must include a dashboard-managed public showcase section for:

- explicitly approved cases;
- explicitly approved images;
- explicitly approved videos;
- explicitly approved positive reviews.

The showcase may appear on approved public surfaces only after privacy, legal,
design, storage, and publication-consent gates are satisfied.

## Dashboard-Manageable Fields

Future dashboard management must include, at minimum:

- `title_ar`;
- `title_en`;
- `description_ar`;
- `description_en`;
- media type: image, video, or review;
- media file or external approved review reference;
- display location: home page, gallery page, doctor page, or hidden;
- sort order;
- featured flag;
- active/inactive flag;
- autoplay carousel enabled/disabled;
- carousel interval;
- publication consent status;
- consent source;
- consent date;
- consent expiry date if applicable;
- anonymization requirement;
- whether face/identity may be shown;
- internal admin notes.

## Publication Consent Boundary

No patient image, video, medical case, WhatsApp media, uploaded file, report, or
review may be published unless it has explicit publication consent.

Publication consent must be separate from:

- patient account consent;
- WhatsApp consent;
- upload consent;
- appointment consent;
- treatment or visit consent;
- general privacy-policy acknowledgement.

Publication consent must define:

- what may be published;
- where it may be displayed;
- whether identifying details may be shown;
- whether face/identity may be shown;
- whether anonymization is required;
- consent date;
- consent source;
- expiry date if applicable;
- withdrawal/removal process.

Consent must be revocable or removable by an admin workflow.

## Strict Public Exposure Boundaries

The public showcase must not expose:

- internal clinical notes;
- private files;
- raw WhatsApp messages;
- phone numbers;
- full patient names unless explicitly approved for publication;
- medical identifiers;
- internal appointment IDs;
- patient IDs;
- user IDs;
- staff notes;
- audit logs;
- private report files;
- unreviewed upload metadata;
- unapproved images, videos, audio, or documents.

If anonymization is required, the published content must remove or hide all
identifying details before publication.

## Review and Approval Workflow

Future implementation should require:

- staff/admin-only management access;
- draft state before publication;
- preview before publication;
- explicit consent status check before publication;
- inactive/hidden state for content that should not be public;
- removal workflow when consent is revoked or expires;
- audit history for create, edit, publish, unpublish, consent-status changes,
  and deletion/removal actions;
- clear separation between internal admin notes and public descriptions.

## Media and Storage Gates

Before implementing showcase media, the project must define:

- private media storage rules;
- public derivative/storage rules for approved publication assets;
- malware/content-type validation;
- file size and format limits;
- backup and restore behavior;
- deletion/removal behavior after consent withdrawal;
- CDN/static serving policy if used;
- access control for originals and internal files;
- log scrubbing and error-reporting boundaries.

These gates must be handled before uploads or media publication are built.

## Design Gates

Figma/design approval is required before implementing visual placement,
carousel behavior, media cropping, gallery layout, doctor-page placement, home
page placement, hover states, animation, or visual hierarchy.

Autoplay carousel settings must be configurable only after the design and
accessibility behavior are approved.

## Legal and Privacy Gates

Before implementation:

- legal/privacy review must approve publication consent language;
- consent withdrawal/removal process must be approved;
- retention/deletion rules must be approved;
- anonymization rules must be approved;
- patient identity exposure rules must be approved;
- positive review reference/import boundaries must be approved.

## Batch 12 Boundary

Batch 12 does not implement:

- upload/media functionality;
- media publication functionality;
- public showcase UI;
- dashboard showcase UI;
- models or migrations;
- WhatsApp media intake;
- review imports;
- storage providers;
- external infrastructure;
- real patient data.

This document only records the requirement and future implementation gates.
