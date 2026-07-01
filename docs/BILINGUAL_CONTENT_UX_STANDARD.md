# Bilingual Content UX Standard

This document defines Arabic/English content rules for Dr. Khaled Badran
Clinic. It is a content standard only. It does not rewrite templates or create
visual design.

## Core Rules

- Arabic is the default product language.
- English is a professional, concise parallel experience.
- Arabic and English must preserve meaning, not literal word order.
- Avoid weak literal translation.
- Avoid mixed-language controls unless the mixed term is an approved brand,
  doctor name, or unavoidable technical term.
- Do not overclaim medical outcomes, legal approval, staging readiness, or
  production launch.
- Do not use real patient data in examples, docs, screenshots, or tests.

## Content Freshness Rule

Patient-facing and legal copy must match current product behavior.

Current known issue:

- Some public/legal copy still says booking and/or portal features are not
  available in the current batch, while current code implements public booking
  and a bounded optional portal. A future content/legal implementation batch
  must correct this before launch.

## CTA Language

Primary patient CTA:

- Use a direct booking action.
- Do not send patients to account registration before booking.
- Avoid vague labels such as "start" when the action creates a booking path.

Secondary CTAs:

- Doctor profile.
- Services.
- Contact details.
- Patient portal only as optional follow-up.

Disabled/unavailable CTA:

- Explain that booking is currently unavailable and provide contact details.
- Do not imply a system failure if booking was intentionally disabled.

## Medical Disclaimer Language

Required meaning:

- The site is informational and operational.
- It is not for emergencies.
- It does not provide diagnosis.
- It does not provide triage.
- It does not provide treatment automation.
- It does not replace medical consultation.

Tone:

- Clear and calm.
- Present emergency warning where needed.
- Do not repeat emergency text so heavily that normal flows feel unsafe.

## Booking Microcopy

Required booking meaning:

- No account is required.
- No appointment is created until final confirmation.
- Selected time is rechecked at confirmation.
- Phone number is needed for clinic contact.
- Optional WhatsApp/contact number must not imply automated WhatsApp sending
  until implemented and approved.
- Booking note is optional and staff/internal after submission.
- Success means the appointment was created.
- Portal linking is optional.

Avoid:

- "maybe", "request" or "pending" wording if current behavior creates a
  confirmed appointment.
- scary legal warnings during normal booking;
- medical advice;
- diagnosis/triage language.

## Dashboard Labels

Dashboard labels should be:

- short;
- operational;
- consistent;
- status-aware;
- clear about public versus staff-only data.

Examples of safe English labels:

- Today.
- Upcoming appointments.
- Appointment details.
- Mark arrived.
- Reschedule.
- Cancel appointment.
- No-show.
- Public content.
- Draft.
- Pending review.
- Approved.
- Published.
- Superseded.

Arabic equivalents must be natural Arabic, not literal word-for-word copies.

## Legal/Privacy Copy Status Labels

Use explicit status labels for dashboard-managed legal/privacy text:

- Draft.
- Pending review.
- Approved.
- Published.
- Superseded.
- Blocked.

Public pages must not claim legal/privacy approval until qualified review is
complete.

## Error Messages

Errors should:

- say what happened;
- say what the patient/admin can do next;
- avoid internal details;
- avoid account enumeration;
- avoid raw tokens, IDs, secrets, or database terms;
- be bilingual.

Safe generic examples:

- "We could not sign you in with those details."
- "We could not link an appointment with those details."
- "This appointment time is no longer available."
- "Too many attempts. Please wait before trying again."

Arabic equivalents must be professionally written and reviewed.

## Empty States

Empty states should:

- explain the state;
- provide a next action;
- avoid blame.

Examples:

- No available times: change visit type or contact the clinic.
- No linked appointments: link an appointment using the confirmation details.
- No upcoming appointments: book an appointment or review linked appointments.
- No showcase items: hide the section or show an approved generic state only.

## Success Messages

Success messages should:

- confirm the user action;
- avoid exposing internal details;
- provide a useful next step.

Examples:

- Appointment confirmed.
- Appointment linked to your portal.
- Password changed.
- Public content saved as draft.
- Showcase item unpublished.

## Privacy-Sensitive Copy

Do not write copy that asks patients to submit:

- reports;
- photos;
- diagnoses;
- detailed symptoms;
- medical records;
- WhatsApp messages;
- payment details;
- identity documents;
- private media;

unless a future approved workflow exists for that data type.

## Translation Review Checklist

- Does Arabic sound native and clinic-appropriate?
- Does English sound concise and professional?
- Are CTA meanings identical across languages?
- Are medical/legal claims consistent?
- Are error messages safe and non-enumerating?
- Are status labels consistent across public, portal, and dashboard?
- Does text fit on mobile in both languages?
- Does the copy reflect implemented behavior today?
