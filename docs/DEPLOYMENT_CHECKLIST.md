# Deployment Checklist

This checklist is for a future deployment engineer. Batch 6 does not deploy anything.

## Pre-Deployment Gate

- Confirm the deployment branch and release artifact are reviewed.
- Confirm no `.env`, secrets, logs, private media, or real patient data are committed.
- Confirm patient portal, uploads, WhatsApp API/webhooks, online payments, medical records, and medical automation remain out of scope unless a later approved batch implements them.
- Run `python manage.py makemigrations --check --dry-run`.
- Run `python manage.py check`.
- Run `python manage.py test`.
- Review `python manage.py check --deploy` output under the intended production settings.
- Confirm dependency installation from `requirements.txt`.
- Run dependency vulnerability scanning.
- Confirm legal/privacy review status before public launch.

## Environment Variables

- `DJANGO_SETTINGS_MODULE=config.settings.prod`.
- `DJANGO_SECRET_KEY` set to a generated secret outside Git.
- `DJANGO_DEBUG=false`.
- `DJANGO_ALLOWED_HOSTS` set to exact production hosts.
- `DJANGO_CSRF_TRUSTED_ORIGINS` set to HTTPS origins.
- `DATABASE_URL` set to PostgreSQL.
- `DATABASE_SSL_REQUIRE` matches provider requirements.
- `CACHE_URL` set to shared Redis.
- `DJANGO_SECURE_SSL_REDIRECT=true`.
- `DJANGO_SECURE_HSTS_SECONDS` intentionally chosen.
- `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` intentionally chosen.
- `DJANGO_SECURE_HSTS_PRELOAD` intentionally chosen.
- `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED` set only after proxy review.
- `BOOKING_TRUST_X_FORWARDED_FOR=false` unless trusted proxy stripping is verified.
- `BOOKING_TRUSTED_PROXY_CONFIGURED=true` only if the trusted proxy review is complete.
- `DJANGO_LOG_LEVEL` set.
- `SENTRY_DSN` or other error-reporting DSN configured only after privacy scrubbing review.

## HTTPS, HSTS, and Cookies

- TLS certificates provisioned and auto-renewal tested.
- HTTP to HTTPS redirect works.
- `SESSION_COOKIE_SECURE=true`.
- `CSRF_COOKIE_SECURE=true`.
- `CSRF_COOKIE_SAMESITE=Lax`.
- `SESSION_COOKIE_SAMESITE=Lax`.
- HSTS enabled only after HTTPS is stable.
- HSTS includeSubDomains enabled only when all subdomains support HTTPS.
- HSTS preload submitted only after operational/legal approval.

## Trusted Hosts and CSRF

- `ALLOWED_HOSTS` contains only production hostnames.
- No wildcard host in production.
- `CSRF_TRUSTED_ORIGINS` contains all HTTPS public origins.
- Booking POST flow tested through each public hostname.
- Admin login tested through the production hostname.

## PostgreSQL

- PostgreSQL is provisioned.
- App database exists.
- Least-privilege app user exists.
- Database password stored only in secret manager/environment.
- SSL requirement confirmed.
- Connection limits and `DATABASE_CONN_MAX_AGE` reviewed.
- Migrations run in a controlled deployment step.
- Production-like migration test completed.
- Booking duplicate/concurrency behavior tested under PostgreSQL.

## Backups and Restore

- Automated database backups enabled.
- Backup encryption enabled.
- Backup retention documented.
- Restore drill completed before launch.
- Restore drill owner assigned.
- Restore time objective documented.
- Data-loss tolerance documented.
- Backup monitoring/alerts configured.
- Backup access limited to authorized operators.

## Redis and Rate Limiting

- Redis or equivalent shared cache provisioned.
- `CACHE_URL` configured.
- `DJANGO_CACHE_KEY_PREFIX` unique to environment.
- Booking IP rate limit tested across multiple app processes if applicable.
- Booking phone rate limit tested.
- LocMemCache is not used in production.
- Redis persistence and eviction policy reviewed.

## Reverse Proxy and IP Handling

- Proxy overwrites incoming `X-Forwarded-Proto`.
- Proxy sets `X-Forwarded-Proto=https` for HTTPS.
- `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true` only after that behavior is verified.
- Proxy strips incoming client-supplied `X-Forwarded-For` if `BOOKING_TRUST_X_FORWARDED_FOR=true`.
- Proxy sets its own trusted `X-Forwarded-For`.
- Rate limiting tested with real proxy behavior.
- Default remains `BOOKING_TRUST_X_FORWARDED_FOR=false` if not verified.

## Static Files

- `python manage.py collectstatic` run.
- `STATIC_ROOT` served by reverse proxy, CDN, or reviewed static file middleware.
- Cache headers for static assets configured.
- Admin static files verified.
- Public CSS/JS/images verified.

## Media and Private Files

- Uploads are not implemented yet.
- No patient medical files stored under public static/media URLs.
- Future private storage design reviewed before uploads.
- Future private media backup/restore policy documented.
- Future private media access logging and retention policy documented.

## Logging, Monitoring, and Error Reporting

- Application stdout/stderr collected.
- Request errors visible in platform logs.
- Security warnings visible.
- Infrastructure access logs configured.
- Logs exclude full form payloads and patient medical content.
- Log retention policy documented.
- Uptime monitoring configured for `/health/`.
- Internal readiness monitoring configured for `/health/ready/`.
- Error reporting configured only with privacy scrubbing.
- Alert routing tested.

## Audit Logs

- AuditLog retention policy defined.
- Staff access to audit logs reviewed.
- AuditLog is not treated as a full infrastructure audit trail.
- Audit export/access process reviewed if legally required.

## Accounts and Access

- Least-privilege admin/staff accounts created.
- Shared admin accounts prohibited.
- Strong passwords enforced.
- Superuser count minimized.
- Staff access review scheduled.
- Offboarding process documented.

## Legal, Privacy, and Safety

- Privacy policy reviewed by qualified counsel.
- Terms reviewed.
- WhatsApp policy reviewed.
- Medical disclaimer reviewed.
- No emergency-care claims added.
- No diagnosis, triage, treatment, or medical AI automation enabled.
- Data retention and deletion request process reviewed.
- Local legal/privacy obligations assessed.

## Load and Security Testing

- Load test public pages.
- Load test booking slot generation.
- Load test duplicate booking submissions.
- Load test staff appointment list/detail.
- Run vulnerability scan.
- Run dependency update review.
- Review Django security settings with `check --deploy`.
- Review admin exposure and rate limits.

## Incident Response

- Incident owner assigned.
- On-call/contact path documented.
- Secret rotation process documented.
- Database credential rotation process documented.
- Rollback process documented.
- Backup restore process documented.
- Patient/privacy incident escalation process documented.
- Post-incident review process documented.

## Launch Decision

Do not launch until all required items are complete or formally accepted as documented risks by the project owner.
