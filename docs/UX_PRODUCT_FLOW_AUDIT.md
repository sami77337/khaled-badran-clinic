# UX Product Flow Audit

Batch 13 audits the current product flows for Dr. Khaled Badran Clinic and
records factual UX/product findings for later implementation planning. This is
documentation only. It does not create Figma work, visual design, templates,
CSS, JavaScript, models, migrations, settings, dependencies, deployment, or
external infrastructure.

## Sources Inspected

- Required project, release, staging, legal/privacy, route, data exposure,
  quality, and Batch 8 through Batch 12 documents.
- `config/urls.py`.
- Current app views, forms, models, admin registrations, services, rate-limit
  helpers, selectors, and audit helpers for public site, booking, staff
  operations, patient portal, and operational commands.
- Public, booking, staff, patient portal, legal, and shared templates.
- `static/css/site.css`.
- Relevant tests in `apps/core/tests.py`, `apps/clinic/tests.py`,
  `apps/booking/tests.py`, and `apps/patients/tests.py`.

If a finding below says `needs verification`, the repository did not provide
enough evidence to state it as fact.

## Summary Findings

- The current implementation is a bounded clinic system foundation with public
  bilingual pages, login-free booking, UUID public success URLs, staff-only
  appointment operations, optional patient portal foundation, safe operational
  commands, and strong route/privacy documentation.
- The implemented booking flow is real: valid public final confirmation creates
  a patient and confirmed appointment. Several public and legal content areas
  still contain stale wording from earlier batches that says booking or portal
  features are not available. That is a UX and legal/content review gap.
- The current doctor/admin product surface is not yet a broad comfortable
  dashboard. Staff appointment list/detail operations exist, and Django admin
  registrations exist for clinic profile, doctor, visit types, schedules,
  closed days, system settings, patients, appointments, and audit logs.
- The patient portal is intentionally optional and bounded to account access,
  password change, account summary, clinic-assisted recovery information,
  appointment linking, and linked appointment viewing.
- Uploads, medical records, WhatsApp API/webhooks, payments, diagnosis,
  triage, treatment automation, clinical decision support, and medical AI are
  absent and remain prohibited until future gated batches.
- Figma/design approval remains required for future visual changes. This audit
  defines product and handoff requirements only.

## Public Arabic/English Site

### Current Known Status

Status: `Partial`.

The public site has Arabic/default and English routes for home, doctor,
services, contact, privacy, terms, medical disclaimer, and WhatsApp policy.
Shared layout includes a language switch, primary navigation, a persistent
booking CTA, legal footer links, a skip link, and public safety/emergency
copy.

### What Exists

- Arabic/default routes:
  `/`, `/doctor/`, `/services/`, `/contact/`, `/privacy/`, `/terms/`,
  `/medical-disclaimer/`, and `/whatsapp-policy/`.
- English routes under `/en/`.
- Public SEO basics: `/robots.txt` and `/sitemap.xml`.
- Public content models for clinic profile, doctor, visit types, schedules, and
  closed days.
- Placeholder images/assets for clinic, doctor, and map.
- Public home sections for hero, clinic intro, highlighted services, why-this
  clinic, CTA, and location/hours.
- Doctor profile page with placeholder portrait and verified-wording warnings.
- Services page with service groups and visit types.
- Contact page with phone/address placeholders, map placeholder, booking CTA,
  and WhatsApp placeholder text.
- Legal draft pages linked from the footer.

### What Appears Missing

- Final verified public clinic phone, address, map/location, clinic hours, and
  doctor credential wording.
- Final approved bilingual content for home, doctor, services, contact, and
  legal pages.
- A public gallery page or gallery section with approved real assets.
- Authorized cases/reviews/media showcase implementation.
- Dashboard-managed draft/preview/publish workflow for public content.
- Human/owner-approved Figma or design handoff for any future visual changes.

### UX Friction Points

- Some public page copy still says booking is a later workflow or that visit
  options do not create bookings, while current booking does create confirmed
  appointments after final submission.
- Contact and doctor pages still show placeholders and verification notes,
  which is appropriate for safety but not final-product comfortable.
- WhatsApp is presented as a placeholder contact concept, not a real action.
- Public content management currently appears split between code fallbacks,
  seed data, and Django admin, not a polished dashboard workflow.

### Privacy/Security Constraints

- Public pages must not expose internal IDs, staff notes, audit logs, private
  clinical data, uploads, WhatsApp messages, payment details, or staff
  operation controls.
- Legal pages are operational drafts, not launch approval.
- Future cases/reviews/gallery media must require explicit publication consent.

### Mobile Concerns

- CSS is mobile-first, with responsive grids and wrapped navigation/actions.
- Staff-style tables use horizontal overflow handling where tables are reused.
- Final mobile QA still needs browser/device verification for Arabic and
  English text length, first-screen CTA clarity, forms, and no horizontal
  overflow.

### Arabic/English Concerns

- Arabic is the default route/language and English exists under `/en/`.
- Current templates support RTL/LTR through `lang` and `dir`.
- Some Arabic content could not be quality-reviewed from terminal output
  because the shell displayed mojibake; browser-level verification is needed.
- Stale English and Arabic legal/public copy must be updated through a future
  approved content/legal batch.

### Dashboard-Management Opportunities

- Clinic profile, doctor profile, services, visit types, contact, location,
  hours, gallery, legal draft status, and public CTA copy should be managed from
  a doctor/admin dashboard with validation, audit, preview, and publish states.

### Implementation Risks

- Updating public copy without legal review could create inaccurate legal or
  medical claims.
- Visual redesign without Figma/design handoff would violate project
  governance.
- Publishing patient media or reviews without explicit publication consent
  would violate privacy boundaries.

## Booking Flow

### Current Known Status

Status: `Partial but implemented for bounded public booking`.

Public booking is login-free and has Arabic/default plus English routes.
Booking proceeds through visit type selection, slot selection, confirmation
form, and UUID-token success page. Valid final POST creates a confirmed
appointment.

### What Exists

- `/book/`, `/book/visit-type/`, `/book/slots/`, `/book/confirm/`,
  `/book/success/<uuid:public_token>/`, plus English equivalents.
- Visit type selection from active visit types for the active doctor.
- Slot generation from active schedules, closed days, appointment conflicts,
  min lead time, max days ahead, slot interval, and visit duration.
- Public confirmation form with full name, phone, same-as-phone checkbox,
  optional WhatsApp phone, hidden visit type, hidden start time, and optional
  booking note.
- Jordan-first phone normalization with support for plausible international
  numbers starting with `+`.
- Public booking IP and phone rate limits using hashed identities.
- CSRF on public final POST.
- `never_cache` on confirmation and success pages.
- UUID public success URL with short confirmation reference.
- Optional portal-link CTA from success page.

### What Appears Missing

- Patient-facing self-service reschedule/cancel.
- Real reminder sending.
- WhatsApp confirmation/reminders.
- Production-tuned Redis/shared-cache rate limits.
- Production-like PostgreSQL concurrency evidence.
- Friendly dashboard for booking settings, hours, closed days, prices,
  instructions, and reminder rules.

### UX Friction Points

- Booking entry copy elsewhere on the public site and legal pages is stale.
- The optional WhatsApp phone field exists even though no WhatsApp sending is
  implemented, so final copy must avoid implying messages will be sent.
- No available slots lead to a simple empty state; final copy should guide the
  patient calmly without creating support burden.
- The success page links to portal appointment linking with the raw token in
  the query string. This is an explicit current flow, but it should remain
  no-cache and should not spread the token to account/dashboard pages.

### Privacy/Security Constraints

- No account may be required before booking.
- Public success must remain UUID-token based, not numeric ID based.
- Success may show only patient-safe confirmation details.
- Internal IDs, staff notes, booking private notes, audit data, medical
  records, uploads, WhatsApp messages, and payment details must not appear.
- Rate-limit identities must remain hashed and must not store raw phones in
  cache keys.

### Mobile Concerns

- Visit type cards, slot buttons, and confirmation form are mobile-friendly in
  structure.
- Final QA must confirm tap targets, date/slot readability, error visibility,
  and keyboard behavior on mobile.

### Arabic/English Concerns

- Booking routes and templates exist in Arabic/default and English.
- Final microcopy must avoid scary wording during normal booking.
- Error messages are partly generic English from services/forms; Arabic
  rendering of validation details needs browser verification.

### Dashboard-Management Opportunities

- Booking enabled/disabled state.
- Visit types, duration, price visibility, and instructions.
- Schedules and closed days.
- Lead time, max days ahead, slot interval, rate limits, and reminder offset.
- Patient-facing booking microcopy and unavailable/empty-state messages.

### Implementation Risks

- Incorrect booking settings could block all slots or create unrealistic
  availability.
- PostgreSQL/Redis/proxy behavior remains unvalidated in real restricted
  staging.
- Patient self-service reschedule/cancel would need identity, abuse, audit, and
  policy rules before implementation.

## Booking Success and Confirmation Behavior

### Current Known Status

Status: `Implemented for safe bounded confirmation`.

The final confirmation POST creates a confirmed appointment, redirects to the
UUID success URL, and success displays a short confirmation reference plus
patient-safe appointment details.

### What Exists

- Confirmation summary showing visit type and selected time.
- CSRF-protected final POST.
- Redirect to UUID success URL.
- Success page shows confirmation reference, patient name, doctor, visit type,
  and appointment time.
- Success page includes book-another, home, and optional portal-link actions.

### What Appears Missing

- Calendar export.
- Printed/downloadable confirmation.
- Reminder delivery state visible to patients.
- Reschedule/cancel instructions tied to approved policy.

### UX Friction Points

- The emergency warning appears on normal confirmation/success surfaces. It is
  safety-relevant but should remain calm and not dominate the happy path.
- Patients may not understand that portal linking is optional and not required
  for the appointment to remain confirmed.

### Privacy/Security Constraints

- Success page is bearer-link style and must remain no-cache.
- Public success must never show internal appointment IDs, patient IDs, user
  IDs, audit logs, status history notes, staff URLs, medical records, uploads,
  payment admin details, or raw staff notes.

### Implementation Risks

- Adding notifications or reminders without consent and provider review could
  violate privacy expectations.
- Adding patient self-service changes without identity controls could allow
  unauthorized appointment modification.

## Staff Appointment Operations

### Current Known Status

Status: `Partial`.

Staff appointment operations exist and are bounded to appointment list/detail
and status changes. This is not yet a full doctor/admin dashboard.

### What Exists

- Staff-only routes outside language prefixes:
  `/staff/appointments/`,
  `/staff/appointments/<appointment-id>/`, and POST-only cancel, reschedule,
  arrived, complete, and no-show operations.
- Anonymous staff routes redirect to Django admin login.
- Authenticated non-staff users receive `403`.
- Staff list filters by status, range, doctor, visit type, date range, and
  patient name/phone search.
- Staff detail shows internal ID, public reference, public token, status, time,
  patient, phone, doctor, visit type, booking note, operations, status history,
  and audit events.
- State changes write status history and audit logs.
- Terminal restore/undo is intentionally not implemented.

### What Appears Missing

- Today overview and daily workflow landing page.
- Broad dashboard navigation and grouped workflow modules.
- Appointment timeline UI optimized for repeated doctor/admin use.
- Custom dashboard management for public content and booking configuration.
- Reports, operational alerts, privacy/legal statuses, staff access review, and
  dashboard audit review screens.
- Staff copy localization or explicitly approved English-only staff policy.

### UX Friction Points

- Staff operations are functional but dense and form-heavy.
- Multiple operation forms appear on one detail page; final dashboard should
  group actions by status and risk.
- Reschedule requires manually entering a datetime rather than choosing from
  available validated slots.
- Audit metadata is visible in raw-ish JSON form to staff; useful for safety
  but not comfortable for daily review.

### Privacy/Security Constraints

- Staff pages may show internal operational data only after staff auth.
- Staff operation forms must remain CSRF-protected.
- Staff numeric appointment IDs must never become public/patient URLs.
- Staff audit data must not appear on patient pages.

### Mobile Concerns

- Staff pages use tables with horizontal scrolling and are likely more desktop
  oriented.
- Final dashboard may prioritize desktop but should remain usable on tablet and
  reasonable mobile access.

### Arabic/English Concerns

- Current staff templates are English.
- Final policy should decide whether dashboard operations are English-only or
  bilingual. If bilingual, all staff messages, statuses, filters, and errors
  need Arabic/English coverage.

### Dashboard-Management Opportunities

- Convert bounded appointment operations into a dashboard module with today,
  upcoming, detail, status actions, audit history, patient entry point, and
  settings/public-content sections.

### Implementation Risks

- A comfortable dashboard must not weaken current staff authorization, CSRF,
  no-cache, audit, and terminal-state safety.
- Adding reversible corrections needs a reviewed correction workflow, not a
  simple undo button.

## Patient Portal Foundation

### Current Known Status

Status: `Partial`.

The portal is optional and bounded to account access, password change, account
summary, static recovery policy, appointment linking, and linked appointment
viewing.

### What Exists

- `/portal/` dashboard and English equivalent.
- Login, POST-only logout, registration, account page, password change,
  account recovery policy, appointment linking, appointment list, and
  appointment detail.
- Patient accounts use normalized phone as username.
- Passwords use Django hashing and validation.
- Password change keeps the session valid.
- Appointment linking requires login, UUID token, and matching booking phone.
- Appointment list/detail are ownership-filtered by `patient__user`.
- Portal pages are no-cache.
- Generic errors avoid account/token disclosure.
- Portal rate-limit identities are hashed.
- Patient-visible appointment fields are limited to safe data.

### What Appears Missing

- Verified phone/email ownership.
- Real account recovery or self-service password reset.
- Patient identity verification policy.
- Self-service contact updates.
- Deletion request intake.
- Uploads, medical records, private media, payments, and WhatsApp message
  visibility.
- Abuse monitoring and production alerting.

### UX Friction Points

- Appointment linking requires the patient to handle a token plus phone number.
- Portal limits are repeated often, which is safe but may feel heavy if not
  balanced with calm copy.
- Account recovery is informational only; patients cannot start a structured
  recovery request.

### Privacy/Security Constraints

- Portal must not be required before public booking.
- Portal detail must use UUID token plus authenticated ownership filtering.
- Account pages must not expose raw public tokens or raw internal IDs.
- Portal must not show staff notes, booking notes, status history notes, audit
  logs, records, uploads, WhatsApp messages, or payment admin details.

### Mobile Concerns

- Portal reuses booking layout and staff-style tables. Appointment tables must
  be verified for mobile scanning and no horizontal overflow surprises.

### Arabic/English Concerns

- Portal routes and templates exist in Arabic/default and English.
- Password validation/help text may come from Django and needs bilingual review.

### Dashboard-Management Opportunities

- Patient portal explanatory text, support instructions, recovery policy
  status, and privacy labels should eventually be dashboard-managed with
  review states.

### Implementation Risks

- Self-service recovery without verified ownership is high risk.
- Medical records/uploads would create a new sensitive data surface and need
  private storage, authorization, retention, and legal gates.

## Account and Security Flows

### Current Known Status

Status: `Partial`.

Core web security behavior is implemented for the bounded scope, while
production account policy is not final.

### What Exists

- CSRF on state-changing forms.
- POST-only portal logout.
- No-cache behavior on booking confirmation/success, staff, and portal pages.
- Password hashing/validation.
- Safe `next` URL handling for portal login/registration.
- Generic login/linking/registration error behavior.
- Rate limits for booking, portal login, portal registration, and appointment
  linking.
- Health/readiness routes without internal details.
- Safe smoke/status/settings reports that avoid secrets and patient
  identifiers.

### What Appears Missing

- Verified phone/email ownership policy.
- Secure account recovery workflow.
- Abuse monitoring and alerting.
- Production Redis rate-limit tuning.
- Real reverse proxy/IP trust validation.
- Formal staff access review/offboarding.

### UX Friction Points

- Generic security errors are safe but need careful copy so patients know what
  to do next without account enumeration.
- Recovery currently sends patients to clinic support without a structured
  intake workflow.

### Privacy/Security Constraints

- No secrets, raw connection strings, tokens, passwords, raw request bodies, or
  real patient data may appear in logs, docs, smoke output, or reports.
- Public booking IP trust must remain conservative unless a trusted proxy is
  validated.

### Implementation Risks

- Any email/WhatsApp recovery implementation before ownership and privacy
  approval would weaken account security.

## Public Legal Pages

### Current Known Status

Status: `Draft and needs review`.

Privacy, terms, medical disclaimer, and WhatsApp policy pages exist in Arabic
and English. They are operational drafts.

### What Exists

- Footer links to legal pages.
- Each legal page includes review/draft wording.
- Medical disclaimer states no diagnosis/treatment automation and not for
  emergencies.
- WhatsApp policy states no real WhatsApp sending/webhook/automation exists.

### What Appears Missing

- Qualified legal/privacy approval.
- Updated legal copy reflecting that public booking and the bounded patient
  portal are now implemented.
- Retention/deletion policy.
- Account recovery and identity verification policy.
- Publication consent policy for cases/reviews/media.

### UX Friction Points

- Privacy and terms templates still describe a pre-booking/pre-portal batch in
  places. This is not final-product accurate.
- Draft warnings are necessary but should be integrated into a calm legal
  review status model before launch.

### Privacy/Security Constraints

- Legal pages must not overclaim launch readiness or legal approval.
- WhatsApp policy must not imply API/webhook functionality.

### Dashboard-Management Opportunities

- Legal/privacy copy may become dashboard-editable only with draft, pending
  review, approved, published, and superseded states.

### Implementation Risks

- Launching with stale legal copy could misrepresent how booking and portal
  data are collected and displayed.

## Operational Readiness Screens and Commands

### Current Known Status

Status: `Partial`.

The repository has safe operational commands and health endpoints. These are
operator-facing, not patient features.

### What Exists

- `/health/` public liveness endpoint.
- `/health/ready/` readiness endpoint intended for private/internal monitoring.
- `python manage.py deployment_smoke` with human, JSON, and strict modes.
- `python manage.py project_status_report` with human and JSON modes.
- `python manage.py production_settings_report` with human and JSON modes.
- Seed commands for safe public content and booking demo settings/schedules.
- Staging validation scripts and local-only PostgreSQL/Redis harness from
  earlier batches.

### What Appears Missing

- Real restricted staging validation evidence.
- Real PostgreSQL/Redis/HTTPS/proxy proof.
- Monitoring/alerting service configuration.
- Backup/restore drill evidence.
- Dashboard operational alert surface.

### UX Friction Points

- Operational readiness is command-line oriented. Doctor/admin dashboard users
  do not yet have a comfortable operational status view.

### Privacy/Security Constraints

- Reports must remain counts/booleans/categories only and must not print
  patient-identifying values or secrets.

### Implementation Risks

- Treating local smoke success as staging/production readiness would be unsafe.

## Cross-Flow Highest Priority UX/Product Gaps

1. Public/legal copy freshness: update stale booking/portal statements in a
   future implementation/content batch with legal review as needed.
2. Restricted staging validation: prove current booking, staff, portal, cache,
   and security behavior under PostgreSQL, Redis/shared cache, HTTPS, and
   proxy settings.
3. Dashboard product gap: define and implement a comfortable doctor/admin
   dashboard without weakening current staff-only and audit boundaries.
4. Dashboard-managed public content/configuration: move routine clinic content
   and operational settings out of programmer dependency, with validation,
   audit, review states, and safe defaults.
5. Patient portal production policy: define identity verification, recovery,
   contact changes, deletion request intake, and abuse monitoring before
   broader launch.
6. Authorized showcase: design and build only after publication consent,
   storage, legal/privacy, and Figma/design handoff gates.
7. WhatsApp: keep absent until consent, opt-out, provider, logging, webhook,
   credential, and privacy gates are approved.
