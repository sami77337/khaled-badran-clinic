# Staging Validation Blockers

## Summary

Batch 14 completed local/provisional validation only. Batch 14B used the
repository-approved local Docker PostgreSQL/Redis harness now that Docker
Desktop and WSL2 are available locally.

Batch 14B improved local service evidence but did not complete staging
validation:

- local Docker PostgreSQL connectivity and migrations worked;
- local Docker PostgreSQL app tests failed;
- local Docker Redis cache reachability worked after installing existing
  declared requirements locally;
- Redis-backed booking and patient portal app tests passed on SQLite;
- combined PostgreSQL+Redis smoke/report commands passed under dev settings;
- combined PostgreSQL+Redis full-suite tests failed;
- real restricted staging, HTTPS/proxy/CSRF-origin, backup/restore,
  monitoring, legal/privacy, and load/concurrency validation remain blocked.

Do not claim production readiness from Batch 14 or Batch 14B.

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

## Local Tooling Status

Batch 14 local tooling blockers were updated by Batch 14B:

- `docker` is now available.
- `docker compose` is now available.
- Docker Desktop daemon is running on WSL2.
- The documented local PostgreSQL/Redis compose harness starts successfully.
- PostgreSQL and Redis containers become healthy and are localhost-bound.
- The active Python environment initially missed the already-declared Redis
  client dependency; `python -m pip install -r requirements.txt` installed it
  locally without changing dependency files.

Remaining local-tooling limitations:

- Direct `psql` and `redis-cli` client validation was not used; validation used
  Docker health checks and Django commands.
- The local harness is not a substitute for real restricted staging.
- The local harness does not include HTTPS, reverse proxy, DNS, process
  manager, static serving, monitoring, or backup/restore infrastructure.

## PostgreSQL Blockers

PostgreSQL readiness remains incomplete after Batch 14B.

Batch 14B locally validated:

- local Docker PostgreSQL connection;
- local Docker PostgreSQL migration application;
- local Docker PostgreSQL migration check;
- local Docker PostgreSQL smoke/report commands.

Batch 14B also discovered a PostgreSQL blocker:

- `python manage.py test apps.booking` failed with 24 errors.
- `python manage.py test apps.patients` failed with 7 errors.
- `python manage.py test` failed with 31 errors.
- Failure signature:
  `FOR UPDATE cannot be applied to the nullable side of an outer join`.

The affected behavior involves staff appointment operations and patient portal
appointment linking paths that use `select_for_update()` with related nullable
appointment data.

Still not validated or still blocked:

- passing booking/staff/patient portal tests on PostgreSQL;
- real staging PostgreSQL connection;
- staging database creation;
- least-privilege database user;
- provider SSL requirement;
- active appointment uniqueness behavior under real PostgreSQL load;
- duplicate public booking concurrency on PostgreSQL;
- staff reschedule collision behavior on PostgreSQL after the blocker is fixed;
- connection pooling limits;
- PostgreSQL backup and restore.

## Redis / Shared Cache Blockers

Redis/shared-cache readiness remains incomplete after Batch 14B.

Batch 14B locally validated:

- local Docker Redis service health;
- Django cache set/get/delete against Redis;
- safe smoke/report output with `cache=redis`;
- `python manage.py test apps.booking` with Redis and SQLite:
  130 tests ran, OK;
- `python manage.py test apps.patients` with Redis and SQLite:
  46 tests ran, OK.

Batch 14B limitations:

- `python manage.py test` with Redis and SQLite failed one core test that
  intentionally asserts local default settings use LocMemCache.
- Multi-process quota behavior was not tested.
- Redis outage behavior was not tested.

Still not validated or still blocked:

- real Redis/shared-cache staging connection;
- Redis authentication or TLS;
- unique staging cache prefix against a real shared backend;
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

Batch 14B did not provision HTTPS or a reverse proxy. Local Docker
PostgreSQL/Redis validation does not reduce these blockers.

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

Fix the local Docker PostgreSQL validation blocker, then rerun the documented
local PostgreSQL/Redis validation plan with synthetic data only.

Recommended next batch:

```text
Batch 14B-fix/evidence: fix the PostgreSQL local Docker blocker and rerun local PostgreSQL/Redis validation
```

After local Docker PostgreSQL/Redis validation passes, proceed to real
restricted staging and HTTPS/proxy/CSRF-origin validation:

```text
Batch 14C: real restricted HTTPS/proxy/staging-host validation
```

Dashboard implementation should remain deferred until the database/cache and
staging blockers are resolved or explicitly accepted as a documented risk by
the owner.
