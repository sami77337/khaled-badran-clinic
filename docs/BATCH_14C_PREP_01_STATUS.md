# Batch 14C-PREP-01 Status - Render Restricted Staging Prerequisites

## Scope

Batch 14C-PREP-01 prepared the repository for a future restricted Render
staging deployment.

This was a narrow deployment-readiness prep batch. It did not deploy the app,
create Render services, create DNS/TLS, add `render.yaml`, add product
features, change booking behavior, change patient portal behavior, use secrets,
or use real patient data.

## Branch and Base

- Working branch:
  `codex/batch-14c-prep-01-render-staging-prereqs`
- Base branch: `main`
- Verified base HEAD: `75c3e6eabba8147b9296cff8cff4a6fea30de1c9`
- Verified base short HEAD: `75c3e6e`
- Verified base subject:
  `BATCH-14B-FIX-01: fix PostgreSQL locking validation blocker (#22)`

The preserved local branch `feat/security-operations-release-evidence` was not
used, modified, rebased, merged, deleted, pushed, or included.

## Files Changed

Runtime/settings:

- `requirements.txt`
- `config/settings/base.py`

Documentation:

- `docs/BATCH_14C_PREP_01_STATUS.md`
- `docs/RENDER_STAGING_SETUP.md`
- `docs/STAGING_ENVIRONMENT_CONTRACT.md`
- `docs/NEXT_BATCH.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`

No models, migrations, templates, CSS, JavaScript, Docker files, CI files,
dashboard implementation, booking behavior, patient portal behavior, secrets,
committed environment files, or real patient data were changed.

## Runtime Prep Summary

- Added `gunicorn>=23.0,<24.0` for the Render Python web service WSGI process.
- Added `whitenoise>=6.8,<7.0` for static asset serving.
- Added `whitenoise.middleware.WhiteNoiseMiddleware` immediately after
  `django.middleware.security.SecurityMiddleware`.
- Added Django 5.x `STORAGES` configuration using
  `whitenoise.storage.CompressedStaticFilesStorage`.
- Kept `config.wsgi:application` as the WSGI app entry point.
- Kept production security defaults in `config.settings.prod`; staging-specific
  HSTS and proxy behavior are environment-driven.

During validation, an initial attempt with WhiteNoise manifest storage caused
local tests to fail before `collectstatic` because tests call `static()` without
a collected manifest. The storage backend was corrected to compressed
non-manifest storage so local development and tests continue to work before
`collectstatic`, while Render can still serve compressed collected static
assets.

## Render Build and Start Recommendations

Recommended Render build command:

```bash
python -m pip install -r requirements.txt && python manage.py collectstatic --noinput
```

Recommended Render start command:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --access-logfile - --error-logfile -
```

Recommended migration command:

```bash
python manage.py migrate --noinput
```

Use the migration command as a Render pre-deploy command if the selected plan
supports it, or run it once from a trusted Render shell before validation. Do
not put migrations in the web process start command.

Recommended health check path:

```text
/health/
```

## Render Environment Variables Documented

Documented in `docs/RENDER_STAGING_SETUP.md` and
`docs/STAGING_ENVIRONMENT_CONTRACT.md`:

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

The code also supports `CSRF_TRUSTED_ORIGINS` as a fallback. Prefer:

```text
DJANGO_CSRF_TRUSTED_ORIGINS=https://<service>.onrender.com
```

If an operator must use the fallback name, set:

```text
CSRF_TRUSTED_ORIGINS=https://<service>.onrender.com
```

After Render service creation, the operator must insert the exact service URL:

```text
DJANGO_ALLOWED_HOSTS=<service>.onrender.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://<service>.onrender.com
```

Render PostgreSQL and Render Key Value/Redis-compatible services should be in
the same region as the web service and use internal URLs where possible.

## Validation Commands Run

Preflight:

| Command | Result |
| --- | --- |
| `git status --short --branch` | Clean `main` tracking `origin/main`. |
| `git fetch origin` | Exit 0. |
| `git checkout main` | Already on `main`; up to date. |
| `git pull --ff-only origin main` | Already up to date. |
| `git log -1 --oneline` | `75c3e6e BATCH-14B-FIX-01: fix PostgreSQL locking validation blocker (#22)` |
| `git rev-parse HEAD` | `75c3e6eabba8147b9296cff8cff4a6fea30de1c9` |
| `git branch --show-current` | `main` before creating the work branch. |

Local validation:

| Command | Result |
| --- | --- |
| `python --version` | `Python 3.14.2` |
| `python -m pip install -r requirements.txt` | Exit 0; installed `gunicorn 23.0.0` and `whitenoise 6.12.0`. |
| `python manage.py check` | Exit 0; no issues. |
| `python manage.py makemigrations --check --dry-run` | Exit 0; no changes detected. |
| `python manage.py migrate --check` | Exit 0. |
| `python manage.py test` before static storage correction | Exit 1; 246 tests ran with 98 manifest-related errors. |
| `python manage.py test` after static storage correction | Exit 0; 246 tests ran, OK. |
| `python manage.py collectstatic --noinput` | Exit 0; 135 static files copied and 135 post-processed. |
| `python manage.py deployment_smoke` | Exit 0; warning-only local result, 16 pass, 4 expected local warnings. |
| `python manage.py deployment_smoke --json` | Exit 0; safe JSON, warning-only local result. |
| `python manage.py deployment_smoke --strict` | Exit 0; warning-only local result, 0 failures, 0 strict blockers. |
| `python manage.py production_settings_report` | Exit 0; safe local dev report, no sensitive values printed. |
| `python manage.py production_settings_report --json` | Exit 0; safe JSON only. |
| `python manage.py check --deploy` | Exit 0 with 6 expected local-development Django security warnings. |
| WSGI import with temporary synthetic local env values | Exit 0; `wsgi import ok`. |
| `python -c "import gunicorn; print('gunicorn import ok')"` | Exit 0. |
| `python -c "import whitenoise; print('whitenoise import ok')"` | Exit 0. |

The `check --deploy` warnings were the expected local-development warnings for
HSTS, HTTPS redirect, local placeholder-style secret key, insecure session
cookie, insecure CSRF cookie, and `DEBUG=True`. They are not acceptable for
real staging; the Render environment contract documents the required staging
values.

## Pass, Warning, Fail, Blocker Summary

Pass:

- Required local Django checks passed after the storage correction.
- Full local SQLite/LocMem suite passed: 246 tests, OK.
- `collectstatic` passed with WhiteNoise compressed static storage.
- `deployment_smoke` human, JSON, and strict modes passed with expected local
  warnings only.
- `production_settings_report` human and JSON output remained safe.
- WSGI, Gunicorn, and WhiteNoise import checks passed.

Warning:

- Local validation used `config.settings.dev`, SQLite, and LocMemCache.
- `check --deploy` still reports expected local-development warnings.
- Real Render staging service URL, PostgreSQL, Key Value/Redis, HTTPS, proxy,
  secure cookies, and CSRF origin behavior remain unvalidated.

Fail:

- The first local `python manage.py test` run failed after the initial manifest
  storage choice. The code was corrected and the full suite passed on rerun.

Blocker:

- Real restricted Render staging remains blocked until an operator creates the
  web service, PostgreSQL service, Key Value/Redis-compatible service, exact
  environment variables, and restricted HTTPS access outside this repository.

## Explicit No-Deployment Statement

Batch 14C-PREP-01 did not deploy to Render, create Render services, create
DNS/TLS, run staging commands against a real host, create external
infrastructure, or validate real staging.

## Explicit No-Real-Patient-Data Statement

No real patient names, phone numbers, emails, appointments, medical records,
reports, media, WhatsApp messages, payment data, secrets, credentials, database
URLs, cache URLs, or production values were used or committed.
