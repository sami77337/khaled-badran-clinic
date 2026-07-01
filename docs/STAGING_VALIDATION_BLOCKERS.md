# Staging Validation Blockers

## Summary

Batch 14 completed local/provisional validation only. Real restricted staging
validation remains blocked because the required infrastructure, services,
environment variables, and operator context were not provided.

Do not claim production readiness from Batch 14.

## Real Infrastructure Blockers

- Real restricted staging infrastructure was not provided.
- No staging application host was provided.
- No DNS or private staging hostname was provided.
- No TLS certificate was provided.
- No reverse proxy or load balancer was provided.
- No process manager or hosting environment was provided.
- No static asset serving strategy was validated.
- No readiness/liveness monitoring path through a proxy was validated.

## Missing Environment Contract

The strict staging validation script failed because these required variables
were missing:

- `DJANGO_SETTINGS_MODULE`
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL`
- `CACHE_URL`
- `DJANGO_CACHE_KEY_PREFIX`

No values were printed, and no secret values were requested or added.

Additional staging variables from the contract still need operator review and
configuration outside Git, including:

- `DATABASE_SSL_REQUIRE`
- `DATABASE_CONN_MAX_AGE`
- `DATABASE_CONN_HEALTH_CHECKS`
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

## Local Tooling Blockers

The documented local PostgreSQL/Redis harness could not be run because:

- `docker` was unavailable in PATH.
- `docker compose` was unavailable in PATH.
- `psql` was unavailable in PATH.
- `redis-cli` was unavailable in PATH.
- Bash was unavailable in PATH, so Bash validation scripts could not be run.

PowerShell validation scripts were available. The local release script passed;
the strict staging script correctly failed on missing staging variables.

## PostgreSQL Blockers

PostgreSQL readiness remains incomplete because Batch 14 did not validate:

- real staging PostgreSQL connection;
- staging database creation;
- least-privilege database user;
- provider SSL requirement;
- `python manage.py migrate --check` against PostgreSQL;
- `python manage.py migrate` against PostgreSQL;
- active appointment uniqueness constraints on PostgreSQL;
- duplicate public booking concurrency on PostgreSQL;
- staff reschedule collision behavior on PostgreSQL;
- connection pooling limits;
- PostgreSQL backup and restore.

## Redis / Shared Cache Blockers

Redis/shared-cache readiness remains incomplete because Batch 14 did not
validate:

- real Redis/shared-cache connection;
- Redis authentication or TLS;
- unique staging cache prefix against a shared backend;
- public booking IP quota across processes;
- public booking phone quota across processes;
- portal login, registration, and appointment-link quotas across processes;
- Redis expiration behavior;
- Redis outage behavior;
- Redis monitoring and alerting;
- production rate-limit tuning.

## HTTPS, Proxy, and CSRF Blockers

HTTPS/proxy readiness remains incomplete because Batch 14 did not validate:

- TLS certificate validity;
- HTTP-to-HTTPS redirect through the real proxy;
- secure cookies in a browser over HTTPS;
- HSTS headers through the real staging path;
- exact staging `ALLOWED_HOSTS`;
- exact HTTPS `CSRF_TRUSTED_ORIGINS`;
- CSRF POST behavior from the real staging origin;
- reverse proxy overwrite of `X-Forwarded-Proto`;
- whether `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true` is safe;
- reverse proxy stripping of client-supplied `X-Forwarded-For`;
- whether `BOOKING_TRUST_X_FORWARDED_FOR=true` is safe.

## Legal and Privacy Blockers

Legal/privacy launch blockers remain:

- No formal legal/privacy review is recorded.
- Legal pages remain operational drafts.
- Retention and deletion policy is not approved.
- Patient identity verification policy is not approved.
- Secure account recovery policy is not approved.
- Email/phone ownership verification is not defined.
- Publication consent policy is not implemented or approved.
- Staff/admin access review and offboarding policy are not completed.
- Audit retention and access review policy are not completed.

## Backup, Monitoring, Load, and Security Blockers

Operational launch blockers remain:

- No synthetic PostgreSQL backup/restore drill evidence.
- No backup retention/RPO/RTO approval.
- No uptime monitoring configured.
- No alert routing configured.
- No error-reporting privacy scrubbing configured.
- No abuse monitoring configured for booking or portal flows.
- No dependency vulnerability scan evidence or response owner.
- No staging load test.
- No staging concurrency test.
- No production static serving validation.

## Product Scope Blockers and Exclusions

The following remain absent and future-gated:

- WhatsApp API sending.
- WhatsApp webhooks.
- Uploads and private media.
- Medical records.
- Payments.
- Diagnosis automation.
- Triage automation.
- Treatment automation.
- Clinical decision support.
- Medical AI.
- Authorized showcase publication workflow.
- Figma-approved visual changes for future visual work.

## Required Next Action

Provision a real restricted staging environment, or make Docker/PostgreSQL/Redis
available locally, then re-run the documented validation plan with synthetic
data only.

Recommended next batch:

```text
Batch 14B: provision and re-run real restricted staging validation
```

Dashboard implementation should remain deferred until the staging blockers are
resolved or explicitly accepted as a documented risk by the owner.
