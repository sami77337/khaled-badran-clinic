# Security Regression Checklist

Run this checklist before any staging launch, production launch, or feature batch that touches routing, booking, authentication, settings, cache, proxy handling, or patient-facing data.

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

## Routes Not Yet Implemented

- No patient portal routes yet.
- No upload routes yet.
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
- In staging/production-like settings, `python manage.py check --deploy` is reviewed.
- In staging/production-like settings, `python manage.py deployment_smoke --strict` passes.

## Pre-Portal Gate

Do not begin patient portal, uploads, WhatsApp sending/webhooks, medical records, online payments, or medical automation until staging smoke and this security regression checklist are reviewed.
