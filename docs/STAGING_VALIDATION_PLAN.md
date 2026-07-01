# Staging Validation Plan

Batch 10 staging-readiness plan for Dr. Khaled Badran Clinic.

This document defines how a future operator should validate a restricted,
production-like staging environment. It does not deploy anything, provision
infrastructure, store secrets, or authorize real patient data.

## Staging Target

Staging must be production-like but non-public or access-restricted.

Required target:

- `DJANGO_SETTINGS_MODULE=config.settings.prod`.
- PostgreSQL required through `DATABASE_URL`.
- Redis or another shared Django cache required through `CACHE_URL`.
- `DEBUG=False`.
- Production-like security settings.
- HTTPS through the staging reverse proxy.
- Reverse proxy headers reviewed before enabling Django trust settings.
- Secure session and CSRF cookies.
- Exact `DJANGO_ALLOWED_HOSTS`.
- HTTPS `DJANGO_CSRF_TRUSTED_ORIGINS`.
- No real patient data.
- Synthetic smoke data only.
- Secure admin/staff credentials generated outside Git.
- No deployment secrets, credentials, database dumps, logs, or patient data in
  Git.

No `config/settings/staging.py` is required today. If a future staging settings
wrapper is added, it must inherit production-safe defaults and must not weaken
security silently.

## Environment Variables

Set values outside Git. Do not write real values into documentation, commits,
tickets, screenshots, or chat logs.

Required:

- `DJANGO_SETTINGS_MODULE`
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL`
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
- `MEDIA_PRIVATE_ROOT`

Optional or future placeholders:

- `SENTRY_DSN` or other error-reporting DSN only after privacy scrubbing review.
- Email variables only after email ownership, delivery, and recovery policy are
  approved.
- WhatsApp variables must stay unset or placeholder-only until WhatsApp sending
  and webhooks are separately approved.

Never commit:

- `.env`,
- real `DJANGO_SECRET_KEY`,
- `DATABASE_URL`,
- `CACHE_URL`,
- passwords,
- tokens,
- credentials,
- real patient data,
- database dumps,
- private media,
- logs containing sensitive content.

## Validation Commands

Run in a trusted operator shell against staging. Use synthetic data only.

Recommended sequence:

```bash
python manage.py migrate
python manage.py check
python manage.py check --deploy
python manage.py deployment_smoke --strict
python manage.py deployment_smoke --json
python manage.py project_status_report
python manage.py project_status_report --json
python manage.py production_settings_report
python manage.py production_settings_report --json
python manage.py seed_public_content
python manage.py seed_booking_demo
python manage.py test
```

Notes:

- Run `python manage.py test` in staging only when the database is disposable or
  tests use an isolated CI clone.
- If the Django version or target supports a reviewed migration-plan check such
  as `python manage.py migrate --check`, run it before `migrate`.
- `deployment_smoke --strict` must pass before staging is considered validated.
- `deployment_smoke --json` should be archived only if it contains no sensitive
  environment or patient data.
- `project_status_report` is read-only and may be used for a safe counts-only
  route/security snapshot.
- `production_settings_report` is read-only and may be used for a safe
  booleans/counts/backend-category settings snapshot.

Optional Batch 11 operator scripts:

```bash
powershell -ExecutionPolicy Bypass -File scripts/validate_staging_env.ps1 -Strict -Json
bash scripts/validate_staging_env.sh --strict --json
```

Run these only from a trusted operator shell with staging environment variables
already set outside Git. The scripts do not deploy, commit, push, merge,
provision resources, or print secret values.

## Synthetic Data Policy

Allowed:

- `seed_public_content`,
- `seed_booking_demo`,
- synthetic admin/staff accounts,
- synthetic patients only if needed for isolated staging tests,
- synthetic appointments only if needed for isolated staging tests.

Not allowed:

- real patient names,
- real patient phone numbers,
- real patient emails,
- medical notes,
- diagnoses,
- reports,
- images,
- videos,
- audio,
- private media,
- WhatsApp messages,
- payment data.

## Acceptance Criteria

Staging is accepted only when:

- `DEBUG=False`.
- `config.settings.prod` is active.
- PostgreSQL is active, not SQLite.
- Redis/shared cache is active, not LocMemCache.
- HTTPS is active through the proxy.
- Secure cookies are active.
- CSRF trusted origins match HTTPS staging origins.
- `check --deploy` is reviewed and any warnings are understood.
- `deployment_smoke --strict` exits successfully.
- `deployment_smoke --json` contains safe keys only and no secrets/patient data.
- Migrations are applied.
- Public pages render.
- Public booking renders and remains login-free.
- Public success remains UUID-token based.
- Numeric public success URLs return 404.
- Staff appointment pages require authenticated staff.
- Patient portal pages require login where expected and are no-cache.
- Account recovery remains GET-only/static.
- Prohibited upload, medical-record, WhatsApp API/webhook, and payment routes
  return 404.
- Seed commands create no patients or appointments.
- Logs do not include secrets, raw request bodies, passwords, tokens, patient
  medical content, or raw connection strings.

## Rollback Plan

If staging validation fails:

1. Stop further promotion.
2. Record the failing command, exact timestamp, application revision, and
   environment name.
3. Preserve logs outside Git with secrets and patient data removed.
4. Identify whether failure is code, migration, environment, database, cache,
   proxy, static, or credential configuration.
5. Roll back code to the last known good staging revision if the failure is
   release-related and rollback is safer than a forward fix.
6. If migrations ran, review whether schema rollback, database restore, or
   forward fix is safer.
7. Restore from a synthetic staging backup only if needed.
8. Re-run `check`, `check --deploy`, and `deployment_smoke --strict` after
   rollback or fix.
9. Do not promote until acceptance criteria pass.

## Real Patient Data Prohibition

Do not test the following with real patient data:

- public booking submissions,
- portal registration,
- portal login,
- appointment linking,
- account recovery,
- password change,
- staff appointment list/detail,
- logs,
- error reporting,
- backups,
- restore drills,
- load tests,
- screenshots,
- smoke output,
- seed commands.

Use synthetic records only, and keep synthetic identifiers obviously fake.

## Redis and Shared Cache Expectations

Staging must use Redis or an equivalent shared Django cache.

Validate:

- `CACHE_URL` points to staging Redis/shared cache.
- `DJANGO_CACHE_KEY_PREFIX` is unique to staging.
- LocMemCache is not active.
- Public booking IP quota is shared across app processes.
- Public booking phone quota is shared across app processes.
- Portal login, registration, and appointment-link quotas are shared across app
  processes.
- Raw phone numbers and raw public tokens do not appear in cache keys.
- Cache outage behavior is understood and documented.

## PostgreSQL Expectations

Staging must use PostgreSQL.

Validate:

- `DATABASE_URL` points to staging PostgreSQL.
- App user is least privilege.
- SSL requirement matches provider requirements.
- Migrations apply cleanly.
- Active appointment uniqueness constraints exist.
- Duplicate public booking submissions cannot create two active appointments for
  the same doctor/start time.
- Staff reschedule cannot move into an occupied active slot.
- SQLite-only local behavior is not treated as production concurrency proof.

## HTTPS and Reverse Proxy Checklist

Validate through the real staging proxy:

- HTTP redirects to HTTPS if the staging access model allows it.
- TLS certificate is valid for the staging host.
- `SESSION_COOKIE_SECURE=True`.
- `CSRF_COOKIE_SECURE=True`.
- `CSRF_COOKIE_SAMESITE=Lax`.
- `SESSION_COOKIE_SAMESITE=Lax`.
- `ALLOWED_HOSTS` includes only exact staging hosts.
- `CSRF_TRUSTED_ORIGINS` includes exact HTTPS staging origins.
- Proxy overwrites incoming `X-Forwarded-Proto`.
- Enable `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true` only after proxy behavior
  is verified.
- Keep `BOOKING_TRUST_X_FORWARDED_FOR=false` unless the proxy strips all
  client-supplied `X-Forwarded-For` values and sets its own trusted header.
- Set `BOOKING_TRUSTED_PROXY_CONFIGURED=true` only after that review is complete.

## Backup and Restore Validation

Use synthetic data only.

The backup/restore drill must use synthetic data only.

Before public launch:

- Take a staging PostgreSQL backup.
- Restore into an isolated restore-test database.
- Point a staging clone at the restored database.
- Run migrations if needed.
- Run `python manage.py check`.
- Run `python manage.py check --deploy`.
- Run `python manage.py deployment_smoke --strict`.
- Confirm public pages, booking route access, staff route access, and portal
  route access.
- Record restore duration and any data-loss assumptions.

Do not store backup files, restore logs with secrets, database URLs, or patient
data in Git.
