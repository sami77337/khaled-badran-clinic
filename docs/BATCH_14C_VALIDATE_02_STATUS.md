# Batch 14C-VALIDATE-02 Status - Deeper Render Staging Validation

## Scope

Batch 14C-VALIDATE-02 deepened validation evidence for the real Render
restricted staging environment after Batch 14C-VALIDATE-01 confirmed basic
public GET reachability.

This was a validation and documentation batch only. It did not add product
features, change UI design, create migrations, change deployment settings,
change service plans, add dashboard features, add WhatsApp, add uploads, add
medical records, add payments, add AI, use real patient data, submit booking
POSTs, or create appointments.

No Render environment dump, full Render log, database URL, cache URL, password,
secret key, or credential value was printed or recorded.

Production-ready status:

```text
no
```

## Branch and Base

- Working branch:
  `codex/batch-14c-validate-02-deep-render-staging-validation`
- Base branch: `main`
- Verified base commit:
  `7f400f4ea76b68b0bc97a67972c1c50536938863`
- Base subject:
  `Merge PR #24: document Render staging evidence`
- Repository remote:
  `sami77337/khaled-badran-clinic`
- Render staging URL:
  `https://khaled-badran-clinic-staging.onrender.com`
- Render Web Service ID:
  `srv-d937nq67r5hc73bnebi0`
- Validation timestamp:
  `2026-07-03 01:49:16 +03:00` Asia/Amman

The preserved local branch `feat/security-operations-release-evidence` was not
checked out, modified, rebased, merged, deleted, pushed, or used.

## Documentation Inspected

This batch read the required staging and release documents before validation:

- `docs/BATCH_14C_VALIDATE_01_STATUS.md`
- `docs/RENDER_STAGING_SETUP.md`
- `docs/STAGING_ENVIRONMENT_CONTRACT.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/NEXT_BATCH.md`
- `docs/RESTRICTED_STAGING_VALIDATION_EVIDENCE.md`
- `docs/POSTGRESQL_REDIS_VALIDATION_EVIDENCE.md`
- `docs/LOCAL_DOCKER_POSTGRES_REDIS_VALIDATION_EVIDENCE.md`
- `docs/BATCH_14C_PREP_01_STATUS.md`

## Repository State Commands

| Command | Result |
| --- | --- |
| `git fetch origin main` | Exit 0. |
| `git status -sb` before branching | Clean `main` tracking `origin/main`. |
| `git branch --show-current` before branching | `main` |
| `git rev-parse HEAD` before branching | `7f400f4ea76b68b0bc97a67972c1c50536938863` |
| `git rev-parse origin/main` | `7f400f4ea76b68b0bc97a67972c1c50536938863` |
| `git merge-base --is-ancestor 7f400f4 origin/main` | Exit 0; `origin/main` contains `7f400f4`. |
| `git checkout -b codex/batch-14c-validate-02-deep-render-staging-validation origin/main` | Exit 0. |

## Local Baseline Commands

These commands ran locally without staging or production secrets:

| Command | Result |
| --- | --- |
| `python --version` | `Python 3.14.2` |
| `python manage.py check` | Exit 0; no system check issues. |
| `python manage.py test` | Exit 0; 246 tests ran, OK. |
| `python manage.py deployment_smoke` | Exit 0; warning-only local result: 16 pass, 4 expected local warnings, 0 failures, 0 strict blockers. |
| `python manage.py production_settings_report` | Exit 0; safe local report only; development settings, SQLite, LocMemCache, and local HTTPS/security warnings were reported without sensitive values. |
| `python manage.py project_status_report` | Exit 0; safe counts and feature flags only; 0 patients and 0 appointments in the local report. |

The four smoke warnings were expected for `config.settings.dev`:

- `DEBUG=True`;
- SQLite instead of PostgreSQL;
- LocMemCache instead of Redis/shared cache;
- HTTPS redirect disabled locally.

These local warnings are not acceptable production settings. No real Render
secrets were copied into the local workspace.

## External Public Staging GET Evidence

Only safe public GET and HEAD requests were used.

Required HTTPS GET checks:

| Check | HTTP status | Final URL | Response time | Unexpected server-error markers |
| --- | --- | --- | --- | --- |
| `GET /health/` | 200 | `https://khaled-badran-clinic-staging.onrender.com/health/` | 383 ms | None |
| `GET /` | 200 | `https://khaled-badran-clinic-staging.onrender.com/` | 120 ms | None |
| `GET /book/` | 200 | `https://khaled-badran-clinic-staging.onrender.com/book/` | 118 ms | None |
| `GET /en/book/` | 200 | `https://khaled-badran-clinic-staging.onrender.com/en/book/` | 272 ms | None |

HTTP-to-HTTPS redirect checks used safe `HEAD` requests without following the
redirect:

| Check | HTTP status | Location |
| --- | --- | --- |
| `HEAD http://.../` | 301 | `https://khaled-badran-clinic-staging.onrender.com/` |
| `HEAD http://.../health/` | 301 | `https://khaled-badran-clinic-staging.onrender.com/health/` |
| `HEAD http://.../book/` | 301 | `https://khaled-badran-clinic-staging.onrender.com/book/` |
| `HEAD http://.../en/book/` | 301 | `https://khaled-badran-clinic-staging.onrender.com/en/book/` |

Conclusion:

```text
Restricted staging public availability: validated for bounded public GET and
HEAD evidence.
```

## Static Asset Evidence

The staging home page referenced four same-origin static assets. Each returned
HTTP 200 by safe GET:

| Asset path | HTTP status | Content type | Cache-Control |
| --- | --- | --- | --- |
| `/static/site.webmanifest` | 200 | `application/octet-stream` | `max-age=60, public` |
| `/static/img/icons/site-icon.svg` | 200 | `image/svg+xml` | `max-age=60, public` |
| `/static/css/site.css` | 200 | `text/css; charset="utf-8"` | `max-age=60, public` |
| `/static/js/site.js` | 200 | `text/javascript; charset="utf-8"` | `max-age=60, public` |

Conclusion:

```text
Static assets: validated for the basic same-origin assets referenced by the
staging home page.
```

Remaining limitation: this does not validate CDN behavior, cache invalidation,
large-asset behavior, static delivery under load, or custom-domain production
static serving.

## Security Header Evidence

Observed on the required public HTTPS responses:

| Header | Observation |
| --- | --- |
| `Strict-Transport-Security` | Absent on checked public responses. |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `same-origin` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Content-Security-Policy` | Absent on checked public responses. |
| `Set-Cookie` | Absent on `/health/`, `/`, `/book/`, and `/en/book/`. |

HSTS absence matches the documented staging posture where HSTS is intentionally
disabled unless a custom staging domain and policy are approved. Production HSTS
policy still requires separate review and validation before launch.

CSP absence is not a regression discovered by this batch, but it remains a
hardening gap to review before production launch.

## Form, CSRF, Cookie, and Cache Evidence

The Arabic and English booking entry pages returned HTTP 200 but rendered a
placeholder state:

- `booking-option` count: 0;
- `slot-button` count: 0;
- `placeholder-note` count: 1;
- forms rendered: 0.

Because no safe public slot link was exposed from `/book/` or `/en/book/`, this
batch could not reach the booking confirmation form by GET without operator
help and did not submit any POST.

Safe GET checks against anonymous portal form pages did validate CSRF token
rendering and cookie flags:

| Page | Status | Forms | CSRF inputs | Cache-Control | Cookie observation |
| --- | --- | --- | --- | --- | --- |
| `/portal/login/` | 200 | 1 POST form | 1 | `max-age=0, no-cache, no-store, must-revalidate, private` | `csrftoken` set with `Secure` and SameSite present; HttpOnly absent. |
| `/portal/register/` | 200 | 1 POST form | 1 | `max-age=0, no-cache, no-store, must-revalidate, private` | `csrftoken` set with `Secure` and SameSite present; HttpOnly absent. |
| `/en/portal/login/` | 200 | 1 POST form | 1 | `max-age=0, no-cache, no-store, must-revalidate, private` | `csrftoken` set with `Secure` and SameSite present; HttpOnly absent. |
| `/en/portal/register/` | 200 | 1 POST form | 1 | `max-age=0, no-cache, no-store, must-revalidate, private` | `csrftoken` set with `Secure` and SameSite present; HttpOnly absent. |
| `/portal/account-recovery/` | 200 | 0 | 0 | `max-age=0, no-cache, no-store, must-revalidate, private` | No cookie set. |

The CSRF cookie value was not printed. Django CSRF cookies are normally readable
by client-side code unless `CSRF_COOKIE_HTTPONLY` is intentionally enabled, so
the missing HttpOnly flag is recorded as an observation rather than a secret
exposure.

Booking success page no-cache behavior remains incomplete. A safe GET to a
random UUID-shaped success URL returned HTTP 404 and did not create data, but
that is not valid success-page evidence because no existing synthetic booking
token was available and no booking POST was submitted.

Conclusion:

```text
Browser-level HTTPS/proxy/cookie/CSRF behavior: partially validated by safe
HTTP-client GET evidence for public portal forms; incomplete for the booking
confirmation form, booking success page, and real browser execution.
```

## Browser-Level Validation

The in-app browser plugin was attempted after reading its instructions. The
browser runtime reported no available in-app browser instances:

```text
Browser is not available: iab
```

The plugin browser list was empty. No large browser dependency was installed,
and no alternate unrelated browser-control surface was used.

Conclusion:

```text
Browser-level validation: incomplete because no in-app browser instance was
available in this session.
```

## Render Runtime, Database, Cache, and Logs

No Render Shell, Render API credential, or operator-provided safe runtime
command channel was available in this workspace. The current Render setup may
also be limited by plan/operator access. This batch did not require a Render
plan upgrade and did not change service settings.

Not validated in this batch:

- safe `python manage.py check` from inside the Render runtime;
- safe `python manage.py deployment_smoke --strict` from inside the Render
  runtime;
- safe `python manage.py production_settings_report` from inside the Render
  runtime;
- direct managed PostgreSQL migration/runtime command evidence;
- direct managed Redis/shared-cache runtime command evidence;
- backup/restore;
- monitoring/alerting;
- load/concurrency;
- sanitized targeted Render log review.

Full Render logs were not fetched or recorded. No environment values were
printed.

Conclusions:

```text
Managed database runtime command evidence: still incomplete.
Managed Redis/cache runtime evidence: still incomplete.
Backup/restore: still blocked.
Monitoring/alerting: still blocked.
Load/concurrency: still blocked.
Legal/privacy: still blocked.
Production-ready: no.
```

## Evidence Summary

Validated:

- restricted staging public HTTPS availability for `/health/`, `/`, `/book/`,
  and `/en/book/`;
- safe HTTP-to-HTTPS redirect behavior by HEAD for the same public paths;
- absence of unexpected server-error markers on checked public responses;
- basic home-page static asset references and HTTP 200 delivery;
- visible security headers on public responses;
- no cookies on the checked public home/booking/liveness pages;
- anonymous portal login/register forms include CSRF inputs by GET;
- CSRF cookie on portal form pages is `Secure` with SameSite present;
- portal login/register/account-recovery pages return no-cache headers;
- local baseline checks and the full 246-test local suite still pass without
  staging secrets.

Incomplete or blocked:

- booking confirmation form CSRF/cookie behavior, because staging exposed no
  safe slot link from public GET pages;
- booking success page no-cache behavior, because no existing synthetic booking
  UUID was available and no POST was submitted;
- real browser execution, because no in-app browser was available;
- direct Render runtime management command evidence;
- direct managed PostgreSQL evidence;
- direct managed Redis/shared-cache evidence;
- sanitized targeted Render log review;
- backup/restore drill;
- monitoring and alert routing;
- load/concurrency validation;
- legal/privacy approval;
- dependency vulnerability scan evidence and response ownership;
- production launch readiness.

## Secret and Data Handling

No booking POST was submitted. No patient, appointment, medical, upload,
payment, WhatsApp, or automation data was created. No real patient data was
used.

This document intentionally avoids secret values and connection strings. It may
mention forbidden labels such as `DATABASE_URL`, `CACHE_URL`, `SECRET_KEY`,
password, and token only as categories or policy boundaries. No values for
those labels are recorded.
