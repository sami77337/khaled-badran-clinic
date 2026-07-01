# Patient Portal UX Specification

This document defines the final patient portal UX target while preserving the
current bounded privacy/security model. It is specification only.

## Current Baseline

Implemented:

- optional registration;
- phone/password login;
- POST-only logout;
- account summary;
- password change;
- clinic-assisted recovery policy page;
- appointment linking by UUID token plus booking phone;
- linked appointment list and detail;
- no-cache portal pages;
- CSRF on state-changing forms;
- rate limits with hashed identities;
- patient ownership filtering.

Not implemented:

- verified phone/email ownership;
- self-service password reset;
- contact editing;
- uploads;
- medical records;
- deletion request workflow;
- WhatsApp message visibility;
- payments.

## Portal Role

The portal is optional. It must not block public booking. It should provide a
safe way to view linked appointment information and manage basic account
security.

## Registration

Required final behavior:

- collect full name, phone, optional email, password, and password confirmation;
- normalize phone server-side;
- use Django password hashing/validation;
- use generic duplicate/failed registration errors;
- rate limit by safe hashed identities;
- log in the user after successful registration if safe;
- clearly state that booking does not require an account.

Future gates:

- verified phone/email ownership;
- stronger abuse monitoring;
- identity verification policy.

## Login and Logout

Login:

- phone/password;
- generic failure copy;
- rate limited;
- CSRF-protected POST;
- safe `next` URL handling;
- no account existence disclosure.

Logout:

- POST-only;
- CSRF-protected;
- redirects to login;
- no GET logout.

## Account Summary

Allowed fields:

- display name;
- masked username/phone;
- optional email;
- linked appointment count.

Not allowed:

- user ID;
- patient ID;
- appointment IDs;
- raw appointment tokens;
- staff notes;
- audit logs;
- booking notes;
- medical records;
- uploads;
- payment details.

Future contact editing requires verified ownership policy.

## Appointment Linking

Required behavior:

- login required;
- appointment UUID token required;
- booking phone required;
- phone must match the appointment patient's normalized phone;
- generic error for wrong token, wrong phone, nonexistent token, or stolen
  linked patient attempt;
- already linked to same user is a safe no-op;
- existing patient linked to another user cannot be stolen;
- rate limited;
- no raw public tokens in cache keys.

Comfort requirement:

- explain that the token comes from booking confirmation;
- explain that the phone must be the booking phone;
- avoid implying medical records will appear after linking.

## Appointment List and Detail

List should show:

- date/time;
- visit type;
- doctor;
- patient-safe status;
- link to detail.

Detail should show:

- visit type;
- date/time;
- patient-safe status;
- doctor;
- clinic name/address;
- created date.

Not allowed:

- internal IDs;
- staff operation links;
- booking note;
- staff notes;
- status history notes;
- audit metadata;
- raw public token text;
- records/uploads/WhatsApp/payment data.

## Password Change

Required behavior:

- login required;
- current password;
- new password;
- confirm new password;
- Django password validation;
- hashed storage;
- session hash refresh after success;
- no-cache;
- CSRF protection;
- sensitive POST parameters.

Password copy should be calm and security-focused, not technical.

## Recovery Policy Boundary

Current recovery is informational and clinic-assisted.

The page must not:

- collect phone/email;
- send email;
- send WhatsApp;
- create support tickets;
- disclose whether an account exists.

Future recovery requires:

- verified contact ownership;
- identity verification;
- staff procedure;
- abuse controls;
- patient privacy checks;
- failure/escalation paths;
- legal/privacy approval.

## Future Upload/Media/Records Gates

Before any patient upload, private media, or records feature:

- private storage design;
- authorization rules;
- malware/content-type validation;
- retention/deletion policy;
- backup/restore coverage;
- patient-visible data boundaries;
- audit policy;
- legal/privacy review;
- staging validation.

Until then, portal copy should clearly say uploads and records are not
available.

## Deletion Request Future Behavior

Self-service deletion is not implemented.

Future deletion request workflow needs:

- intake channel;
- identity verification;
- retention/legal hold rules;
- what can be deleted, restricted, retained, or anonymized;
- staff review;
- audit retention rules;
- backup retention rules.

Do not implement automated deletion of clinical or operational records without
legal/privacy approval.

## Privacy Boundaries

Portal must preserve:

- login required for dashboard/list/detail/account/password pages;
- UUID token plus ownership filtering for appointment detail;
- no-cache pages;
- generic errors for sensitive linking/login cases;
- no raw public token on dashboard/account;
- no staff-only data on patient pages.

## Arabic/English Requirements

- Arabic/default and English routes must remain equivalent.
- Status labels must be patient-safe in both languages.
- Password validation help text needs bilingual review.
- Errors and empty states must avoid account enumeration.

## Design Handoff Requirements

Before portal visual changes, human/Figma handoff must cover:

- registration/login states;
- account summary states;
- appointment linking states;
- appointment list/detail states;
- password change states;
- recovery policy page;
- empty linked-appointment state;
- Arabic/English text length;
- mobile table/list behavior;
- focus/error/success/no-cache privacy cues.
