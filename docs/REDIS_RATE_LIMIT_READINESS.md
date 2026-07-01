# Redis Rate-Limit Readiness

Batch 11 Redis/shared-cache readiness plan for Dr. Khaled Badran Clinic.

This document does not provision Redis, configure external services, store
credentials, or validate real staging infrastructure.

## Why LocMemCache Is Not Acceptable for Production Rate Limits

Local development uses Django LocMemCache when `CACHE_URL` is empty. That is
acceptable for local development and local SQLite CI, but it is not acceptable
for production-like rate limiting.

LocMemCache problems in production:

- each process has a separate in-memory quota store,
- multiple app processes can each allow the same client quota,
- restarts clear counters,
- horizontal scaling breaks quota consistency,
- operators cannot inspect shared rate-limit behavior centrally.

Production-like staging and production must use Redis or another reviewed
shared Django cache backend.

## Redis or Shared Cache Expectations

Staging must validate:

- `CACHE_URL` points to Redis or another reviewed shared backend.
- `DJANGO_CACHE_KEY_PREFIX` is unique to staging if the cache is shared.
- `python manage.py production_settings_report` reports `cache=redis` or JSON
  `cache_backend=redis`.
- `python manage.py deployment_smoke --strict` passes.
- Cache set/get/delete succeeds.
- Rate-limit counters are shared across app processes.
- Redis expiry behavior matches the intended windows.
- Redis authentication and TLS, if required by the provider, are configured
  outside Git.

## Cache Key Prefix Isolation

Use a unique `DJANGO_CACHE_KEY_PREFIX` per environment.

Required shape:

```text
DJANGO_CACHE_KEY_PREFIX=<environment-specific-prefix>
```

Do not share one prefix between local, staging, and production. Prefix
isolation reduces accidental cross-environment quota collisions when a shared
Redis instance is used.

## Public Booking IP Quota

Public booking POST attempts are rate limited by client IP identity.

Default local behavior:

- uses `REMOTE_ADDR`,
- ignores `X-Forwarded-For`.

Only enable `BOOKING_TRUST_X_FORWARDED_FOR=true` after a trusted reverse proxy
strips client-supplied `X-Forwarded-For` and sets its own trusted value.

Cache-key requirement:

- no raw IP address should appear in cache keys.

## Public Booking Phone Quota

Public booking valid form submissions are rate limited by normalized phone
identity.

Cache-key requirement:

- no raw phone,
- no normalized phone,
- no patient name,
- no appointment note.

The identity must be hashed before building the cache key.

## Portal Login Quota

Portal login attempts are rate limited by:

- IP identity,
- normalized phone identity when available.

Cache-key requirement:

- no raw phone,
- no normalized phone,
- no password,
- no email,
- no patient name.

Login errors must remain generic.

## Portal Registration Quota

Portal registration attempts are rate limited by:

- IP identity,
- normalized phone identity when available.

Cache-key requirement:

- no raw phone,
- no normalized phone,
- no password,
- no email,
- no patient name.

Registration errors must remain generic where account existence would otherwise
be disclosed.

## Appointment-Link Quota

Appointment linking attempts are rate limited by:

- authenticated user/IP identity,
- normalized phone identity when available.

Cache-key requirement:

- no raw `public_token`,
- no raw phone,
- no normalized phone,
- no password,
- no patient name.

Wrong token, missing token, nonexistent token, wrong phone, and already-linked
to another user cases must continue to use a generic error.

## Raw-Phone and Raw-Token Prohibition

Never store these raw values in rate-limit cache keys:

- phone input,
- normalized phone,
- appointment `public_token`,
- confirmation reference,
- password,
- email,
- patient name,
- booking note,
- database ID.

Current local tests assert hashed key behavior for booking and portal rate-limit
paths where practical.

## Redis Outage Behavior

Redis outage behavior is unresolved in this batch.

Current code uses Django cache operations for rate limits. A Redis outage may
cause cache operations to fail depending on backend configuration. Batch 11 does
not add a fallback or outage policy because silently falling back to LocMemCache
could weaken production rate limits.

Before launch, operators must decide and test:

- whether booking should fail closed, fail open with alerting, or temporarily
  degrade under explicit incident procedures,
- how portal login/register/linking should behave during cache outage,
- what alert fires when Redis is unavailable,
- who owns Redis restoration,
- whether provider Redis persistence/eviction settings are acceptable.

## Local Docker Harness

If Docker is available, `docker-compose.staging-validation.yml` provides a
local Redis service on `127.0.0.1:63790` for rehearsal. See
`docs/LOCAL_STAGING_SIMULATION.md`.

Passing local Redis checks does not replace real staging validation.

## Current Batch 11 Status

Batch 11 documents Redis expectations and adds local tests proving sensitive
booking and portal identities are not placed raw in cache keys.

Redis/shared-cache readiness remains partial until real staging validates
multi-process behavior, outage behavior, prefix isolation, and monitoring.

Design status: No design work performed by Codex.
