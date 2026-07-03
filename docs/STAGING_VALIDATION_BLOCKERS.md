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

Batch 14B-FIX-01 fixed the local Docker PostgreSQL nullable outer-join
`select_for_update()` blocker and reran the local Docker service-backed path:

- local Docker PostgreSQL-backed booking, patient portal, and full-suite tests
  now pass;
- local Docker Redis-backed booking, patient portal, and full-suite tests now
  pass;
- combined local Docker PostgreSQL+Redis booking, patient portal, and
  full-suite tests now pass;
- combined smoke/report commands reach PostgreSQL and Redis under
  `config.settings.dev`;
- real restricted staging, HTTPS/proxy/CSRF-origin, backup/restore,
  monitoring, legal/privacy, Redis multi-process/outage, and
  load/concurrency validation remain blocked.

Batch 14C-VALIDATE-01 confirmed that the real Render restricted staging web
service is functionally reachable for bounded public GET checks:

- `/health/` returned HTTP 200;
- `/` returned HTTP 200;
- `/book/` returned HTTP 200 by GET only;
- `/en/book/` returned HTTP 200 by GET only.

This resolves the earlier "no staging host was provided" blocker for bounded
public reachability only. It does not resolve full production-like staging,
browser security behavior, managed database/cache command evidence,
backup/restore, monitoring, legal/privacy, shared-cache multi-process/outage,
or load/concurrency blockers.

Batch 14C-VALIDATE-02 deepened the safe public staging evidence:

- `/health/`, `/`, `/book/`, and `/en/book/` still returned HTTP 200 over
  HTTPS;
- safe HTTP HEAD checks redirected those public HTTP paths to HTTPS;
- four same-origin static assets referenced from the home page returned HTTP
  200;
- checked public responses exposed `X-Content-Type-Options=nosniff`,
  `Referrer-Policy=same-origin`, and
  `Cross-Origin-Opener-Policy=same-origin`;
- HSTS and CSP were absent on checked public responses;
- anonymous portal login/register pages rendered CSRF inputs and set a secure
  CSRF cookie over HTTPS;
- portal login, register, and account recovery pages returned no-cache headers.

This improves public HTTPS, static-asset, and HTTP-client CSRF/cookie evidence.
It does not resolve booking confirmation/success browser behavior, direct
Render runtime command evidence, managed database/cache command evidence,
backup/restore, monitoring, legal/privacy, shared-cache multi-process/outage,
or load/concurrency blockers.

Batch 15-OPS-01 documented more precise backup/restore and monitoring/
alerting readiness plans:

- PostgreSQL backup expectations and synthetic-only restore drill procedure are
  documented;
- Redis/shared-cache is documented as non-authoritative cache/rate-limit state,
  with outage behavior still requiring a decision and validation;
- current media/private upload backup scope is documented as not applicable
  because uploads remain absent;
- post-restore verification, rollback boundaries, owner checklist, frequency
  recommendations, and retention/deletion considerations are documented;
- uptime checks for `/health/` and `/`, private readiness monitoring, latency
  thresholds, error-rate monitoring, deploy/database/cache alerts,
  privacy-safe error reporting, alert routing, severity levels, incident
  response, and post-incident review are documented.

Batch 15-OPS-01 did not execute a restore drill, configure a backup provider,
configure uptime monitoring, configure alert routing, add error reporting,
change Render settings, or validate production readiness.

Do not claim production readiness from Batch 14, Batch 14B,
Batch 14C-VALIDATE-01/02, or Batch 15-OPS-01.

## Real Infrastructure Blockers

Partially resolved by Batch 14C-VALIDATE-02:

- a real Render staging web service exists;
- the staging application host is reachable over HTTPS;
- public liveness, home, and booking entry GET checks returned HTTP 200;
- public HTTP paths checked by HEAD redirect to HTTPS;
- basic same-origin static assets referenced from the home page return HTTP
  200;
- anonymous portal form pages expose CSRF inputs and secure CSRF cookies over
  HTTPS;
- the staging service uses the `main` branch in the Frankfurt region by known
  operator context.

Still blocked or not fully validated:

- no custom DNS or private staging hostname has been validated;
- no real browser automation was available to validate rendered browser
  behavior;
- no booking confirmation form CSRF/cookie behavior has been validated because
  the public staging booking page exposed no safe slot links during the batch;
- no booking success no-cache behavior has been validated because no existing
  synthetic booking UUID was available and no booking POST was submitted;
- no HSTS header was observed on checked public responses;
- no CSP header was observed on checked public responses;
- no reverse proxy header overwrite or client IP stripping behavior has been
  validated;
- no safe staging shell command output has been archived from the Render
  runtime;
- no full static asset strategy has been validated beyond basic home-page
  static assets returning HTTP 200;
- no readiness/liveness monitoring path has been connected to alerting.

## Staging Environment Contract Status

Batch 14 local validation proved that staging-only environment values were not
available in the local workspace. Batch 14C-VALIDATE-01 and
Batch 14C-VALIDATE-02 did not import those values locally and did not print or
document any secret values.

Operator context says the Render staging environment was configured manually
outside Git after the old exposed database connection was invalidated. The
public GET evidence proves the web service can start and answer traffic, but it
does not prove the complete environment contract.

Still required:

- safe staging runtime checks from a trusted operator shell or equivalent;
- exact host and HTTPS origin behavior validation;
- production-mode debug/security posture review;
- provider database and shared-cache behavior validation without recording
  connection strings;
- reviewed proxy, HSTS, secure-cookie, and client IP trust behavior;
- staging log review after sanitization.

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

PostgreSQL readiness remains incomplete for real staging after
Batch 14C-VALIDATE-02.

Batch 14B and Batch 14B-FIX-01 locally validated:

- local Docker PostgreSQL connection;
- local Docker PostgreSQL migration application;
- local Docker PostgreSQL migration check;
- local Docker PostgreSQL smoke/report commands.

Batch 14B discovered a PostgreSQL blocker:

- `python manage.py test apps.booking` failed with 24 errors.
- `python manage.py test apps.patients` failed with 7 errors.
- `python manage.py test` failed with 31 errors.
- Failure signature:
  `FOR UPDATE cannot be applied to the nullable side of an outer join`.

The affected behavior involves staff appointment operations and patient portal
appointment linking paths that use `select_for_update()` with related nullable
appointment data.

Batch 14B-FIX-01 fixed that local blocker:

- staff operation locking now uses `select_for_update(of=("self",))`;
- patient appointment linking now uses
  `select_for_update(of=("self", "patient"))`;
- local Docker PostgreSQL-backed `apps.booking` passed: 130 tests, OK;
- local Docker PostgreSQL-backed `apps.patients` passed: 46 tests, OK;
- local Docker PostgreSQL-backed full suite passed: 246 tests, OK.

Still not validated or still blocked:

- direct safe staging database command evidence from the real Render runtime;
- least-privilege database user;
- provider SSL requirement;
- active appointment uniqueness behavior under real PostgreSQL load;
- duplicate public booking concurrency on PostgreSQL;
- staff reschedule collision behavior on PostgreSQL after the blocker is fixed;
- connection pooling limits;
- PostgreSQL backup and restore.

## Redis / Shared Cache Blockers

Redis/shared-cache readiness remains incomplete after Batch 14C-VALIDATE-02.

Batch 14B locally validated:

- local Docker Redis service health;
- Django cache set/get/delete against Redis;
- safe smoke/report output with `cache=redis`;
- `python manage.py test apps.booking` with Redis and SQLite:
  130 tests ran, OK;
- `python manage.py test apps.patients` with Redis and SQLite:
  46 tests ran, OK.

Batch 14B-FIX-01 additionally validated:

- `python manage.py test` with Redis and SQLite:
  246 tests ran, OK.
- combined local Docker PostgreSQL+Redis `python manage.py test`:
  246 tests ran, OK.

Remaining Redis limitations:

- Multi-process quota behavior was not tested.
- Redis outage behavior was not tested.

Still not validated or still blocked:

- direct safe staging shared-cache command evidence from the real Render
  runtime;
- shared-cache authentication or TLS behavior;
- unique staging cache prefix against a real shared backend;
- public booking IP quota across processes;
- public booking phone quota across processes;
- portal login, registration, and appointment-link quotas across processes;
- Redis expiration behavior;
- Redis outage behavior;
- Redis monitoring and alerting;
- production rate-limit tuning.

## HTTPS, Proxy, and CSRF Blockers

Batch 14C-VALIDATE-02 confirmed basic HTTPS GET reachability, HTTP-to-HTTPS
HEAD redirects, public security header observations, and safe HTTP-client
CSRF/cookie evidence on anonymous portal forms. HTTPS/proxy readiness remains
incomplete because the batch did not validate:

- secure cookies in a real browser over HTTPS;
- booking confirmation form CSRF behavior over the real staging origin;
- booking success page no-cache behavior through a valid synthetic success URL;
- HSTS headers through the real staging path, because checked responses showed
  HSTS absent;
- CSP behavior, because checked responses showed CSP absent;
- exact staging `ALLOWED_HOSTS`;
- exact HTTPS `CSRF_TRUSTED_ORIGINS`;
- CSRF POST behavior from the real staging origin;
- reverse proxy overwrite of `X-Forwarded-Proto`;
- whether `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true` is safe;
- reverse proxy stripping of client-supplied `X-Forwarded-For`;
- whether `BOOKING_TRUST_X_FORWARDED_FOR=true` is safe.

Local Docker PostgreSQL/Redis validation does not reduce these browser,
proxy, and CSRF blockers. Batch 14C-VALIDATE-02 reduces them only to the extent
that safe public GET/HEAD and anonymous portal form checks passed.

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

- Backup/restore planning exists, but no synthetic PostgreSQL backup/restore
  drill evidence exists.
- No backup retention/RPO/RTO approval.
- Monitoring/alerting planning exists, but no uptime monitoring is configured.
- No alert routing is configured.
- No privacy-safe error-reporting integration is configured.
- No abuse monitoring configured for booking or portal flows.
- No dependency vulnerability scan evidence or response owner.
- No staging load test.
- No staging concurrency test.
- No complete production static serving validation beyond basic home-page
  static assets returning HTTP 200.

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

Proceed to operator-assisted real restricted staging validation with synthetic
data only. The Render staging host is now functionally reachable for public
GET checks, redirects checked HTTP paths to HTTPS, and serves basic home-page
static assets, but local Docker validation and public HTTP-client evidence are
not substitutes for full production-like staging validation.

Recommended next batches:

```text
Batch 14C-VALIDATE-03: operator-assisted Render runtime validation
Batch 15-OPS-02: synthetic restore drill and approved monitoring/alerting setup
```

Dashboard implementation should remain deferred until the staging runtime,
database/cache, browser security, backup/restore, monitoring, and
load/concurrency blockers are resolved or explicitly accepted as a documented
risk by the owner.
