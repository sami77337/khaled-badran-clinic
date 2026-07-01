# HTTPS, Proxy, and CSRF Validation Evidence

## Summary

Batch 14 validated only local and code-level HTTPS/proxy/CSRF readiness
signals. No real restricted staging HTTPS endpoint, TLS certificate, DNS name,
reverse proxy, or load balancer was provided.

Result: local/provisional checks passed or produced expected local warnings;
real HTTPS/proxy validation remains blocked.

## Production Settings Report Summary

Default local command:

```powershell
python manage.py production_settings_report
```

Result:

- Exit 0.
- Settings module: `config.settings.dev`.
- Production-like: false.
- Debug: true.
- Database backend category: `sqlite`.
- Cache backend category: `locmem`.
- Allowed hosts count: 3.
- CSRF trusted origins count: 0.
- HTTPS redirect: false.
- Secure session cookie: false.
- Secure CSRF cookie: false.
- HSTS enabled: false.
- Secure proxy SSL header enabled: false.
- Booking forwarded IP trust: false.
- Booking trusted proxy configured: false.
- Output policy: safe booleans, counts, and backend categories only.

Default local JSON command:

```powershell
python manage.py production_settings_report --json
```

Result:

- Exit 0.
- Safe JSON only.
- No application secret, connection string, password, token, host value, or raw
  environment dump printed.

Interpretation:

- The report correctly identifies this as a local development environment.
- The report is useful for local evidence, but it is not staging evidence.

## Deployment Smoke Summary

Default local command:

```powershell
python manage.py deployment_smoke
```

Result:

- Exit 0.
- Result: `WARNING`.
- Summary: 16 pass, 4 warning, 0 failure, 0 strict blocker.

Local warnings:

- `DEBUG` enabled.
- SQLite active.
- LocMemCache active.
- HTTPS redirect disabled.

Strict local command:

```powershell
python manage.py deployment_smoke --strict
```

Result:

- Exit 0 under development settings.
- Same 16 pass, 4 local-development warnings, 0 failures, 0 strict blockers.

JSON local command:

```powershell
python manage.py deployment_smoke --json
```

Result:

- Exit 0.
- JSON `status=warning`.
- Summary: 16 pass, 4 warnings, 0 failures, 0 strict blockers.
- Safe categories only.

Interpretation:

- Local smoke validates safe startup, database/cache reachability, migration
  state, public content presence, booking settings, health imports, readiness
  database check, route/security summaries, and prohibited-feature absence.
- Local smoke does not validate real HTTPS, proxy headers, secure-cookie
  behavior over TLS, or real CSRF trusted origins.

## Django Deploy Check Summary

Command:

```powershell
python manage.py check --deploy
```

Result:

- Exit 0.
- 6 expected local-development warnings:
  - HSTS not set.
  - HTTPS redirect not enabled.
  - local placeholder-style secret key.
  - session cookie not secure.
  - CSRF cookie not secure.
  - `DEBUG=True`.

Interpretation:

- These warnings are expected under `config.settings.dev`.
- They confirm the local environment is not production-like.

## Synthetic Production-Settings Negative Check

A synthetic local-only `config.settings.prod` environment was attempted with:

- generated local-only application secret;
- `DJANGO_DEBUG=false`;
- localhost-only allowed host shape;
- HTTPS localhost CSRF origin shape;
- SQLite database URL;
- LocMemCache URL;
- proxy SSL header trust disabled;
- forwarded IP trust disabled.

Commands:

```powershell
python manage.py production_settings_report
python manage.py check
```

Result:

- Both commands exited 1 before successful production acceptance.
- Production checks rejected:
  - `clinic.E005`: production cache uses LocMemCache.
  - `clinic.E006`: production database uses SQLite.

Interpretation:

- The project correctly blocks unsafe production database/cache substitutes.
- This is not a real staging validation and must not be used as launch
  evidence.

## Settings and Code Inspection Summary

Inspected files:

- `config/settings/base.py`
- `config/settings/dev.py`
- `config/settings/prod.py`
- `config/settings/helpers.py`
- `apps/core/checks.py`
- `apps/core/management/commands/deployment_smoke.py`
- `apps/core/management/commands/production_settings_report.py`
- `.github/workflows/django.yml`
- `docs/STAGING_ENVIRONMENT_CONTRACT.md`
- `docs/STAGING_VALIDATION_PLAN.md`
- `docs/PRODUCTION_READINESS.md`

Observed behavior:

- `config.settings.dev` defaults to local development:
  - `DEBUG=True`.
  - SQLite if `DATABASE_URL` is empty.
  - LocMemCache if `CACHE_URL` is empty.
  - HTTPS redirect disabled.
  - secure cookies disabled.
  - HSTS disabled.
  - proxy SSL header trust disabled.
  - booking forwarded IP trust disabled.
- `config.settings.prod` requires:
  - `DJANGO_SECRET_KEY`.
  - exact `DJANGO_ALLOWED_HOSTS`.
  - `DATABASE_URL`.
  - `DJANGO_DEBUG=false` by default.
  - secure session cookie.
  - secure CSRF cookie.
  - HTTPS redirect enabled by default.
  - HSTS enabled by default.
  - `CSRF_TRUSTED_ORIGINS` from environment.
  - `SECURE_PROXY_SSL_HEADER` only when
    `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true`.
- Production checks reject:
  - `DEBUG=True`.
  - missing or placeholder secret key.
  - empty or wildcard allowed hosts.
  - empty CSRF trusted origins when allowed hosts are set.
  - LocMemCache in production.
  - SQLite in production.
  - booking forwarded IP trust without proxy attestation.

## Setting-by-Setting Evidence

| Setting or behavior | Local observed status | Real staging status |
| --- | --- | --- |
| `ALLOWED_HOSTS` | Dev report count 3. | Exact restricted staging hostnames not provided or validated. |
| `CSRF_TRUSTED_ORIGINS` | Dev report count 0. Synthetic prod shape was not accepted because DB/cache were invalid. | Exact HTTPS staging origins not provided or validated. |
| `SECURE_SSL_REDIRECT` | False under dev report. | Real HTTPS redirect through proxy not validated. |
| `SECURE_PROXY_SSL_HEADER` | False under dev report. Prod setting is opt-in by environment. | Real proxy overwrite behavior not validated. |
| `SESSION_COOKIE_SECURE` | False under dev report. Prod code sets true. | Secure cookie over real HTTPS not validated. |
| `CSRF_COOKIE_SECURE` | False under dev report. Prod code sets true. | Secure CSRF cookie over real HTTPS not validated. |
| HSTS | Disabled under dev report. Prod code enables by default. | HSTS behavior through real staging response not validated. |
| `DEBUG=False` | Dev report shows `DEBUG=True`. Synthetic prod check used `DJANGO_DEBUG=false` but was blocked by DB/cache. | Not validated in a real staging runtime. |
| Static serving boundary | Static strategy documented as unresolved for production. | Not validated with real hosting/CDN/proxy. |
| Media/private serving boundary | Uploads/private media absent. | No media serving validation applicable yet; future uploads remain gated. |
| No-cache sensitive pages | Existing tests passed for booking success/confirmation and portal pages; staff pages are documented/tested. | Browser/proxy cache behavior over real staging not validated. |

## CSRF and Route Safety Evidence

Existing tests passed for:

- CSRF enforcement on public booking POSTs.
- CSRF enforcement on portal login, registration, password change, and
  appointment linking POSTs.
- CSRF enforcement on staff operation forms through Django middleware and view
  coverage.
- POST-only portal logout.
- GET-only account recovery.
- Staff-only appointment operations.
- Patient ownership filtering.

Limit:

- These tests do not prove real staging `CSRF_TRUSTED_ORIGINS` behavior through
  a browser and HTTPS reverse proxy.

## What Requires Real Reverse Proxy / HTTPS Staging

The following remain unproven until real restricted staging exists:

- TLS certificate validity for the staging host.
- HTTP-to-HTTPS redirect behavior.
- HSTS response headers over HTTPS.
- Secure cookie flags observed by a browser over HTTPS.
- CSRF POST behavior from the exact HTTPS staging origin.
- `ALLOWED_HOSTS` behavior for accepted and rejected hosts.
- Reverse proxy overwriting `X-Forwarded-Proto`.
- Whether `DJANGO_SECURE_PROXY_SSL_HEADER_ENABLED=true` is safe.
- Reverse proxy stripping client-supplied `X-Forwarded-For`.
- Whether `BOOKING_TRUST_X_FORWARDED_FOR=true` is safe.
- Load balancer/readiness endpoint behavior.
- Static asset serving strategy.

## Blockers

- Real restricted staging infrastructure not provided/validated.
- No staging hostname.
- No DNS/TLS certificate.
- No reverse proxy or load balancer path.
- No production-like PostgreSQL/Redis services.
- No environment-variable injection for staging.
- No browser-level HTTPS validation.

## Conclusion

Local HTTPS/proxy/CSRF readiness checks behaved safely and conservatively. The
system clearly reports local insecure development settings and blocks unsafe
production-mode database/cache substitutes. However, real HTTPS/proxy/CSRF
validation remains incomplete and must be re-run in restricted staging before
any production-readiness claim.
