# Production Readiness

Batch 6 prepares the project for a professional production deployment, but it does not deploy the app and does not claim launch readiness. It hardens settings, adds checks, documents infrastructure expectations, and improves health/readiness behavior.

## Current Status

Ready for future deployment planning:

- Split settings are preserved: `config.settings.dev` and `config.settings.prod`.
- Production settings require `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `DATABASE_URL`.
- `DJANGO_DEBUG` is environment-driven and defaults to false in production settings.
- HTTPS redirect, secure cookies, and HSTS are enabled by default only in production settings.
- `DJANGO_CSRF_TRUSTED_ORIGINS` is environment-driven.
- PostgreSQL is supported through `DATABASE_URL`.
- Redis cache is supported through `CACHE_URL` for production rate limiting.
- Production-only Django system checks flag unsafe production configurations.
- Logging is configured for stdout/stderr collection without adding request body logging.
- `/health/` provides public liveness without internals.
- `/health/ready/` checks database connectivity and returns only `ok` or `unavailable`.
- Booking confirmation/success and staff appointment pages are marked no-cache.
- CI runs migrations check, Django check, and tests on SQLite.

Not production-ready until these are completed:

- Actual hosting platform, reverse proxy, TLS certificates, and DNS are configured.
- PostgreSQL is provisioned with least-privilege credentials.
- Redis or equivalent shared cache is provisioned.
- Backups and restore drills are tested.
- Monitoring, uptime checks, and error reporting are configured.
- Legal/privacy review is complete.
- Static serving strategy is chosen and tested.
- Private media design is completed before uploads.
- Load testing and concurrency testing are performed.
- Dependency vulnerability scanning and update policy are in place.

## Settings Behavior

Local development uses `config.settings.dev` by default through `manage.py`.

Development defaults:

- `DEBUG=true` unless overridden.
- `ALLOWED_HOSTS=localhost,127.0.0.1,[::1]` unless overridden.
- Empty `DATABASE_URL` uses `db.sqlite3`.
- Empty `CACHE_URL` uses LocMemCache.
- HTTPS redirect, secure cookies, and HSTS are disabled.
- `BOOKING_TRUST_X_FORWARDED_FOR=false`.

Production uses `config.settings.prod`.

Production behavior:

- `DJANGO_SECRET_KEY` is required and must not be a placeholder.
- `DJANGO_ALLOWED_HOSTS` is required.
- `DATABASE_URL` is required.
- `DJANGO_DEBUG` defaults to false.
- `DJANGO_SECURE_SSL_REDIRECT` defaults to true.
- `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` are true.
- HSTS defaults to one year with includeSubDomains and preload enabled.
- `CSRF_TRUSTED_ORIGINS` comes from `DJANGO_CSRF_TRUSTED_ORIGINS`.
- `SECURE_PROXY_SSL_HEADER` is set only when `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true`.

## Database Readiness

SQLite is local-only. It is acceptable for local development and CI but not production.

Production should use PostgreSQL:

1. Create a database, for example `khaled_badran_clinic`.
2. Create a least-privilege app user.
3. Grant only required database permissions.
4. Store the connection string in `DATABASE_URL`.
5. Run migrations before traffic is switched to the new app version.
6. Keep migration execution as a controlled deployment step, not an automatic side effect of app startup.

Suggested PostgreSQL creation outline:

```sql
CREATE DATABASE khaled_badran_clinic;
CREATE USER clinic_app WITH PASSWORD 'replace-with-real-secret-outside-git';
GRANT ALL PRIVILEGES ON DATABASE khaled_badran_clinic TO clinic_app;
```

Adjust privileges for the hosting provider and PostgreSQL version. Do not commit the real password.

Migration safety:

- Run `python manage.py makemigrations --check --dry-run` in CI.
- Review generated migrations before deployment.
- Run `python manage.py migrate` during a controlled deployment window.
- Back up before migrations that alter important tables.
- For high-risk migrations, test on a restored production-like backup first.

Booking concurrency note:

- Booking and staff operations use transactions and active-slot uniqueness.
- PostgreSQL must be used before launch to validate production concurrency behavior.
- Load testing should include duplicate public booking POSTs and staff rescheduling races.

Backup expectations:

- Automated PostgreSQL backups at least daily before launch.
- Point-in-time recovery if supported by the provider.
- Backup encryption at rest.
- Access restricted to deployment/admin operators.
- Restore drill before launch and then on a recurring schedule.
- Record restore time objective and data-loss tolerance.

## Cache and Rate Limit Readiness

Public booking rate limits use Django cache:

- IP hourly quota.
- Normalized phone daily quota.
- Cache keys hash identities and do not store raw phone numbers.

Local LocMemCache is acceptable for development. It is not acceptable for production because each process has a separate in-memory cache.

Production must use a shared backend such as Redis or Memcached. Batch 6 supports Redis through `CACHE_URL`:

```text
CACHE_URL=redis://redis-host.example.com:6379/1
```

The production system check reports an error when production mode uses LocMemCache.

Memcached remains an acceptable alternative if the deployment explicitly configures Django `CACHES` with a reviewed Memcached backend and driver.

## Logging and Observability

The project configures console logging for Django, request errors, security events, and app loggers. Production platforms should collect stdout/stderr.

Log:

- Request errors and exceptions.
- Deployment/runtime health.
- Security warnings from Django.
- Booking operational events at a safe summary level.
- AuditLog records for sensitive app-level operations.

Do not log:

- Full form payloads.
- Booking notes by default.
- Patient medical history, future records, diagnoses, attachments, or file contents.
- Secrets, tokens, database URLs, cookies, authorization headers, or CSRF tokens.
- Raw request bodies.

`AuditLog` is an application-level operational record. It is not a replacement for infrastructure logs, access logs, database audit trails, or error reporting.

Third-party error reporting is not active in Batch 6. If Sentry or another service is added later, configure privacy scrubbing before enabling it.

## Health Checks

`GET /health/`

- Public liveness.
- Returns small JSON: `status` and service name.
- Does not check database.
- Does not expose secrets, settings, database engine, hostname, or version.

`GET /health/ready/`

- Readiness endpoint intended for private/internal monitoring or a load balancer health check.
- Checks database connectivity.
- Returns only `{"status": "ok"}` or `{"status": "unavailable"}`.
- Does not expose exception details.
- Should not be indexed or exposed as a diagnostic endpoint to patients.

## Static Files

Static files are not served by Django directly in production unless a reviewed static serving solution is added.

Deployment options:

- Reverse proxy serves files from `STATIC_ROOT` after `python manage.py collectstatic`.
- CDN serves collected static files.
- WhiteNoise may be added later if the deployment target benefits from it.

Current command:

```bash
python manage.py collectstatic
```

`STATIC_ROOT=staticfiles` is ignored by Git.

## Media and Private Files

Uploads are not implemented in this batch.

Future patient uploads must:

- Use private storage.
- Avoid public `MEDIA_URL` access for medical files.
- Require authenticated authorization checks.
- Prevent public caching of sensitive files.
- Include malware/content-type controls.
- Include backup and restore coverage.
- Include retention/deletion policy review.

Do not store sensitive medical uploads under public static directories.

## Reverse Proxy and IP Handling

Default behavior is safe:

- Django ignores `X-Forwarded-For` for booking rate limiting.
- `BOOKING_TRUST_X_FORWARDED_FOR=false`.
- `SECURE_PROXY_SSL_HEADER` is disabled.

If running behind a trusted reverse proxy:

- Proxy must set `X-Forwarded-Proto=https` for HTTPS requests.
- Proxy must overwrite any incoming client-supplied `X-Forwarded-Proto`.
- Enable `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true`.

If enabling client IP extraction from `X-Forwarded-For`:

- Proxy must strip all incoming client-supplied `X-Forwarded-For`.
- Proxy must set its own single trusted chain.
- Enable `BOOKING_TRUST_X_FORWARDED_FOR=true`.
- Set `BOOKING_TRUSTED_PROXY_CONFIGURED=true` only after review.
- Rate limiting depends on this being correct.

## Known Gaps

- No deployment has been performed.
- No production database, cache, TLS, DNS, or proxy exists in this repo.
- No patient portal, uploads, WhatsApp sending/webhooks, payments, medical records, or medical automation are implemented.
- No real patient data should be present.
- No structured JSON logging dependency is active.
- No Sentry/error reporting SDK is active.
- No static hosting choice has been finalized.
- No private media implementation exists.
- No legal/privacy signoff is recorded.
- No vulnerability scanning tool is configured.
- No load test results exist.

## Recommended Next Batch

Before patient portal, uploads, WhatsApp, or records, the next batch should validate deployment infrastructure assumptions in a staging-like environment:

- Exercise production settings with placeholder staging secrets.
- Provision PostgreSQL and Redis in staging.
- Run migrations and seed commands in staging.
- Verify reverse proxy headers.
- Verify `/health/` and `/health/ready/` behavior through the proxy.
- Add vulnerability/dependency scanning.
- Draft incident response and backup restore runbooks.
