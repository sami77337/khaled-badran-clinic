# KBC MASTER HANDOFF — Final Commercial Delivery v1

هذه الوثيقة هي المرجع التنفيذي الحالي بعد إغلاق **Commercial Delivery v1**. عند التعارض، الترتيب هو:

1. قرار المالك الحالي.
2. GitHub live / PR / branch الحالي.
3. Final approved Figma visual language.
4. `docs/CLINIC_DELIVERY_V1_SCOPE_LOCK.md`.
5. هذه الوثيقة.
6. الوثائق التاريخية الأقدم.

## الحالة الحالية

- Repository: `sami77337/khaled-badran-clinic`
- Production: `https://drkhaledbadran.com`
- Final application delivery commit: `f25fcac7d300c6aeb6b472bd4a009341e740f69a`
- Final application deploy: `dep-daropq7avr4c73fimu6g` — **LIVE**
- PR #101: merged — Home Services final visual gap fix.
- PR #96: closed as superseded.
- PR #100: closed as superseded.
- Open closeout PRs: none at the time of this handoff.
- Commercial Delivery v1 status: **CLOSED / HANDED OFF**
- Production Readiness remains a separate track and must not reopen Commercial Delivery unless a real blocker is found.

## Final QA evidence

Latest application merge candidate:

- Dependency audit: PASS.
- Django checks: PASS.
- `python manage.py makemigrations --check --dry-run`: PASS.
- deployment smoke: PASS.
- Full Django suite: **1249 tests PASS**.
- Rendered AR/EN Home/Public/Staff coverage: PASS at `320 / 390 / 768 / 1024 / 1440`.
- Patient closeout/privacy browser matrices: PASS.
- Production startup: migrations current, media-storage checks PASS, Gunicorn healthy.
- Production service reached LIVE on the final application delivery commit.
- Reminder cron resumed successful runs after the deployment transition.

Expected negative-path tests may log 4xx/5xx messages inside CI while still passing; use the final test result, not isolated expected-error log lines, as the gate.

## Final visual state

Approved design language is preserved:

- Arabic default / RTL.
- English / LTR.
- Burgundy / cream / warm wood-gold language.
- Existing typography, radii, shadows and component language preserved.
- No redesign was introduced in closeout.

Home final behavior:

- Mobile below 768px: Services section hidden.
- Tablet/Desktop at 768px and above: `Cases → Services → Reviews`.
- Existing service card component reused.
- Mobile active navigation keeps the approved wood/beige treatment.

## Public / Booking

- Public Home / Doctor / Services / Cases / Reviews / Contact are delivered.
- Booking does not require login.
- Existing availability and booking lifecycle are preserved.
- Booking Confirmation uses the configured Meta-approved template flow.
- No public WhatsApp contact button/link is part of the final public website.

## Appointment Operations / Messaging

Staff workflow:

1. Appointment remains Confirmed/Rescheduled until staff action.
2. Overdue appointments enter the Needs Classification workflow.
3. Staff can classify Arrived / No-show and complete visits according to current rules.
4. Arrived/No-show message compose uses one editable field.
5. The field is prefilled from the configured AR/EN default with safe appointment placeholders.
6. Staff may send it as-is, edit/replace it, or choose No Message.
7. This post-classification flow opens WhatsApp manually; it does not falsely mark a message Sent/Delivered.

Appointment Messages page:

- Persistent dashboard access.
- AR/EN defaults for Arrived / No-show.
- Placeholder explanations.
- Automatic Reminder controls.
- Global Reminder enable/disable.
- Default lead time setting; default is 180 minutes / 3 hours.
- Changing the default affects new bookings; existing appointments keep their saved offset.

Automatic Reminder:

- Uses Meta-approved WhatsApp template.
- Template body is not free-text editable from the clinic dashboard.
- Scheduler runs via Render cron every minute.
- Internal dispatch endpoint is POST-only and token protected.
- Reminder is marked sent only after accepted provider delivery attempt according to current implementation.

## Dashboard / Staff

Delivered staff capabilities include:

- Scheduling and exceptions.
- Appointment operations and follow-up.
- Appointment Messages / Reminder controls.
- Patient list and records.
- Visit/note creation.
- Private image / short-video upload.
- Patient visibility controls.
- Public-case consent and publication controls.
- Patient review moderation.
- Website content manager.
- Doctor profile/content management.
- Staff attention bell and notifications.

## Patient Portal / Privacy

Final Commercial QA verified:

- patient ownership isolation.
- patient sees only own approved content.
- portal medical content is read-only in v1.
- private/trashed/other-patient media denied.
- no direct private medical media URLs.
- no public patient PII.
- CSRF/auth boundaries preserved.
- appointment list/detail/cancel/reschedule flows covered.
- Close Account requires current safeguards and preserves retained records according to the implemented lifecycle.
- AR/EN and responsive portal layouts covered.

## Public Cases / Consent

Public display requires the current consent/publication gates:

- approved public-case state.
- confirmed consent.
- active/public eligibility.

Public media uses controlled routes; private storage paths are not exposed. Patient identity and private clinical data must not appear publicly.

## Daily clinic operations vs Developer/Admin work

Clinic/doctor daily operation:

- manage schedule and appointments.
- classify visits.
- use Appointment Messages.
- enable/disable reminders and set the default lead time.
- review patient records/media and visibility.
- manage reviews.
- manage public cases only after consent.
- use Website Content Manager for approved editable public content.

Developer/Admin-only work:

- Meta template creation/approval or credential changes.
- Render service/cron configuration.
- environment variables/secrets.
- database/storage operations.
- dependency upgrades.
- infrastructure/DNS/TLS changes.
- schema/code changes.
- incident/security operations.

## Security invariants

Do not break:

- no real patient data in tests/docs/screenshots.
- records private by default.
- patient ownership isolation.
- patient-visible != public.
- public case requires consent.
- no direct private-media URL.
- no public patient PII.
- CSRF/auth boundaries.
- no secrets in Git/docs.
- no medical AI diagnosis/treatment automation.

## Continuation rule

Commercial Delivery v1 is closed. New work must be classified as exactly one of:

1. real defect correction.
2. Production Readiness / Operations.
3. deployment/data operation.
4. owner-approved new scope.

Do not reopen finished backend/features or redesign approved surfaces without a new owner decision.
