# Doctor Dashboard UX Specification

This document defines the final doctor/admin dashboard UX target. It is
specification only and does not implement a dashboard or visual design.

## Current Baseline

Implemented today:

- staff-only appointment list;
- staff-only appointment detail;
- staff cancel, reschedule, arrived, complete, and no-show operations;
- status history and audit events;
- Django admin registrations for clinic profile, doctor, visit types,
  schedules, closed days, appointments, patients, system settings, and audit
  logs.

Not implemented today:

- broad custom doctor/admin dashboard;
- today overview;
- dashboard-managed public content workflow;
- dashboard-managed legal/privacy review workflow;
- authorized showcase management;
- reports;
- operational alert dashboard;
- comfortable settings workflow.

## Dashboard Goals

The final dashboard must be:

- comfortable for daily repeated clinic work;
- grouped by real workflows;
- validated before risky saves;
- auditable for operational and publication-sensitive changes;
- reversible where practical through reviewed correction flows;
- privacy-safe by default;
- clear about draft, preview, published, pending, and blocked states;
- efficient on desktop and usable on tablet/mobile.

## Access Expectations

- Dashboard access requires authenticated active staff/admin.
- Role boundaries should distinguish doctor/admin, staff operator, and
  technical operator where needed.
- Anonymous users redirect to login.
- Authenticated non-staff users receive denial.
- State-changing operations remain CSRF-protected.
- Sensitive dashboard pages should be no-cache.
- Staff access review and offboarding remain pre-launch requirements.

## Today Overview

The dashboard landing page should show:

- today appointment count;
- next appointment;
- arrived/waiting appointments;
- confirmed upcoming appointments;
- rescheduled appointments;
- cancelled/no-show indicators;
- overdue operational items;
- booking availability status;
- operational alerts;
- legal/privacy/review blockers if launch-relevant.

It should not show raw logs, secrets, connection strings, or patient data beyond
what staff are authorized to see.

## Upcoming Appointments

Required capabilities:

- filter by status, date/range, doctor, visit type, patient name/phone;
- sort by time;
- quick links to appointment detail;
- clear patient-safe status labels where staff needs patient-facing wording;
- pagination or efficient loading for larger lists;
- no public/staff URL leakage to patient pages.

Future improvements:

- calendar/day view;
- next available slot helper;
- staff assignment if roles expand.

## Appointment Detail

The detail screen should group:

- appointment summary;
- patient/contact summary;
- visit type and schedule;
- operational status;
- patient-visible versus staff-only data reminder;
- action area;
- status history;
- audit history.

Actions:

- mark arrived;
- mark completed;
- reschedule;
- cancel;
- mark no-show.

Final UX requirements:

- only valid actions appear for the current status;
- destructive/terminal actions require clear notes where policy requires;
- reschedule should use validated available slots where practical, not only a
  raw datetime input;
- action results should show clear success/error messages;
- terminal correction/restore requires a reviewed workflow before enabling.

## Patient Profile Entry Point

The dashboard should provide a staff-only patient profile entry from
appointment detail/search.

Patient profile may show:

- patient name;
- phone/contact fields;
- linked portal account status;
- appointment history;
- safe operational notes if approved;
- identity verification flags after policy exists.

Patient profile must not become a medical-record surface until records are
separately designed and approved.

## Dashboard-Managed Configuration

Configuration sections should be grouped by risk:

- Clinic public profile.
- Doctor profile.
- Services and visit types.
- Booking rules.
- Schedule and closed days.
- Reminders.
- Public content.
- Authorized showcase.
- Legal/privacy drafts and review statuses.
- Dashboard preferences/reports.

Each section should provide:

- clear labels;
- validation;
- preview where public-facing;
- effective date where relevant;
- audit trail;
- safe defaults;
- confirmation for risky changes.

## Visit Types, Prices, and Durations

Dashboard must manage:

- Arabic/English visit type name;
- duration;
- price;
- whether price is visible to patients;
- Arabic/English instructions;
- active/inactive;
- display order;
- doctor association.

Validation:

- duration must be positive;
- price cannot be negative;
- inactive visit types must not be bookable;
- changes should not silently invalidate existing appointments.

## Working Hours and Closed Days

Dashboard must manage:

- working weekdays;
- start/end times;
- active/inactive schedules;
- doctor-specific closed days;
- clinic-wide closed days;
- bilingual reason for closed day where public-facing.

Validation:

- end time after start time;
- closed day removes public availability;
- schedule changes should warn if they affect existing bookings.

## Reminders

Dashboard may manage reminders only after provider/privacy gates:

- reminder enabled/default status;
- timing offset;
- approved Arabic/English message text;
- channel;
- consent/opt-out status;
- failure handling.

Until sending is implemented and approved, dashboard copy must not promise
actual sent reminders.

## Public Content

Dashboard-managed public content should support:

- clinic name and contact;
- doctor profile;
- services;
- home page sections;
- contact/location;
- gallery;
- patient-facing booking/portal copy;
- draft/preview/publish states;
- audit history.

Public content must never expose private patient data.

## Authorized Showcase Management

Dashboard must provide:

- draft item creation;
- bilingual title/description;
- media/review type;
- display location;
- sort order/featured/active;
- consent status/source/date/expiry;
- anonymization and identity visibility controls;
- internal admin notes separated from public copy;
- preview;
- publish/unpublish/remove;
- audit history.

Publication must be blocked unless explicit publication consent and legal/privacy
gates are satisfied.

## Reports

Reports may include:

- appointment counts by date/status/visit type;
- no-show/cancellation trends;
- booking volume;
- public booking availability health;
- portal linking counts;
- safe operational counts.

Reports must not export raw patient data unless a future approved export policy
exists.

## Operational Alerts

Dashboard alerts may include:

- booking disabled;
- no active doctor;
- no active visit types;
- no active schedules;
- upcoming closed days;
- staging/production validation missing;
- legal/privacy approval blocked;
- backup/restore drill missing;
- monitoring/alerting missing;
- dependency/security review missing.

Operational alerts must not expose secrets or raw provider details.

## Privacy/Legal Review Statuses

Dashboard should eventually show:

- privacy policy draft/pending/approved/published/superseded;
- terms draft/pending/approved/published/superseded;
- medical disclaimer draft/pending/approved/published/superseded;
- WhatsApp policy draft/pending/approved/published/superseded;
- publication consent review status;
- account recovery policy status;
- identity verification policy status.

Legal approval must not be self-certified by code.

## Staff/Admin Access Expectations

Required:

- least privilege;
- named accounts;
- no shared production admin accounts;
- periodic access review;
- offboarding process;
- audit visibility for sensitive changes.

Future roles need explicit permission mapping before implementation.

## Design Handoff Requirements

Before visual dashboard implementation or redesign, human/Figma handoff must
cover:

- dashboard navigation;
- today overview information hierarchy;
- appointment list and table behavior;
- appointment detail grouping;
- action states and confirmations;
- configuration section structure;
- draft/preview/publish states;
- alert severity treatment;
- Arabic/English dashboard label behavior if bilingual;
- mobile/tablet fallback;
- focus, keyboard, empty, error, disabled, loading, and success states.

No visual design should be inferred from this specification.
