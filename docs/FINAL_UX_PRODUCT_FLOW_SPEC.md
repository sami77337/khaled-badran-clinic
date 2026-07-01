# Final UX Product Flow Specification

Batch 13 defines the final product UX and product-flow target for Dr. Khaled
Badran Clinic. This document is implementation-grade product specification, not
application code and not visual design. It also defines what a human/owner
approved Figma or design handoff must cover before any future visual work.

## Non-Negotiable Product Principles

- Arabic is the default patient experience. English is a professional parallel
  experience.
- Public booking must not require an account before booking.
- Patient-facing flows must be mobile-first, calm, and low friction.
- Doctor/admin workflows must be comfortable for repeated daily use, grouped by
  real clinic operations, and not feel like a temporary demo.
- Routine clinic content and safe operational settings should be
  dashboard-managed wherever practical.
- Privacy and security boundaries from `docs/ROUTE_ACCESS_MATRIX.md` and
  `docs/DATA_EXPOSURE_MATRIX.md` must remain intact.
- Public success URLs remain UUID/token based and no-cache.
- Staff numeric appointment IDs remain behind staff-only authorization.
- Patient portal appointment details require authentication and ownership
  filtering.
- Visual design, layout density, colors, spacing, typography, animation,
  shadows, borders, hover behavior, imagery direction, and composition require
  approved human/Figma design handoff before implementation.

## Patient Journey: First Visit to Booking

### Entry Points

Patients may enter from:

- home page booking CTA;
- doctor page booking CTA;
- services page visit type/service CTAs;
- contact page booking CTA;
- search result or direct booking URL;
- future approved WhatsApp menu link;
- future approved authorized showcase CTA.

### Required Flow

1. Patient lands on a public Arabic/default or English page.
2. Patient sees the clinic identity, doctor identity, and primary booking CTA
   without needing to understand internal system state.
3. Patient can review doctor profile, services, contact/location, and legal
   links without account creation.
4. Patient starts booking.
5. Patient chooses visit type.
6. Patient chooses an available date/time slot.
7. Patient enters full name and phone number. WhatsApp phone may be collected
   only as contact preference until WhatsApp is approved.
8. Patient confirms the appointment.
9. System creates a confirmed appointment and redirects to UUID public success.

### Required Comfort Behaviors

- The flow should feel like three clear decisions: visit type, time, contact.
- Copy should say that the appointment is only created after final confirmation.
- The patient must never be asked to register before booking.
- Emergency warning must be present where needed but not dominate normal
  booking.
- Validation errors should be clear, visible, and non-accusatory.
- Empty slot states should offer a calm next step: change visit type, choose
  another date if available, or contact the clinic.

## Patient Journey: After Booking

### Success State

The success page must show only:

- short confirmation reference;
- patient name;
- doctor display name;
- visit type;
- appointment date/time;
- safe instructions approved for public display;
- optional portal linking action;
- book another appointment action;
- return home/contact action.

The success page must not show:

- internal appointment ID;
- patient ID;
- user ID;
- staff notes;
- booking private notes;
- audit logs;
- status history notes;
- medical records;
- uploads/private media;
- WhatsApp messages;
- payment administration details.

### Follow-Up Options

After booking, the patient may:

- save the confirmation reference;
- contact the clinic using public contact details;
- create/sign in to the optional portal;
- link the appointment using confirmation token plus booking phone;
- book another appointment.

Future approved additions may include:

- reminders through approved channels;
- calendar download;
- patient self-service reschedule/cancel after identity, abuse, and policy
  gates;
- WhatsApp confirmation after consent and provider gates.

## Optional Patient Portal Journey

### Current and Final Role

The portal is optional. It should help patients see linked appointment
information, not replace public booking and not become a medical-record portal
until future privacy/legal gates are complete.

### Required Flow

1. Patient reaches portal from public nav, success page, or direct URL.
2. Patient can register or log in with phone/password.
3. Patient can link an appointment using confirmation token plus booking phone.
4. Patient can view dashboard, linked appointment list, appointment detail,
   account summary, and password change.
5. Patient can log out with POST-only logout.
6. Account recovery remains clinic-assisted until an approved secure recovery
   policy is implemented.

### Patient-Visible Appointment Data

Allowed:

- visit type;
- appointment date/time;
- patient-safe status label;
- doctor display name;
- clinic name/address;
- created date.

Not allowed:

- internal IDs;
- raw public token on dashboard/account pages;
- staff notes;
- booking notes;
- status history notes;
- audit logs;
- medical records;
- uploads;
- WhatsApp messages;
- payment admin details.

## Doctor/Admin Daily Workflow

### Final Dashboard Entry

The final dashboard should open to a practical daily overview, not a marketing
screen.

Required first-level modules:

- Today overview.
- Upcoming appointments.
- Appointment search.
- Appointment detail.
- Patient profile entry point.
- Clinic configuration.
- Public content.
- Authorized showcase management.
- Reports.
- Alerts/review queue.
- Legal/privacy review statuses.

### Today Overview

The doctor/admin should see:

- today appointment count by status;
- next appointment;
- arrived/waiting appointments;
- overdue/no-show candidates;
- cancelled/rescheduled indicators;
- operational alerts;
- quick link to booking availability.

### Appointment Detail

Appointment detail should group:

- patient/contact block;
- appointment block;
- status/action block;
- schedule/reschedule block;
- internal note/audit block;
- patient-safe visibility reminder.

Actions must be:

- validated;
- CSRF-protected;
- audited;
- restricted to staff/admin;
- reversible only through a reviewed correction workflow where practical.

## Dashboard-Managed Configuration Journey

### Manageable Areas

The doctor/admin dashboard should eventually manage:

- clinic profile;
- doctor profile;
- public services;
- visit types;
- durations;
- prices and price visibility;
- working days/hours;
- holidays/closed days;
- booking enabled/disabled state;
- booking lead time, max days ahead, slot interval;
- reminder timing and approved message text;
- public page content;
- gallery items;
- contact/location/social links;
- patient-facing explanatory copy;
- legal/privacy drafts and review statuses where safe;
- authorized showcase entries;
- dashboard reports/preferences.

### Required Configuration Flow

1. Admin opens a grouped configuration section.
2. Admin edits fields with clear labels and validation.
3. System previews public-facing content where appropriate.
4. Risky changes require confirmation or review state.
5. Save writes audit history.
6. Public content uses draft/preview/publish where appropriate.
7. Legal/privacy content uses draft, pending review, approved, published, and
   superseded statuses.

### Not Dashboard-Managed

The dashboard must not manage:

- secrets;
- API credentials;
- database/cache URLs;
- DNS/TLS;
- deployment settings;
- dependency versions;
- security headers;
- infrastructure;
- backup provider configuration.

## Authorized Cases and Reviews Showcase Journey

### Final Product Goal

The public site should eventually show approved cases, approved images/videos,
and positive reviews only after all publication-consent gates are complete.

### Required Staff/Admin Flow

1. Staff/admin creates a draft showcase item.
2. Staff/admin enters bilingual title and description.
3. Staff/admin selects media/review type and intended display location.
4. Staff/admin records publication consent status, source, date, expiry if any,
   anonymization requirements, and identity/face visibility permission.
5. Staff/admin previews the item.
6. System blocks publication unless consent status and legal/privacy gates are
   satisfied.
7. Publish/unpublish/removal actions are audited.
8. Revoked or expired consent triggers removal workflow.

### Public Flow

The public showcase must never expose unapproved patient identity, private
files, internal notes, raw WhatsApp messages, reports, identifiers, audit logs,
or staff-only data.

## Future WhatsApp Journey After Privacy Gates

WhatsApp must stay absent until a future approved batch defines and implements:

- consent;
- opt-out;
- provider;
- credential handling;
- webhook verification;
- logging boundaries;
- message content boundaries;
- abuse/cost controls;
- incident response;
- token rotation;
- legal/privacy approval.

Future WhatsApp may support:

- menu link to booking;
- administrative confirmation;
- reminders;
- patient inquiries within approved boundaries.

Future WhatsApp must not automate diagnosis, triage, treatment plans, reports,
images, sensitive records, or medical AI.

## Safe Operational/Admin Workflows

Operational workflows should include:

- safe smoke/readiness summaries;
- staging validation results;
- backup/restore drill status;
- monitoring/alert status;
- legal/privacy review status;
- staff access review status;
- dependency/security review status.

These workflows may be shown in dashboard summaries only if they avoid secrets,
connection strings, raw logs, patient identifiers, and raw tokens.

## Design Handoff Requirements

This document does not design visuals. Before implementation of visual changes,
a human/owner-approved Figma or design handoff must cover:

- page/screen inventory;
- desktop, tablet, and mobile behavior;
- Arabic RTL and English LTR behavior;
- component states;
- navigation states;
- form field, error, loading, empty, success, disabled, and focus states;
- appointment status states;
- dashboard information grouping;
- patient portal states;
- public booking states;
- legal/privacy review status states;
- authorized showcase states;
- responsive overflow rules;
- accessibility requirements;
- content length and wrapping rules;
- approved assets and crop rules;
- approved icon set if any;
- exact rules for what must not change.

Figma or human design approval cannot override route, CSRF, no-cache,
ownership, data exposure, staging, legal/privacy, or consent gates.

## Final Acceptance Criteria

The final product UX is acceptable only when:

- public booking is smooth and login-free;
- booking success is UUID/no-cache and patient-safe;
- public/legal copy accurately reflects implemented features;
- patient portal is optional, safe, and ownership-filtered;
- doctor/admin dashboard supports daily operations comfortably;
- dashboard-managed configuration covers routine safe settings/content;
- Arabic and English copy are reviewed and not literal weak translations;
- mobile flows are verified on real viewports;
- accessibility checklist is reviewed;
- staging validation passes with production-like infrastructure;
- legal/privacy review is complete before public launch;
- no prohibited feature is enabled without its required future gates.
