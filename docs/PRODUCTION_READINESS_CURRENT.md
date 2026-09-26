# Production Readiness — Current Runtime Checkpoint

This file is the current operational checkpoint after Commercial Delivery v1.
It excludes legal/privacy review, which is tracked separately by the owner.

## Current production baseline

- Application main/deployed commercial reference before this operations batch:
  `a48bb3cb889701c0580224a232116419528eca91`.
- Render production web service: Starter, Frankfurt, one instance.
- Managed PostgreSQL: available, paid compute, Frankfurt.
- Managed Redis/Key Value: available, 256 MB, Frankfurt; used as shared cache.
- Persistent disk: 5 GB mounted at `/var/data`.
- Production startup runs migrations and `check_media_storage --write-probe`
  before Gunicorn.
- Automatic WhatsApp reminder cron is active and has recent successful runs.

## 24-hour capacity baseline

The current clinic traffic is intentionally very small. Render metrics from the
24-hour audit window showed low utilization:

- Web CPU peak remained well below one full CPU.
- Web memory remained below 200 MB.
- PostgreSQL active connections remained at 1–2.
- Redis memory remained only a few MB with at most one active connection.

These figures are a low-traffic baseline, not a load-test result.

## Runtime gates added by this operations batch

### Production-like PostgreSQL + Redis integration

GitHub Actions now runs selected concurrency and shared-cache tests against real
PostgreSQL 16 and Redis service containers instead of SQLite/LocMem only.

Coverage includes:

- patient reschedule concurrency;
- public booking vs reschedule races;
- staff reschedule race;
- overlapping WhatsApp reminder workers;
- webhook process coordination;
- public booking IP/phone rate limiting;
- hashed rate-limit identities;
- patient portal login/register/link throttling.

All data in this gate is synthetic CI data.

### External production uptime gate

A scheduled GitHub Actions workflow checks, without printing response bodies:

- `/health/`;
- `/health/ready/`;
- Arabic Home;
- English Home.

It retries transient network failures and fails on non-200 results or sustained
hard latency. This provides an external signal independent of the Render runtime.

It is not a substitute for a dedicated monitoring/alert-routing provider.

### Bounded production read-only load baseline

A deliberately small production baseline is defined for the clinic's current low-volume operating stage:

- 48 GET requests total;
- maximum 4 concurrent requests;
- public/health/booking GET routes only;
- no POST requests;
- no appointments, patients, messages or medical records created;
- no private/staff pages;
- response bodies are discarded and never printed;
- pass target: zero request errors, overall p95 <= 2.5 seconds, and no single request above 5 seconds.

This is a small-clinic operating baseline, not a stress/capacity ceiling. Write-path race integrity remains tested in isolated PostgreSQL + Redis CI.

Observed run on 2026-09-26:

- 48/48 requests returned HTTP 200;
- errors: 0;
- p50: 0.295s;
- p95: 0.603s;
- maximum single request: 0.654s;
- slowest sampled route: Arabic Services at 0.654s p95/max for its six requests.

Result: **PASS** for the approved bounded small-clinic read-only baseline.

## Confirmed provider backup foundations

Current Render capabilities provide important foundations:

- paid Render Postgres supports provider-managed point-in-time recovery;
- persistent Render disks receive automatic encrypted daily snapshots;
- the application private-media roots are on the attached persistent disk.

These foundations do **not** replace a provider-level isolated restore drill. A local synthetic PostgreSQL logical backup/restore drill already passed in Batch 15 OPS 02; the remaining blocker is the real Render-managed recovery path.

## Remaining production-readiness work

### BLOCKER — Render-managed isolated restore drill

The repository already has a successful local synthetic PostgreSQL logical backup/restore drill. A real Render-managed restore/PITR test has not yet been completed against an isolated recovery database / recovery target. Do not test restoration by overwriting active
production.

The drill must validate:

- database recovery into an isolated instance;
- migration state and application smoke checks;
- protected media recovery/consistency plan;
- RPO/RTO observations;
- cleanup of the temporary recovery target.

No production patient rows, dump files, credentials, connection strings or
private media may be committed to Git.

### BLOCKER — Render application health-check path

The production service currently uses Render's default TCP health check rather
than an HTTP application-level health path.

Target configuration:

`/health/ready/`

This is a provider setting and should be changed in the Render service settings,
then verified on a deployment. The current connector cannot safely edit that
service field directly.

### BLOCKER — alert routing / incident ownership

GitHub scheduled uptime and Render platform notifications provide signals, but
a confirmed primary + backup alert route and incident ownership chain are still
required. Private contact destinations stay outside Git.

### SEPARATE PRIVACY/LEGAL TRACK — external error reporting

A privacy-safe error-reporting provider is not enabled. Provider selection,
scrubbing, retention and access rules should be finalized together with the
separate privacy/legal review before enabling production event capture.

### MANUAL DEVICE CHECK

Automated responsive/PWA gates are complete, but a short real-device check on
the doctor's iPhone/Android/desktop remains useful for installed-icon/cache and
native browser behavior.

### CREDENTIAL HYGIENE

Before broader clinic use, review active staff/admin accounts, keep least
privilege, remove obsolete access, and rotate/transfer credentials privately
where needed. Never place credentials in Git or handoff documents.

## Production-readiness decision rule

Do not label the system fully Production Ready until the restore drill,
application-level Render health check, and tested alert-routing ownership are
closed, plus the separate legal/privacy track is complete.
