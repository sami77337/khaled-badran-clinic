# Security Regression Checklist

Run this checklist before any staging launch, production launch, or feature batch that touches routing, booking, authentication, settings, cache, proxy handling, or patient-facing data.

## Batch 10 Matrix Checks

- Review `docs/ROUTE_ACCESS_MATRIX.md` before merging route, view, URL, template,
  middleware, or auth changes.
- Review `docs/DATA_EXPOSURE_MATRIX.md` before merging public, portal, staff,
  account, smoke, logging, or template changes.
- Confirm `docs/PROJECT_MAP.md` remains accurate after app/module/command/test
  changes.
- Confirm `docs/STAGING_VALIDATION_PLAN.md` is followed before claiming staging
  readiness.
- Confirm future visual changes follow `docs/FIGMA_DESIGN_HANDOFF.md` and do not
  weaken route, CSRF, cache, ownership, or privacy protections.

## Public Booking Tokens

- Public appointment success URLs use UUID `public_token` values.
- Public success pages do not use numeric appointment IDs.
- Public success pages show only approved confirmation details.
- Public success pages do not show internal notes, staff notes, audit logs, internal IDs, medical data, uploads, or future medical-record content.

## Numeric Success Route

- `/book/success/<numeric-id>/` returns 404.
- `/en/book/success/<numeric-id>/` returns 404.
- Staff-only numeric appointment IDs remain behind staff authorization only.

## Staff-Only Pages

- `/staff/appointments/` requires authenticated active staff.
- `/staff/appointments/<appointment-id>/` requires authenticated active staff.
- Staff cancel/reschedule/arrived/complete/no-show operations require staff.
- Anonymous users redirect to admin login.
- Authenticated non-staff users receive 403.
- Audit logs and status history remain staff-only.

## CSRF

- Public booking POST uses CSRF protection.
- Staff operations use CSRF protection.
- `DJANGO_CSRF_TRUSTED_ORIGINS` is set for staging and production HTTPS origins.
- No CSRF trusted origin wildcard is used.

## Patient Portal Foundation and Account Security

- `/portal/` requires authenticated patient access.
- `/portal/account/` requires authenticated patient access.
- `/portal/password/change/` requires authenticated patient access.
- `/portal/account-recovery/` is informational only and does not collect sensitive data.
- `/portal/login/`, `/portal/register/`, `/portal/password/change/`, and `/portal/link-appointment/` POSTs use CSRF protection.
- Password change uses Django password validation, Django password hashing, and session hash refresh after success.
- Email password reset is not implemented unless a safe production email ownership and delivery policy is approved.
- Account recovery remains clinic-assisted and must not disclose whether an account exists.
- Patient portal pages are marked no-cache.
- Portal navigation keeps logout as POST-only.
- Patient account pages show only display name, masked username/phone, optional email, and linked appointment count.
- Patient appointment detail URLs use UUID `public_token`, not numeric appointment IDs.
- `/portal/appointments/<numeric-id>/` returns 404.
- User A cannot access User B's linked appointment.
- Appointment linking requires an authenticated user, the appointment public token, and a phone number matching the appointment patient's normalized phone.
- Wrong phone and nonexistent token cases use a generic error and do not link.
- A Patient already linked to another user cannot be stolen.
- Re-linking an appointment already linked to the same user is a safe no-op.
- Portal appointment pages show only patient-safe appointment data.
- Portal appointment pages do not show internal IDs, staff notes, booking notes, status history notes, audit logs, medical records, uploads, WhatsApp messages, or payment admin details.
- Patient account and dashboard pages do not expose raw appointment public
  tokens.
- Patient pages do not link staff appointment operation URLs.
- Patient templates do not expose audit/status-history/private-note strings.

## Routes Not Yet Implemented

- No upload routes yet, including under `/portal/`.
- No WhatsApp webhook routes yet.
- No online payment routes yet.
- No medical record routes yet.
- No medical AI, diagnosis automation, triage automation, or treatment automation routes.

## Public Page Privacy

- Public pages do not show internal notes.
- Public pages do not show audit logs.
- Public pages do not show staff-only controls.
- Public pages do not expose private media paths.
- Legal pages remain informational drafts until legal/privacy review.

## Audit Logs

- Audit logs are visible only to staff through staff appointment detail.
- Audit metadata remains operational and limited.
- Audit logs are not treated as a complete infrastructure audit trail.
- Audit retention and access review policy remains a pre-launch requirement.

## Rate Limiting

- Public booking IP rate limit is active.
- Public booking phone rate limit is active.
- Raw phone numbers are not used in cache keys.
- Patient portal appointment-link rate limit is active.
- Patient portal login and registration rate limits are active if enabled by the current code path.
- Patient portal cache keys do not include raw public tokens, raw phone numbers, or passwords.
- Staff operations are not blocked by public booking rate limits.
- Staging and production use shared cache, not LocMemCache.

## Trusted Proxy and IP Handling

- `BOOKING_TRUST_X_FORWARDED_FOR=false` unless a trusted reverse proxy strips client-supplied `X-Forwarded-For`.
- `BOOKING_TRUSTED_PROXY_CONFIGURED=true` only after proxy behavior is reviewed.
- `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true` only after the proxy overwrites incoming `X-Forwarded-Proto`.
- Rate-limit behavior is tested through the real staging proxy before launch.

## Secure Cookies and HSTS

- Production-like settings use secure session cookies.
- Production-like settings use secure CSRF cookies.
- HTTPS redirect is enabled unless a reviewed staging exception exists.
- HSTS settings are intentionally chosen.
- HSTS preload is enabled only after full HTTPS coverage and operational approval.

## Secret Hygiene

- Smoke output does not print application secrets.
- Smoke output does not print database connection strings.
- Smoke output does not print cache connection strings.
- Logs do not print passwords, tokens, cookies, authorization headers, CSRF tokens, raw request bodies, or environment dumps.
- `.env`, database dumps, logs, private media, and credentials are not committed.

## CI and Smoke

- CI passes.
- `python manage.py makemigrations --check --dry-run` passes.
- `python manage.py check` passes.
- `python manage.py test` passes.
- `python manage.py deployment_smoke` runs in CI.
- `python manage.py deployment_smoke --json` emits safe JSON keys only.
- Deployment smoke includes public booking security summary.
- Deployment smoke includes patient portal security summary.
- Deployment smoke includes project consolidation summary.
- Deployment smoke includes prohibited-feature disabled summary.
- Deployment smoke does not print patient names, emails, phone numbers, raw
  public tokens, or appointment confirmation references.
- `python manage.py project_status_report` and
  `python manage.py project_status_report --json` do not print patient names,
  emails, phone numbers, raw public tokens, secrets, or connection strings.
- In staging/production-like settings, `python manage.py check --deploy` is reviewed.
- In staging/production-like settings, `python manage.py deployment_smoke --strict` passes.

## Seed Command Safety

- `python manage.py seed_public_content` does not create patients or
  appointments.
- `python manage.py seed_booking_demo` does not create patients or appointments.
- Seed commands do not create WhatsApp messages, uploads, secrets, credentials,
  payments, medical records, or real patient data.

## Portal Expansion Gate

Do not expand beyond bounded portal account security and linked-appointment viewing, add uploads, implement WhatsApp sending/webhooks, expose medical records, add online payments, or add medical automation until staging smoke and this security regression checklist are reviewed.
