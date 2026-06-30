# Security Hardening

This document records the Batch 6 security posture. It is not a replacement for a legal, privacy, or security review.

## Safe Defaults

Local development:

- Uses `config.settings.dev`.
- Allows SQLite fallback.
- Uses LocMemCache.
- Keeps HTTPS/HSTS/secure-cookie settings disabled by default.
- Keeps `BOOKING_TRUST_X_FORWARDED_FOR=false`.

Production:

- Uses `config.settings.prod`.
- Requires `DJANGO_SECRET_KEY`.
- Requires `DJANGO_ALLOWED_HOSTS`.
- Requires `DATABASE_URL`.
- Defaults `DJANGO_DEBUG` to false.
- Enables HTTPS redirect by default.
- Enables secure session and CSRF cookies.
- Enables HSTS by default.
- Reads `DJANGO_CSRF_TRUSTED_ORIGINS` from the environment.
- Enables `SECURE_PROXY_SSL_HEADER` only when explicitly requested.

## Production System Checks

Batch 6 adds production-only checks under `apps.core.checks`.

When `PRODUCTION=True`, checks report:

- `clinic.E001`: `DEBUG=True`.
- `clinic.E002`: missing or placeholder `SECRET_KEY`.
- `clinic.E003`: empty or wildcard `ALLOWED_HOSTS`.
- `clinic.E004`: empty `CSRF_TRUSTED_ORIGINS`.
- `clinic.E005`: LocMemCache in production.
- `clinic.E006`: SQLite in production.
- `clinic.W001`: `BOOKING_TRUST_X_FORWARDED_FOR=True` without trusted proxy attestation.

These checks intentionally do not make local development noisy.

## Booking Security Boundaries

Preserved boundaries:

- Public booking remains login-free.
- Public success pages use non-enumerable UUID `public_token` values.
- Public success pages do not use internal numeric appointment IDs.
- Staff appointment pages require authenticated active users with `is_staff=True`.
- Anonymous users are redirected to Django admin login before staff pages load.
- Authenticated non-staff users receive 403.
- Staff operations remain bounded to appointment list/detail and status operations.
- Patient portal routes are added for optional account registration, login, account summary, password change, clinic-assisted recovery policy, appointment linking, and linked appointment viewing.
- Patient password change uses Django password validation, Django password hashing, CSRF protection, `sensitive_post_parameters`, no-cache responses, and session hash refresh after success.
- Email password reset is not implemented because production email ownership, delivery, and recovery policy are not configured yet.
- Account recovery is informational and clinic-assisted for now; it does not collect sensitive data, send email, send WhatsApp messages, create support tickets, or disclose whether an account exists.
- Patient portal appointment detail uses UUID `public_token` URLs and authenticated ownership checks.
- Patient portal linking requires a public token and matching booking phone, with generic errors for wrong phone or nonexistent token.
- No upload routes are added.
- No WhatsApp webhook/API routes are added.
- No payments, medical records, medical AI, diagnosis automation, triage automation, or treatment automation are added.

Batch 10 adds explicit route and data-surface inventories:

- `docs/ROUTE_ACCESS_MATRIX.md` documents method, auth, staff, ownership, CSRF,
  cache, data exposure, implementation file, and prohibited-route expectations.
- `docs/DATA_EXPOSURE_MATRIX.md` documents public, patient portal, staff-only,
  internal-only, and never-on-patient-page fields.

Future route or template changes must be checked against both matrices before
merge.

## Rate Limiting and IP Handling

Public booking POSTs use Django cache rate limiting:

- Per-IP hourly quota.
- Per-normalized-phone daily quota.
- Raw phone numbers are not stored in cache keys.

Patient portal rate limiting uses Django cache:

- Appointment linking is throttled by authenticated user/IP and normalized phone hash when available.
- Login is throttled by IP and normalized phone hash when available.
- Registration is throttled by IP and normalized phone hash when available.
- Raw public tokens, raw phone numbers, and passwords are not stored in portal cache keys.
- Defaults are intentionally light for local development; staging and production must tune these limits against shared-cache behavior.

Default IP behavior:

- Uses `REMOTE_ADDR`.
- Ignores `X-Forwarded-For`.

Only enable `BOOKING_TRUST_X_FORWARDED_FOR=true` when:

- A trusted reverse proxy strips incoming client-supplied `X-Forwarded-For`.
- The proxy sets its own trusted `X-Forwarded-For`.
- The deployment engineer sets `BOOKING_TRUSTED_PROXY_CONFIGURED=true` after review.

Production rate limiting must use shared cache, not LocMemCache.

Account-security reminder:

- Portal login, registration, password change, logout, account recovery, and
  appointment linking must preserve CSRF expectations.
- Portal logout must remain POST-only.
- Account recovery must remain GET-only/static until a reviewed recovery process
  exists.
- Email password reset must remain disabled until production email ownership,
  delivery, and recovery policy are approved.
- Staging and production must tune public booking and portal rate limits against
  Redis/shared cache behavior.

## Caching Rules

Batch 6 marks these responses as no-cache:

- `/health/`
- `/health/ready/`
- Booking confirmation.
- Booking success.
- Staff appointment pages and operations.
- Patient portal pages, including account, password change, and account recovery policy.

Public informational pages can be made cacheable later after a reviewed policy. Staff, medical, private, and patient-specific pages must not be cached publicly.

## Logging Rules

Configured logging:

- Console logging for local and production.
- Django request error logging.
- Django security logging.
- App logger namespace for booking.

Do log:

- Exceptions and request errors.
- Security warnings.
- Operational event summaries.
- Infrastructure health events.

Do not log:

- Full form payloads.
- Booking notes by default.
- Patient medical content.
- Future medical records.
- File contents or uploads.
- Secrets, tokens, passwords, cookies, CSRF tokens, authorization headers, database URLs.
- Raw request bodies.

`AuditLog` stores app-level operational events and limited metadata. It is not a replacement for platform logs, access logs, database audit logs, or SIEM/error-reporting tools.

## Health Endpoint Safety

`/health/`:

- Public liveness only.
- Does not touch the database.
- Does not expose settings, versions, hostnames, database details, or secrets.

`/health/ready/`:

- Intended for private/internal checks.
- Checks database connectivity.
- On failure, returns only `{"status": "unavailable"}` with HTTP 503.
- Does not expose exception text.

## Static and Media Safety

Static:

- Use `collectstatic`.
- Serve static files by reverse proxy, CDN, or reviewed middleware.
- Do not serve private files from static directories.

Media/private files:

- Uploads are not implemented.
- Future uploads must use private storage.
- No sensitive medical files should have public URLs.
- No sensitive medical files should be cached publicly.
- Future private media backups and restore drills must be included.

## Design Governance and Security

Figma is the source of truth for visual design. Codex must not invent visual
design decisions or use design changes to bypass security/privacy requirements.

Future Figma-approved visual implementation must preserve:

- UUID-only public booking success URLs,
- public booking without login,
- staff-only appointment operations,
- CSRF protection,
- no-cache patient portal pages,
- patient appointment ownership filtering,
- static/clinic-assisted account recovery until a recovery design is approved,
- no upload, medical-record, WhatsApp API/webhook, payment, diagnosis, triage,
  treatment automation, or medical AI routes unless separately approved.

See `docs/FIGMA_DESIGN_HANDOFF.md`.

## Dependency and Secret Hygiene

- Dependencies are declared in `requirements.txt`.
- Redis client is included to support Django's Redis cache backend for production rate limiting.
- No real secrets are committed.
- `.env` is ignored.
- Local logs, coverage output, SQLite databases, and media/private media paths are ignored.
- Run vulnerability scanning before launch and on a recurring schedule.

## Remaining Security Work

Before launch:

- Complete legal/privacy review.
- Define verified email or phone ownership, secure self-service account recovery if desired, patient identity verification, and portal abuse monitoring policies before public portal launch.
- Tune portal login, registration, and appointment-link rate limits in staging with Redis/shared cache.
- Configure actual production hosting, TLS, proxy, PostgreSQL, Redis, monitoring, and backups.
- Add dependency vulnerability scanning.
- Add error reporting with privacy scrubbing if approved.
- Perform load testing and concurrency testing.
- Define audit retention and staff access review policy.
- Create incident response runbook.
- Design private media storage before uploads.
