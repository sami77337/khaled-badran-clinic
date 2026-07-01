# Staging Environment Contract

Batch 11 operational contract for restricted production-like staging.

This document names required environment variables and validation expectations.
It does not provide secret values, credentials, real hostnames, or patient data.
It does not deploy or provision infrastructure.

## Contract Summary

Staging must be production-like and restricted. It should use
`config.settings.prod` unless a future reviewed `config.settings.staging`
wrapper is added. Any future wrapper must inherit production-safe defaults and
must not silently weaken security.

Staging is not production and is not public launch approval. It is a validation
environment for synthetic data only.

## Required Core Variables

Set these outside Git:

| Variable | Required staging expectation |
| --- | --- |
| `DJANGO_SETTINGS_MODULE` | Must be `config.settings.prod` unless a reviewed production-safe staging wrapper exists. |
| `DJANGO_SECRET_KEY` | Must be a generated staging-only secret stored outside Git. |
| `DJANGO_DEBUG` | Must be `false`. |
| `DJANGO_PRODUCTION` | May be `true` for explicit production-mode checks; production settings already set `PRODUCTION=True`. |
| `DJANGO_ALLOWED_HOSTS` | Must list exact restricted staging hostnames only. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Must list exact HTTPS staging origins. |
| `DATABASE_URL` | Must point to staging PostgreSQL. |
| `DATABASE_CONN_MAX_AGE` | Must be chosen for the hosting/database limits. |
| `DATABASE_CONN_HEALTH_CHECKS` | Should be `true` for production-like validation. |
| `DATABASE_SSL_REQUIRE` | Must match the provider requirement; production-like default should be `true` unless the local-only harness explicitly documents otherwise. |
| `CACHE_URL` | Must point to Redis or another reviewed shared cache. |
| `DJANGO_CACHE_KEY_PREFIX` | Must be unique for staging if any cache service is shared. |
| `DJANGO_SECURE_SSL_REDIRECT` | Should be `true` after HTTPS/proxy path is verified. |
| `DJANGO_SESSION_COOKIE_SECURE` | Must be effectively true under production settings. |
| `DJANGO_CSRF_COOKIE_SECURE` | Must be effectively true under production settings. |
| `DJANGO_SECURE_HSTS_SECONDS` | Must be intentionally chosen for staging; do not copy production preload assumptions blindly. |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | Enable only when staging subdomain coverage is understood. |
| `DJANGO_SECURE_HSTS_PRELOAD` | Enable only when the operator understands preload implications; staging normally should not submit preload. |
| `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED` | Enable only after reverse proxy behavior is verified. |
| `BOOKING_TRUST_X_FORWARDED_FOR` | Keep false unless trusted proxy stripping is verified. |
| `BOOKING_TRUSTED_PROXY_CONFIGURED` | Set true only after proxy stripping/setting behavior is reviewed. |
| `DJANGO_LOG_LEVEL` | Must be appropriate for staging and must not cause request-body or secret logging. |
| `MEDIA_PRIVATE_ROOT` | Future placeholder only; it does not enable uploads. |

## Forbidden Values and Placeholder Warnings

Do not use any of these in staging:

- `DJANGO_SECRET_KEY=change-me`
- `DJANGO_SECRET_KEY=django-insecure-local-dev-only`
- `DJANGO_SECRET_KEY=replace-with-generated-secret`
- Any `.env.example` placeholder as a real secret.
- `DJANGO_DEBUG=true`
- `DJANGO_ALLOWED_HOSTS=*`
- Empty `DJANGO_ALLOWED_HOSTS`
- Empty `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL` pointing to SQLite.
- Empty `DATABASE_URL`.
- Empty `CACHE_URL`.
- `CACHE_URL=locmem://...`
- Real patient names, real phone numbers, real emails, real medical notes,
  reports, images, private media, WhatsApp messages, or payment data.

Never paste actual environment values into Git, docs, pull requests, tickets,
screenshots, test output, chat logs, or incident notes.

## PostgreSQL Requirement

Staging must use PostgreSQL. SQLite is acceptable for local development and
local CI only.

Staging PostgreSQL must have:

- a staging-only database,
- a staging-only app user,
- least-privilege credentials,
- SSL behavior matched to the provider,
- migration validation,
- backup coverage,
- restore-test path,
- no real patient data.

Do not treat SQLite test success as PostgreSQL launch proof.

## Redis or Shared Cache Requirement

Staging must use Redis or another reviewed shared Django cache backend.
LocMemCache is not acceptable for production-like rate limits because each
process has a separate memory store.

Staging must validate:

- `CACHE_URL` points to the shared cache.
- `DJANGO_CACHE_KEY_PREFIX` is unique to staging if the cache is shared.
- Booking IP quotas are shared across app processes.
- Booking phone quotas are shared across app processes.
- Portal login quotas are shared across app processes.
- Registration quotas are shared across app processes.
- Appointment-link quotas are shared across app processes.
- Cache keys do not include raw phones, raw public tokens, passwords, secrets,
  or patient-identifying values.

## DEBUG=False Requirement

`DEBUG` must be false in staging. A staging environment with `DEBUG=True` is not
production-like and must not be used for launch acceptance.

Required checks:

```bash
python manage.py check
python manage.py check --deploy
python manage.py deployment_smoke --strict
python manage.py production_settings_report
python manage.py production_settings_report --json
```

The commands must not print secret values, connection strings, raw tokens,
passwords, cookies, or patient-identifying data.

## HTTPS and Proxy Variables

Use HTTPS through the staging reverse proxy or load balancer.

`DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true` may be used only when:

- the proxy sets `X-Forwarded-Proto=https` for HTTPS requests,
- the proxy overwrites any incoming client-supplied `X-Forwarded-Proto`,
- the behavior has been verified through the real staging path.

If the proxy behavior is not verified, keep the setting false and treat that as
a staging blocker until resolved.

## Exact ALLOWED_HOSTS Requirement

`DJANGO_ALLOWED_HOSTS` must contain exact staging hostnames only. Do not use a
wildcard in staging.

Examples of acceptable shape, without real values:

```text
DJANGO_ALLOWED_HOSTS=staging-host.example.test
DJANGO_ALLOWED_HOSTS=staging-host.example.test,staging-alt.example.test
```

These are shape examples only. Do not commit real staging hostnames if they are
private.

## CSRF Trusted Origin Requirement

`DJANGO_CSRF_TRUSTED_ORIGINS` must contain exact HTTPS origins matching the
staging hostnames that accept POST requests.

Shape example only:

```text
DJANGO_CSRF_TRUSTED_ORIGINS=https://staging-host.example.test
```

Do not use wildcards. Do not use HTTP origins for production-like staging.

## Secure Cookie Settings

Under `config.settings.prod`, these must be effectively true:

- `SESSION_COOKIE_SECURE`
- `CSRF_COOKIE_SECURE`

Current SameSite expectations:

- `SESSION_COOKIE_SAMESITE=Lax`
- `CSRF_COOKIE_SAMESITE=Lax`

Do not make patient portal pages cacheable. Cookie security does not replace
CSRF, ownership filtering, or no-cache behavior.

## HSTS Expectations

Production settings default to HSTS enabled. Staging HSTS choices must be
intentional because staging hostnames and subdomains may differ from production.

Validate:

- `SECURE_HSTS_SECONDS` is intentionally set.
- `SECURE_HSTS_INCLUDE_SUBDOMAINS` is enabled only when every relevant
  subdomain is HTTPS-ready.
- `SECURE_HSTS_PRELOAD` is enabled only after operational approval.

Do not submit staging hosts to preload lists through this repository.

## Booking Trusted Proxy Settings

Default:

```text
BOOKING_TRUST_X_FORWARDED_FOR=false
BOOKING_TRUSTED_PROXY_CONFIGURED=false
```

Only enable `BOOKING_TRUST_X_FORWARDED_FOR=true` when the staging reverse proxy:

- strips all incoming client-supplied `X-Forwarded-For`,
- sets its own trusted `X-Forwarded-For`,
- preserves a verified client identity chain appropriate for rate limiting.

Set `BOOKING_TRUSTED_PROXY_CONFIGURED=true` only after that review. If not
verified, leave both false and use `REMOTE_ADDR` for booking rate-limit identity.

## Email Variables Disabled Until Recovery Policy Exists

Email variables remain placeholders until email ownership, delivery,
verification, account recovery, privacy, and support processes are approved.

Placeholder variables:

- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`
- `DEFAULT_FROM_EMAIL`

Do not enable email password reset in staging or production until the recovery
policy is approved and tested.

## WhatsApp Variables Disabled Until Separate Approval

WhatsApp variables must remain unset or placeholder-only until WhatsApp sending
and webhooks are separately designed, approved, implemented, and tested.

Placeholder variables:

- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_APP_SECRET`

Do not implement WhatsApp API sending, WhatsApp webhooks, automated medical
messages, or WhatsApp media intake in Batch 11.

## MEDIA_PRIVATE_ROOT Placeholder Only

`MEDIA_PRIVATE_ROOT` is a future private-storage path placeholder. It does not
enable file uploads.

Uploads remain absent. Future uploads require:

- private storage design,
- authenticated authorization checks,
- malware/content-type controls,
- no public media URLs for medical files,
- backup/restore coverage,
- retention/deletion review,
- legal/privacy approval.

## `.env.example` Status

Batch 11 does not require `.env.example` changes at this point. The existing
template already uses placeholder-only values and documents local versus
production behavior.

If `.env.example` is modified in a future phase, tests must ensure no
real-looking secrets, credentials, or patient-identifying data are committed.

## Validation Evidence

Operators should record these outside Git if they contain environment details:

- environment name,
- app revision,
- command timestamps,
- pass/fail status,
- safe command output after secret/patient-data review,
- PostgreSQL and Redis backend categories,
- backup/restore evidence,
- proxy/TLS validation evidence,
- monitoring/alerting validation evidence.

Do not store real environment values or logs containing sensitive data in Git.

Design status: No design work performed by Codex.
