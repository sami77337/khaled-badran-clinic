# Local Staging Simulation

Batch 11 optional local-only service harness for Dr. Khaled Badran Clinic.

This is not deployment. It does not launch the site publicly, create external
cloud resources, create DNS records, store real credentials, or authorize real
patient data.

## Decision

A local Docker staging simulation is useful because the application expects
PostgreSQL and Redis/shared cache for production-like validation, while the
default local environment uses SQLite and LocMemCache.

The harness is intentionally service-only:

- PostgreSQL service for local migration and database behavior checks.
- Redis service for local shared-cache and rate-limit checks.
- No Django app container.
- No reverse proxy.
- No public web serving.
- No production deployment assumptions.

## Files

- `docker-compose.staging-validation.yml`

## Local-Only Bindings

The compose file binds services to localhost only:

- PostgreSQL: `127.0.0.1:54329`
- Redis: `127.0.0.1:63790`

It must not bind services to public `0.0.0.0` interfaces.

## Placeholder Credentials

The compose file uses obvious local placeholder values only:

- database: `kbc_staging_validation`
- user: `kbc_local`
- password: `local_validation_password`

These values are for local validation only. Do not reuse them for staging or
production.

## Start Services

```bash
docker compose -f docker-compose.staging-validation.yml up -d
```

Check container status:

```bash
docker compose -f docker-compose.staging-validation.yml ps
```

## Example Local Environment Shape

Set these only in a trusted local shell when running against the local Docker
services. They are not staging secrets.

PowerShell:

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"
$env:DATABASE_URL="postgres://kbc_local:local_validation_password@127.0.0.1:54329/kbc_staging_validation"
$env:CACHE_URL="redis://127.0.0.1:63790/1"
$env:DJANGO_CACHE_KEY_PREFIX="kbc-local-staging-validation"
```

Bash:

```bash
export DJANGO_SETTINGS_MODULE=config.settings.dev
export DATABASE_URL=postgres://kbc_local:local_validation_password@127.0.0.1:54329/kbc_staging_validation
export CACHE_URL=redis://127.0.0.1:63790/1
export DJANGO_CACHE_KEY_PREFIX=kbc-local-staging-validation
```

For production-like settings experiments, use generated local-only values in
the shell and do not commit them:

```text
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=<generated-local-validation-secret>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://localhost
```

Do not paste real staging or production values into docs, tests, commits, or
logs.

## Validation Commands

Local service-backed validation can use:

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py check
python manage.py deployment_smoke
python manage.py deployment_smoke --json
python manage.py project_status_report
python manage.py project_status_report --json
python manage.py test
```

When production-like environment variables are intentionally set:

```bash
python manage.py check --deploy
python manage.py deployment_smoke --strict
python manage.py production_settings_report
python manage.py production_settings_report --json
```

Do not run these against a database containing real patient data.

## Stop Services

```bash
docker compose -f docker-compose.staging-validation.yml down
```

## Cleanup Volumes

Volume cleanup deletes the local PostgreSQL and Redis validation data.

```bash
docker compose -f docker-compose.staging-validation.yml down -v
```

Use cleanup only for local synthetic validation data.

## Synthetic Data Only

Allowed:

- `seed_public_content`
- `seed_booking_demo`
- synthetic test users created by Django tests
- synthetic appointments created by tests

Forbidden:

- real patient names,
- real phone numbers,
- real email addresses,
- medical notes,
- diagnoses,
- reports,
- images,
- audio,
- video,
- WhatsApp messages,
- payment data,
- real clinic private contact data,
- real credentials.

## If Docker Is Unavailable

Do not stop Batch 11. Record the blocker in `docs/BATCH_11_PROGRESS.md` and
continue with:

- scripts,
- docs,
- static checks,
- local SQLite/LocMemCache validation,
- dry-run production-like checks,
- tests that do not require PostgreSQL or Redis.

## Not Launch Evidence

Passing this local harness does not prove staging or production readiness.

Real launch still requires restricted staging with real PostgreSQL,
Redis/shared cache, HTTPS, reverse proxy validation, backup/restore evidence,
monitoring, legal/privacy review, staff access governance, dependency scanning,
and load/concurrency validation.

Design status: No design work performed by Codex.
