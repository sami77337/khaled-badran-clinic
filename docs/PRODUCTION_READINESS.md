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
- `python manage.py deployment_smoke` provides safe local/staging/production-like smoke validation without printing secrets.
- Logging is configured for stdout/stderr collection without adding request body logging.
- `/health/` provides public liveness without internals.
- `/health/ready/` checks database connectivity and returns only `ok` or `unavailable`.
- Booking confirmation/success and staff appointment pages are marked no-cache.
- Patient portal foundation pages are marked no-cache.
- Optional patient portal account registration, login, appointment linking, and linked appointment viewing exist without requiring login for public booking.
- CI runs migrations check, Django check, local SQLite migration for smoke validation, `deployment_smoke`, and tests on SQLite.

Not production-ready until these are completed:

- Actual hosting platform, reverse proxy, TLS certificates, and DNS are configured.
- PostgreSQL is provisioned with least-privilege credentials.
- Redis or equivalent shared cache is provisioned.
- Backups and restore drills are tested.
- Monitoring, uptime checks, and error reporting are configured.
- Legal/privacy review is complete.
- Patient account recovery, email verification/reset policy, patient identity verification policy, and abuse monitoring are defined.
- Static serving strategy is chosen and tested.
- Private media design is completed before uploads.
- Load testing and concurrency testing are performed.
- Dependency vulnerability scanning and update policy are in place.

## Operational Documentation

Batch 7 adds operational docs for future staging and production operators:

- `docs/BACKUP_RESTORE_RUNBOOK.md` - backup, restore, retention, and restore-drill expectations.
- `docs/INCIDENT_RESPONSE_RUNBOOK.md` - incident severity, containment, recovery, communication, and review outline.
- `docs/RELEASE_CHECKLIST.md` - pre-merge, pre-deploy, migration, smoke, rollback, monitoring, and post-deploy checklist.
- `docs/LOAD_TEST_PLAN.md` - staging-only public page, booking, staff list, DB concurrency, and Redis rate-limit test plan.
- `docs/SECURITY_REGRESSION_CHECKLIST.md` - public-token, staff-only, CSRF, route, rate-limit, proxy, cookie, HSTS, secret, CI, and smoke checklist.

These documents do not prove staging or production readiness by themselves. They define how a future operator should validate it.

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

Staging should also use `config.settings.prod` unless a future reviewed `config.settings.staging` wrapper is added. Staging must be production-like but non-public or restricted, with its own generated application secret, exact allowed hosts, CSRF trusted HTTPS origins, PostgreSQL, shared Redis/cache, HTTPS, no real patient data, and secure uncommitted admin credentials.

## Deployment Smoke Command

Run:

```bash
python manage.py deployment_smoke
```

The command checks:

- Django startup and settings load.
- Database connectivity.
- Applied migration state.
- Default cache set/get/delete reachability.
- Active clinic profile, active doctor, and active visit types, reported as warnings if missing.
- Booking settings load and safe summary.
- Health and readiness endpoint import.
- Readiness database check.
- Production-mode flags and project production-readiness checks.
- Public booking safety summary, including UUID public-token success lookup and staff-only numeric operations.
- Patient portal foundation route summary without requiring patient accounts or printing patient data.

Options:

```bash
python manage.py deployment_smoke --json
python manage.py deployment_smoke --strict
```

Output rules:

- Does not print application secret values.
- Does not print database connection strings.
- Does not print cache connection strings.
- Does not print passwords, tokens, cookies, or raw environment dumps.
- Prints only safe redacted statuses, counts, booleans, and backend categories.

Local development may show warnings for DEBUG, SQLite, LocMemCache, and disabled HTTPS redirect. Those warnings mean local settings are not staging or production settings.

Strict mode is for staging/production-like validation. It exits non-zero for hard failures and staging/production blockers.

## Safe Command Sequences

Local:

```bash
python manage.py check
python manage.py test
python manage.py deployment_smoke
```

Staging:

```bash
python manage.py migrate --check
python manage.py check
python manage.py check --deploy
python manage.py deployment_smoke --strict
python manage.py seed_public_content
python manage.py seed_booking_demo
```

Run `python manage.py test` in staging only if the staging database is disposable or a separate CI clone is used.

Production:

```bash
python manage.py check --deploy
python manage.py deployment_smoke --strict
```

Production migrations require a backup and rollback plan. Do not run destructive seed commands in production unless explicitly approved.

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
- The patient portal is a foundation only: optional account, login, appointment linking, and linked appointment viewing.
- No uploads, WhatsApp sending/webhooks, payments, medical records, or medical automation are implemented.
- Patient portal production launch still needs email verification/reset policy, account recovery, patient identity verification policy, privacy/legal review, rate-limit review, and abuse monitoring.
- No real patient data should be present.
- No structured JSON logging dependency is active.
- No Sentry/error reporting SDK is active.
- No static hosting choice has been finalized.
- No private media implementation exists.
- No legal/privacy signoff is recorded.
- No vulnerability scanning tool is configured.
- No load test results exist.

## Recommended Next Batch

Before expanding patient portal capabilities, uploads, WhatsApp, payments, or records, the next batch should use the Batch 7 tooling against real staging infrastructure:

- Provision restricted staging with PostgreSQL and Redis.
- Exercise `config.settings.prod` with staging-only generated secrets.
- Run `check --deploy` and `deployment_smoke --strict` in staging.
- Verify reverse proxy headers and HTTPS behavior through the real staging proxy.
- Verify `/health/` and `/health/ready/` through the proxy.
- Complete a restore drill with synthetic data.
- Add dependency/security scanning if approved.
