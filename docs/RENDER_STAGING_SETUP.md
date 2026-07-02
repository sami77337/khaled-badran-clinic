# Render Restricted Staging Setup

Batch 14C-PREP-01 prepares the repository for a future restricted Render
staging deployment. It does not deploy the app, create Render services, create
DNS records, create secrets, or validate real staging.

Use this document only after an operator intentionally creates staging services
in Render with synthetic data only.

## Scope

This setup targets a manual Render Python web service using:

- Django WSGI entry point: `config.wsgi:application`
- Django settings: `config.settings.prod`
- Render PostgreSQL for the staging database
- Render Key Value/Redis-compatible service for Django cache and rate limits
- WhiteNoise for collected static assets
- Gunicorn as the production WSGI process

Do not add `render.yaml` unless a later reviewed batch explicitly approves
infrastructure-as-code for this project.

## Manual Render Service Shape

Create these services manually in the Render dashboard:

- one Python web service for the Django app;
- one Render PostgreSQL database for staging;
- one Render Key Value service for staging cache/rate limits.

Place all three in the same Render region. Use internal service URLs wherever
Render provides them so traffic stays on Render's private network and latency
is minimized.

Do not use production databases, production Redis/Key Value instances,
production secrets, real patient data, real patient phone numbers, real emails,
medical notes, uploads, payment data, WhatsApp data, or copied production
backups.

## Build Command

Recommended Render build command:

```bash
python -m pip install -r requirements.txt && python manage.py collectstatic --noinput
```

Environment variables are required before this build command can complete with
`config.settings.prod`, because production settings require a generated secret,
exact allowed hosts, and a PostgreSQL `DATABASE_URL`.

## Start Command

Recommended Render start command:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --access-logfile - --error-logfile -
```

This uses the existing WSGI module, which defaults to
`DJANGO_SETTINGS_MODULE=config.settings.prod`.

## Migration Command

Migrations must be applied deliberately after the staging PostgreSQL service
exists and before accepting staging validation traffic.

If the selected Render service plan supports pre-deploy commands, use:

```bash
python manage.py migrate --noinput
```

If pre-deploy commands are unavailable, run the same command once from a trusted
Render shell before validation. Do not put migrations in the web process start
command.

## Health Check Path

Use the public liveness endpoint for the Render web service health check:

```text
/health/
```

The readiness endpoint remains:

```text
/health/ready/
```

`/health/ready/` checks database connectivity and is intended for private or
operator validation paths, not as a public diagnostic page.

## Required Environment Variables

Set these in Render outside Git. Values below are placeholders or exact
non-secret booleans only.

```text
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=<generated staging-only secret>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=<service>.onrender.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://<service>.onrender.com
DATABASE_URL=<Render PostgreSQL internal database URL>
CACHE_URL=<Render Key Value internal redis:// or rediss:// URL>
DJANGO_CACHE_KEY_PREFIX=kbc-render-staging
DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true
DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_SECURE_HSTS_SECONDS=0
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=false
DJANGO_SECURE_HSTS_PRELOAD=false
DJANGO_LOG_LEVEL=INFO
BOOKING_TRUST_X_FORWARDED_FOR=false
BOOKING_TRUSTED_PROXY_CONFIGURED=false
```

The code also supports `CSRF_TRUSTED_ORIGINS` as a fallback. Prefer
`DJANGO_CSRF_TRUSTED_ORIGINS`. If an operator must use the fallback name, set:

```text
CSRF_TRUSTED_ORIGINS=https://<service>.onrender.com
```

and leave `DJANGO_CSRF_TRUSTED_ORIGINS` unset. Do not set either CSRF variable
to a wildcard or an HTTP origin for production-like staging.

After the Render web service is created, replace `<service>.onrender.com` with
the exact generated service hostname:

```text
DJANGO_ALLOWED_HOSTS=<service>.onrender.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://<service>.onrender.com
```

If a custom staging domain is later approved, add only that exact hostname and
HTTPS origin after TLS is active and reviewed.

## HSTS Staging Position

Use this staging HSTS posture unless a custom staging domain and HSTS policy
are intentionally approved:

```text
DJANGO_SECURE_HSTS_SECONDS=0
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=false
DJANGO_SECURE_HSTS_PRELOAD=false
```

This avoids accidentally applying production HSTS preload assumptions to a
temporary Render staging hostname. Production settings still default to strict
HSTS when these environment variables are not overridden.

## PostgreSQL Notes

Use the Render PostgreSQL internal database URL where possible:

```text
DATABASE_URL=<Render PostgreSQL internal database URL>
```

Keep the database staging-only, least-privilege, and synthetic-data-only.
`DATABASE_SSL_REQUIRE` defaults to true in production settings. If Render's
selected internal URL or plan requires a different SSL setting, document that
as a staging exception before validation.

## Key Value / Redis Notes

Use the Render Key Value internal URL where possible:

```text
CACHE_URL=<Render Key Value internal redis:// or rediss:// URL>
```

Render Key Value is Redis-compatible for Django's Redis cache backend. Use a
staging-specific `DJANGO_CACHE_KEY_PREFIX` if the cache service is shared, and
validate booking and portal rate limits against the real shared cache before
claiming readiness.

## Initial Synthetic Data

Only these seed commands are allowed for staging setup:

```bash
python manage.py seed_public_content
python manage.py seed_booking_demo
```

They must be run only with synthetic/public demo data. Do not import real
patients, real appointment history, medical records, uploads, WhatsApp data, or
payment data.

## Validation Commands For The Later Staging Batch

After Render services exist and environment variables are set outside Git, run
these from a trusted Render shell or equivalent restricted operator shell:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py collectstatic --noinput
python manage.py deployment_smoke
python manage.py deployment_smoke --json
python manage.py deployment_smoke --strict
python manage.py production_settings_report
python manage.py production_settings_report --json
python manage.py check --deploy
```

Also validate through the real HTTPS browser path:

- exact `ALLOWED_HOSTS` behavior for the Render hostname;
- exact HTTPS CSRF trusted origin behavior for booking and portal POSTs;
- secure session and CSRF cookies over HTTPS;
- HTTP-to-HTTPS redirect behavior;
- reverse proxy `X-Forwarded-Proto` behavior with
  `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true`;
- whether client-supplied `X-Forwarded-For` is stripped before any future
  decision to enable `BOOKING_TRUST_X_FORWARDED_FOR=true`;
- static asset delivery from collected WhiteNoise assets.

Do not claim real staging readiness until those checks are completed and safe
evidence is recorded without secrets or patient-identifying data.
