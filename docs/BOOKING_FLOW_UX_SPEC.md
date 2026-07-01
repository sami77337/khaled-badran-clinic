# Booking Flow UX Specification

This document defines the final smooth booking UX for Dr. Khaled Badran Clinic.
It is specification only. It does not implement code, copy, styling, or
infrastructure.

## Core Booking Principle

Patients must be able to book without creating an account. The booking flow
should feel short, calm, and clear:

1. Choose visit type.
2. Choose available time.
3. Enter contact details and confirm.

## Current Baseline

Implemented:

- public Arabic/default and English booking routes;
- no account required;
- visit type selection;
- generated available slots;
- confirmation form;
- CSRF-protected final POST;
- phone normalization;
- IP and phone rate limits using hashed identities;
- confirmed appointment creation;
- UUID public success page;
- no-cache on confirmation and success;
- optional patient portal linking from success.

Not implemented:

- patient self-service reschedule/cancel;
- reminder sending;
- WhatsApp API/webhook confirmation;
- uploads/records/payments;
- production Redis/PostgreSQL/HTTPS/proxy validation.

## Visit Type Selection

Required final behavior:

- Show active visit types for the active doctor.
- Show patient-safe name, duration, and instructions.
- Show price only when configured as visible to patient.
- Make clear that no appointment is created at this step.
- Provide a clear empty/unavailable state if no active doctor or visit type
  exists.
- Keep the CTA language action-oriented and calm.

Dashboard-managed future fields:

- active/inactive;
- Arabic/English name;
- duration;
- price;
- show/hide price;
- Arabic/English instructions;
- display order.

## Available Slot Selection

Required final behavior:

- Show only available slots derived from schedules, closed days, appointment
  conflicts, visit duration, lead time, max days ahead, and slot interval.
- Group slots by date.
- Revalidate selected time on confirmation.
- Do not create appointments from slot browsing.
- If no slots exist, offer next steps without blaming the patient.

Future UX improvement:

- date filtering or next-available suggestions may be added if approved.

## Name and Phone Entry

Required final fields:

- full name;
- phone number;
- optional WhatsApp/contact phone only when wording makes clear whether it is
  actually used;
- optional booking note only if it remains staff/internal after submission.

Phone expectations:

- accept local mobile format according to current normalization rules;
- accept plausible international format starting with `+`;
- normalize server-side;
- show friendly validation;
- avoid exposing raw normalized values where not needed.

The booking note must not appear on public success or patient portal pages.

## Confirmation Step

Required final behavior:

- Show selected visit type and time before submit.
- Explain that the confirmed appointment is created only after submitting.
- Keep emergency warning short and appropriate.
- Prevent duplicate/stale slot creation through server validation.
- Use clear non-field errors for stale/unavailable slot and rate-limit cases.
- Preserve CSRF protection.

## UUID/Token Public Success Behavior

Required final behavior:

- Success URL uses UUID public token.
- Numeric public success URLs remain absent.
- Page is no-cache.
- Page shows patient-safe confirmation details only.
- Short confirmation reference is shown instead of database ID.
- Full public token should not be shown as ordinary text except where it is
  explicitly needed for portal linking.
- Portal-link query token must not appear on portal dashboard/account pages.

Allowed success fields:

- confirmation reference;
- patient name;
- doctor display name;
- visit type;
- date/time;
- safe next steps.

Forbidden success fields:

- internal IDs;
- staff notes;
- booking private note;
- audit/status history;
- records/uploads/private files;
- WhatsApp messages;
- payment admin details.

## Optional Patient Portal Follow-Up

The success page may invite the patient to link the appointment in the optional
portal. Copy must state:

- portal linking is optional;
- booking remains confirmed without an account;
- linking requires confirmation token and booking phone;
- portal currently shows safe appointment information only.

## Reminder Expectations

Current model/settings support reminder offset and per-appointment reminder
fields, but no sending provider is implemented.

Future reminders require:

- dashboard-managed reminder timing;
- approved Arabic/English message text;
- consent/channel rules;
- logging boundaries;
- provider approval;
- failure/retry policy;
- opt-out where applicable;
- privacy/legal review.

Until then, UI copy must not promise automated reminders.

## Failure and Error States

Final booking UX must cover:

- booking disabled;
- no active doctor;
- no active visit type;
- no available slots;
- invalid/stale slot;
- duplicate/concurrent slot conflict;
- invalid phone;
- missing name/phone;
- rate limit by IP;
- rate limit by phone;
- server-side validation failure;
- expired/back-button scenario.

Errors should:

- be visible near the form or affected field;
- avoid leaking internal details;
- provide a next step;
- stay bilingual;
- avoid frightening medical/legal language unless emergency warning is needed.

## Reschedule and Cancel Rules

Current implementation:

- staff can reschedule confirmed/rescheduled appointments;
- staff can cancel confirmed/arrived/rescheduled appointments;
- staff can mark arrived, complete, and no-show within bounded status rules;
- public token is preserved on reschedule;
- terminal restore is intentionally not available.

Future patient self-service reschedule/cancel is gated by:

- verified identity;
- abuse controls;
- policy for allowed time window;
- audit history;
- patient notification copy;
- staff visibility;
- rate limits;
- legal/privacy review.

Do not implement patient self-service changes until those gates are approved.

## Staff Visibility

Staff dashboard/list/detail may show:

- internal appointment ID;
- patient name;
- phone;
- visit type;
- doctor;
- status;
- booking note;
- status history;
- audit events;
- public token if needed for operational support.

Staff-only data must not leak to public success or portal pages.

## Comfort Requirements

- Minimal steps: visit, time, contact.
- No account wall before booking.
- Plain language.
- Clear Arabic/English equivalents.
- No scary medical/legal wording in normal booking.
- Emergency warning only where needed and phrased calmly.
- Clear distinction between confirmed booking and optional portal.
- No false promise of WhatsApp or reminders before implementation.
- Mobile form fields and slot buttons must be comfortable to tap.
- Back/refresh/stale slot behavior must be understandable.

## Design Handoff Requirements

Before visual changes to booking, the human/Figma handoff must cover:

- step indicator behavior;
- visit type card/list states;
- slot/date grouping and empty states;
- confirmation form fields and validation states;
- success page states;
- Arabic and English copy length;
- mobile and desktop layout;
- loading and disabled states if added;
- focus behavior;
- no-cache/privacy cues;
- interaction rules for optional portal linking.
