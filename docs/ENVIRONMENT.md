# Environment Configuration

This project uses split Django settings:

- Local development: `DJANGO_SETTINGS_MODULE=config.settings.dev`
- Staging: `DJANGO_SETTINGS_MODULE=config.settings.prod`
- Production: `DJANGO_SETTINGS_MODULE=config.settings.prod`

Local development remains simple. If `DATABASE_URL` and `CACHE_URL` are empty, the app uses SQLite and Django LocMemCache. Production must be explicit and should use PostgreSQL and a shared cache.

Do not commit `.env`, real secrets, database passwords, WhatsApp credentials, patient data, logs, or private media.

## Environment Profiles

### Local Development

Local development uses `config.settings.dev` by default through `manage.py`.

Expected local behavior:

- `DJANGO_DEBUG` defaults to true.
- Empty `DATABASE_URL` uses SQLite at `db.sqlite3`.
- Empty `CACHE_URL` uses Django LocMemCache.
- HTTPS redirect, HSTS, and secure cookies are disabled for local simplicity.
- `BOOKING_TRUST_X_FORWARDED_FOR` defaults to false.
- `python manage.py deployment_smoke` may warn about local-only SQLite, LocMemCache, DEBUG, and disabled HTTPS redirect.

Local development must not be treated as staging or production validation.

### Staging

Staging must be production-like but non-public or access-restricted.

Batch 7 does not add `config/settings/staging.py`. Staging should use `config.settings.prod` so it inherits production-safe defaults and fails closed when required settings are missing. A future `config/settings/staging.py` may be added only if it inherits production-safe defaults and does not silently weaken security.

Required staging behavior:

- Staging requires its own generated application secret through `DJANGO_SECRET_KEY`.
- Staging requires `DJANGO_ALLOWED_HOSTS`.
- Staging requires `DJANGO_CSRF_TRUSTED_ORIGINS`.
- Staging uses PostgreSQL through `DATABASE_URL`, not SQLite.
- Staging uses Redis or another shared cache through `CACHE_URL`, not LocMemCache.
- Staging should use HTTPS.
- Staging must not contain real patient data.
- Staging should use `seed_public_content` and `seed_booking_demo` only for clinic/public/booking demo setup.
- Staging admin credentials must be generated securely by the operator and must not be committed.
- Staging should run `python manage.py deployment_smoke --strict` before any patient portal, upload, WhatsApp, payment, medical-record, or medical automation work begins.

Recommended staging command sequence:

```bash
python manage.py migrate --check
python manage.py check
python manage.py check --deploy
python manage.py deployment_smoke --strict
python manage.py seed_public_content
python manage.py seed_booking_demo
```

Run `python manage.py test` in staging only when the staging database is disposable or tests use a separate CI clone.

### Production

Production uses `config.settings.prod`.

Required production behavior:

- `DJANGO_SECRET_KEY` is required and must be generated outside Git.
- `DJANGO_DEBUG=false`.
- `DJANGO_ALLOWED_HOSTS` is required and must contain exact public hostnames.
- `DJANGO_CSRF_TRUSTED_ORIGINS` is required for HTTPS origins.
- `DATABASE_URL` must point to PostgreSQL.
- `CACHE_URL` should point to Redis or another shared cache.
- HTTPS redirect, secure cookies, and HSTS are enabled by default.
- `BOOKING_TRUST_X_FORWARDED_FOR` remains false unless trusted proxy stripping is verified.
- No destructive seed commands should run unless explicitly approved.

Recommended production validation:

```bash
python manage.py check --deploy
python manage.py deployment_smoke --strict
```

Run migrations only with a backup and rollback plan.

## Core Variables

`DJANGO_SETTINGS_MODULE`

- Local: `config.settings.dev`
- Production: `config.settings.prod`

`DJANGO_SECRET_KEY`

- Required for production.
- Must be a unique generated secret stored outside Git.
- Do not use `change-me`, `django-insecure-local-dev-only`, or `.env.example` placeholders.
- Rotation policy: prepare a maintenance window, deploy the new secret to all app processes at once, restart workers, and expect existing signed sessions/password-reset links to become invalid depending on Django feature use.

`DJANGO_DEBUG`

- Local default: `true`.
- Production default in `config.settings.prod`: `false`.
- Production system checks fail if it is true.

`DJANGO_PRODUCTION`

- Optional explicit marker for production mode.
- `config.settings.prod` sets `PRODUCTION=True` regardless of this variable.
- Local development should keep it false.

`DJANGO_ALLOWED_HOSTS`

- Comma-separated hostnames.
- Production must list exact public hosts, for example `clinic.example.com,www.clinic.example.com`.
- Do not use `*` in production.

`DJANGO_CSRF_TRUSTED_ORIGINS`

- Comma-separated HTTPS origins, for example `https://clinic.example.com,https://www.clinic.example.com`.
- Required for production POST flows behind real HTTPS domains.
- Legacy `CSRF_TRUSTED_ORIGINS` is still read as a fallback, but new deployments should use `DJANGO_CSRF_TRUSTED_ORIGINS`.

## Database Variables

`DATABASE_URL`

- Local: leave empty for SQLite.
- Production: set to PostgreSQL.
- Example placeholder: `postgres://clinic_user:replace-with-db-password@db-host.example.com:5432/khaled_badran_clinic`
- SQLite is local-only and is rejected by production readiness checks.

`DATABASE_CONN_MAX_AGE`

- Local default: `0`.
- Production default: `600`.
- Use with deployment-specific connection limits and pooling.

`DATABASE_CONN_HEALTH_CHECKS`

- Local default: `false`.
- Production default: `true`.

`DATABASE_SSL_REQUIRE`

- Local default: `false`.
- Production default: `true`.
- Confirm the hosting provider's TLS requirements before launch.

## Cache Variables

`CACHE_URL`

- Local: leave empty for LocMemCache.
- Production: set to shared Redis, for example `redis://redis-host.example.com:6379/1`.
- Production rate limiting must not use LocMemCache because each process would have a separate quota store.
- Redis support uses Django's built-in `RedisCache` plus the `redis` Python client dependency in `requirements.txt`.
- Memcached is also acceptable for production if the deployment explicitly configures Django `CACHES` with a reviewed Memcached backend and driver.

`DJANGO_CACHE_KEY_PREFIX`

- Default: `kbc`.
- Set a unique prefix when sharing one Redis instance between environments.

## HTTPS and Cookie Variables

`DJANGO_SECURE_SSL_REDIRECT`

- Local: `false`.
- Production default in `config.settings.prod`: `true`.

`DJANGO_SESSION_COOKIE_SECURE`

- Local: `false`.
- Production: forced true by `config.settings.prod`.

`DJANGO_CSRF_COOKIE_SECURE`

- Local: `false`.
- Production: forced true by `config.settings.prod`.

`DJANGO_SECURE_HSTS_SECONDS`

- Local default: `0`.
- Production default: `31536000`.
- Start lower only if the deployment engineer intentionally wants a staged HSTS rollout.

`DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS`

- Production default: `true`.
- Enable only when every subdomain is ready for HTTPS.

`DJANGO_SECURE_HSTS_PRELOAD`

- Production default: `true`.
- Submit to browser preload lists only after legal/operations approval and full HTTPS coverage.

## Reverse Proxy Variables

`DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED`

- Default: `false`.
- Set true only when a trusted reverse proxy sets `X-Forwarded-Proto=https` for HTTPS requests.
- The proxy must overwrite incoming client-supplied `X-Forwarded-Proto`.

`BOOKING_TRUST_X_FORWARDED_FOR`

- Default: `false`.
- Keep false unless Django sits behind a trusted reverse proxy that strips all client-supplied `X-Forwarded-For` headers and sets its own.
- This affects public booking IP rate limiting.

`BOOKING_TRUSTED_PROXY_CONFIGURED`

- Default: `false`.
- Set true only after the proxy stripping/setting behavior above is implemented and reviewed.
- Production checks warn when `BOOKING_TRUST_X_FORWARDED_FOR=true` without this attestation.

## Logging and Monitoring Variables

`DJANGO_LOG_LEVEL`

- Default: `INFO`.
- Production should use stdout/stderr collection from the process manager or platform.
- Do not log full request bodies, booking notes, medical content, file contents, or patient medical data.

`SENTRY_DSN`

- Optional placeholder only.
- No Sentry SDK is active in this batch.
- A future deployment may add error reporting after privacy review and scrubbing policy approval.

## Email Placeholders

Email variables are placeholders only in this batch:

- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`
- `DEFAULT_FROM_EMAIL`

No patient email workflow is implemented in Batch 6.

## Storage Variables

`MEDIA_PRIVATE_ROOT`

- Local default: `media_private`.
- Uploads are not implemented yet.
- Future patient uploads must use private storage with authenticated access checks, not public `MEDIA_URL` links.

## WhatsApp Placeholders

The following variables are placeholders only. No WhatsApp sending or webhooks are implemented:

- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_APP_SECRET`
