# Batch 6 Status - Production Readiness and Deployment Hardening

## Scope Implemented

Batch 6 prepares the Django project for professional production deployment planning without deploying anything.

Implemented:

- Hardened split settings while preserving local development defaults.
- Added testable settings helpers for booleans, lists, integers, database config, cache config, and proxy SSL header opt-in.
- Kept SQLite as local/CI fallback only.
- Kept PostgreSQL as production database target through `DATABASE_URL`.
- Added Redis cache support through `CACHE_URL` for production shared-cache rate limiting.
- Added production-only Django system checks for unsafe production settings.
- Added environment-aware console logging configuration.
- Added safe health/readiness endpoints.
- Added no-cache behavior to booking confirmation/success and staff appointment views.
- Expanded `.env.example` with placeholder-only local and production variables.
- Expanded `.gitignore` for local databases, logs, coverage, cache artifacts, and private media.
- Added GitHub Actions CI for migrations check, Django check, and tests.
- Added operational documentation for environment, production readiness, deployment checklist, and security hardening.

## Settings Changes

Current settings layout remains:

- `config/settings/base.py`
- `config/settings/dev.py`
- `config/settings/prod.py`

Production settings behavior:

- `PRODUCTION=True`.
- `DJANGO_DEBUG` is environment-driven and defaults to false.
- `DJANGO_SECRET_KEY` is required and placeholder values are rejected.
- `DJANGO_ALLOWED_HOSTS` is required.
- `DATABASE_URL` is required.
- `DJANGO_CSRF_TRUSTED_ORIGINS` is environment-driven.
- `SECURE_SSL_REDIRECT` defaults true.
- `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` are true.
- HSTS defaults to 31536000 seconds with includeSubDomains and preload true.
- `SECURE_PROXY_SSL_HEADER` is enabled only when `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true`.
- `BOOKING_TRUST_X_FORWARDED_FOR` remains false by default.

Local development behavior:

- `manage.py` still defaults to `config.settings.dev`.
- Empty `DATABASE_URL` uses SQLite.
- Empty `CACHE_URL` uses LocMemCache.
- HTTPS/HSTS/secure-cookie settings remain off by default.

## Environment Variables Documented

Documented in `.env.example` and `docs/ENVIRONMENT.md`:

- `DJANGO_SETTINGS_MODULE`
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_PRODUCTION`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL`
- `DATABASE_CONN_MAX_AGE`
- `DATABASE_CONN_HEALTH_CHECKS`
- `DATABASE_SSL_REQUIRE`
- `CACHE_URL`
- `DJANGO_CACHE_KEY_PREFIX`
- `DJANGO_SECURE_SSL_REDIRECT`
- `DJANGO_SESSION_COOKIE_SECURE`
- `DJANGO_CSRF_COOKIE_SECURE`
- `DJANGO_SECURE_HSTS_SECONDS`
- `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS`
- `DJANGO_SECURE_HSTS_PRELOAD`
- `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED`
- `BOOKING_TRUST_X_FORWARDED_FOR`
- `BOOKING_TRUSTED_PROXY_CONFIGURED`
- `DJANGO_LOG_LEVEL`
- `SENTRY_DSN`
- email placeholders
- `MEDIA_PRIVATE_ROOT`
- WhatsApp placeholders

## Production System Checks

Added `apps/core/checks.py`.

When production mode is enabled, checks flag:

- `DEBUG=True`.
- Missing/placeholder `SECRET_KEY`.
- Empty or wildcard `ALLOWED_HOSTS`.
- Empty `CSRF_TRUSTED_ORIGINS`.
- LocMemCache in production.
- SQLite in production.
- `BOOKING_TRUST_X_FORWARDED_FOR=True` without trusted proxy attestation.

Local development does not emit these production-readiness errors.

## Database Readiness

- SQLite remains supported for local development and CI only.
- PostgreSQL is supported for production through `DATABASE_URL`.
- `dj-database-url` remains the database URL parser.
- PostgreSQL creation, migrations, backups, restore drills, migration safety, and booking concurrency notes are documented.

## Cache and Rate Limiting Readiness

- Local LocMemCache remains the default when `CACHE_URL` is empty.
- Production Redis cache is supported through `CACHE_URL`.
- Memcached is documented as a production alternative requiring deployment-specific Django `CACHES` and driver configuration.
- `redis` dependency was added to support Django's Redis cache backend.
- Production system checks reject LocMemCache in production mode.
- Documentation states that booking rate limits require a shared production cache.

## Logging and Observability

- Added console logging configuration for Django, request errors, security logs, and app loggers.
- Production logs are ready for stdout/stderr collection.
- Documentation states not to log full form payloads, booking notes by default, patient medical content, file contents, request bodies, or secrets.
- Sentry/error reporting is documented as optional and not active in this batch.

## Health Checks

- `/health/` now returns safe JSON liveness.
- `/health/ready/` returns safe readiness and checks database connectivity.
- Readiness failures return only `{"status": "unavailable"}` and HTTP 503.
- No health endpoint exposes database credentials, database engine, exception details, secrets, or settings.

## Static, Media, and Private Files

Documented:

- `STATIC_ROOT` and `collectstatic`.
- Static files should be served by reverse proxy, CDN, WhiteNoise, or another reviewed stack decision.
- Uploads are not implemented.
- Future patient uploads must use private storage, not public media URLs.
- Sensitive medical files must not be cached publicly.
- Future private media requires backup/restore policy.

## Reverse Proxy and IP Handling

Documented:

- `SECURE_PROXY_SSL_HEADER` requires a trusted proxy setting `X-Forwarded-Proto`.
- Proxy must overwrite client-supplied forwarded headers.
- `BOOKING_TRUST_X_FORWARDED_FOR=false` remains the default.
- If enabled, proxy must strip incoming `X-Forwarded-For` and set its own.
- Rate limiting depends on correct IP handling.

## CI

Added `.github/workflows/django.yml`.

CI runs:

- `python manage.py makemigrations --check --dry-run`
- `python manage.py check`
- `python manage.py test`

CI uses SQLite and requires no secrets or external services.

## Tests

Added tests for:

- Environment helper parsing.
- Database config helper.
- Cache config helper.
- Local development defaults.
- Production system checks.
- Health endpoint.
- Readiness endpoint.
- Readiness failure privacy.

Existing tests continue to cover:

- No patient portal route.
- No upload route.
- No WhatsApp webhook/API route.
- Booking token privacy.
- Staff-only booking access.
- Booking rate-limit IP behavior.

Final test count after Batch 6: 157 tests.

## Verification

Required commands run:

```bash
python manage.py makemigrations --check --dry-run
# No changes detected
```

```bash
python manage.py check
# System check identified no issues (0 silenced).
```

```bash
python manage.py check --deploy
# System check identified 6 issues (0 silenced).
```

`check --deploy` was run with local development settings (`config.settings.dev`), so the following warnings are expected and correctly show that development settings are not production settings:

- `security.W004`: `SECURE_HSTS_SECONDS` is not set.
- `security.W008`: `SECURE_SSL_REDIRECT` is not true.
- `security.W009`: local placeholder `SECRET_KEY` is not production-strength.
- `security.W012`: `SESSION_COOKIE_SECURE` is not true.
- `security.W016`: `CSRF_COOKIE_SECURE` is not true.
- `security.W018`: `DEBUG=True`.

```bash
python manage.py test
# Found 157 test(s).
# Ran 157 tests.
# OK
```

```bash
python manage.py seed_public_content
# Seeded public content: clinic=updated, doctor=updated, visit_types_created=0, visit_types_updated=9.
# No patients, appointments, WhatsApp messages, files, prices, or booking slots were created.
```

```bash
python manage.py seed_booking_demo
# Seeded public content: clinic=updated, doctor=updated, visit_types_created=0, visit_types_updated=9.
# No patients, appointments, WhatsApp messages, files, prices, or booking slots were created.
# Seeded booking demo setup: settings_created=0, settings_updated=7, schedules_created=0, schedules_updated=5.
# No patients, appointments, WhatsApp messages, uploads, secrets, or payments were created.
# Current patient_count=0, appointment_count=0.
```

```bash
python manage.py test
# Found 157 test(s).
# Ran 157 tests.
# OK
```

The test output includes expected warning logs from negative route/access tests for 404, 400, and 403 responses.

## Intentionally Out of Scope

- Deployment.
- Commits, pushes, or merges.
- Patient portal.
- File uploads.
- WhatsApp API sending.
- WhatsApp webhooks.
- Online payments.
- Medical records.
- Medical AI, diagnosis automation, triage automation, or treatment automation.
- Real secrets.
- Real patient data.

## Remaining Production Risks

- No real production infrastructure exists yet.
- No PostgreSQL/Redis staging validation has been performed.
- No reverse proxy has been configured or tested.
- No backup/restore drill has been performed.
- No monitoring or error-reporting service has been configured.
- No legal/privacy approval is recorded.
- No load testing has been performed.
- No vulnerability scanning workflow is configured.
- Private media design remains future work before uploads.

## Recommended Next Batch

Recommended Batch 7 should validate staging infrastructure assumptions before adding patient portal, uploads, WhatsApp, or records:

- Provision staging PostgreSQL and Redis.
- Exercise production settings with placeholder staging secrets.
- Verify reverse proxy headers and HTTPS behavior.
- Run migrations, checks, tests, and seed commands in staging.
- Add dependency/security scanning.
- Draft backup restore and incident response runbooks.
