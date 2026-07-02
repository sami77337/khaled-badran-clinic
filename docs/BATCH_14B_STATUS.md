# Batch 14B Status - Local Docker PostgreSQL and Redis Validation Evidence

## Scope

Batch 14B re-ran the repository-approved local service-backed validation path
now that Docker Desktop and WSL2 are available locally.

This is local Docker PostgreSQL/Redis validation only. It is not real
restricted staging validation, not production launch evidence, and not an
HTTPS/proxy/CSRF-origin validation.

This batch is validation evidence and documentation only.

## Branch and Base

- Working branch:
  `codex/batch-14b-local-docker-postgres-redis-evidence`
- Base branch synced before work: `main`
- Verified base HEAD: `edca384c4d5fcd5c0fcdcba304a2bf63c17cf56b`
- Verified base short HEAD: `edca384`
- Verified base subject:
  `BATCH-14: add restricted staging validation evidence (#20)`
- Pre-validation repository state: clean `main`, then a new Batch 14B branch
  was created from the verified base.

The preserved local branch `feat/security-operations-release-evidence` was not
used, modified, rebased, merged, deleted, pushed, or included.

## Environment

- OS shell: Windows PowerShell
- Python: `Python 3.14.2`
- Docker: `Docker version 29.6.1, build 8900f1d`
- Docker Compose: `Docker Compose version v5.1.4`
- Docker context: `desktop-linux`
- Docker Desktop backend: WSL2
- Docker server: `Docker Desktop`
- Docker kernel: `6.18.33.2-microsoft-standard-WSL2`
- Docker daemon status: running
- Default local Django settings: `config.settings.dev`
- Default local database before validation: SQLite
- Default local cache before validation: LocMemCache

During Redis validation, the active Python environment was missing the
repository-declared `redis` package. `python -m pip install -r requirements.txt`
was run locally and installed the already-declared dependency `redis 5.3.1`
plus its transitive package. No dependency files were changed.

## Harness Discovered

The repository-approved local harness exists and was used:

- Documentation: `docs/LOCAL_STAGING_SIMULATION.md`
- Compose file: `docker-compose.staging-validation.yml`
- PostgreSQL service: `postgres:16-alpine`
- Redis service: `redis:7-alpine`
- PostgreSQL binding: localhost-only `127.0.0.1:54329`
- Redis binding: localhost-only `127.0.0.1:63790`
- Django app container: none
- Reverse proxy: none
- Public serving: none

The documented local-only placeholder credentials and service locations were
used from a trusted local shell. No real staging or production secrets were
used, written to Git, or added to a `.env` file.

## Required Preflight

| Command | Result |
| --- | --- |
| `git status --short --branch` | Clean `main` tracking `origin/main`. |
| `git fetch origin` | Exit 0. |
| `git checkout main` | Already on `main`; up to date with `origin/main`. |
| `git pull --ff-only origin main` | Already up to date. |
| `git log -1 --oneline` | `edca384 BATCH-14: add restricted staging validation evidence (#20)` |
| `git rev-parse HEAD` | `edca384c4d5fcd5c0fcdcba304a2bf63c17cf56b` |
| `git branch --show-current` | `main` before creating the Batch 14B branch. |
| `docker --version` | `Docker version 29.6.1, build 8900f1d` |
| `docker compose version` | `Docker Compose version v5.1.4` |
| `docker info` | Exit 0; Docker Desktop daemon available on WSL2. |

Preflight conclusion: branch, expected head, clean tree, and Docker daemon
checks passed. Work continued on a new Batch 14B branch.

## Baseline Local Validation

Baseline ran before applying temporary Docker service environment variables.

| Command | Result |
| --- | --- |
| `git status --short --branch` | Clean `codex/batch-14b-local-docker-postgres-redis-evidence`. |
| `git log -1 --oneline` | `edca384 BATCH-14: add restricted staging validation evidence (#20)` |
| `git rev-parse HEAD` | `edca384c4d5fcd5c0fcdcba304a2bf63c17cf56b` |
| `python --version` | `Python 3.14.2` |
| `docker --version` | `Docker version 29.6.1, build 8900f1d` |
| `docker compose version` | `Docker Compose version v5.1.4` |
| `docker info` | Exit 0; Docker Desktop daemon available. |
| `python manage.py check` | Exit 0; no system check issues. |
| `python manage.py makemigrations --check --dry-run` | Exit 0; no changes detected. |
| `python manage.py migrate --check` | Exit 0; no unapplied migrations reported. |
| `python manage.py deployment_smoke` | Exit 0; `WARNING`, 16 pass, 4 expected local warnings, 0 failures, 0 strict blockers. |
| `python manage.py deployment_smoke --json` | Exit 0; JSON `status=warning`, database `sqlite`, cache `locmem`, 16 pass, 4 warnings. |
| `python manage.py deployment_smoke --strict` | Exit 0 under dev settings; same warning-only result. |
| `python manage.py production_settings_report` | Exit 0; dev settings, SQLite, LocMem, HTTPS/security cookies/HSTS disabled. |
| `python manage.py production_settings_report --json` | Exit 0; safe JSON only. |
| `python manage.py project_status_report` | Exit 0; 0 patients and 0 appointments. |
| `python manage.py project_status_report --json` | Exit 0; safe counts/booleans/categories only. |
| `python manage.py check --deploy` | Exit 0 with 6 expected local-development Django security warnings. |

Baseline conclusion: default local development settings remain SQLite and
LocMemCache unless temporary documented environment variables are set for local
Docker validation.

## Docker Service Start

| Command | Result |
| --- | --- |
| `docker compose -f docker-compose.staging-validation.yml up -d` | Exit 0; pulled `postgres:16-alpine` and `redis:7-alpine`, created local validation network/volumes, started both services. |
| `docker compose -f docker-compose.staging-validation.yml ps` | Initial status showed both services starting. |
| `docker compose -f docker-compose.staging-validation.yml ps` after wait | PostgreSQL and Redis both healthy, localhost-bound. |

## PostgreSQL Result

Status: failed for local Docker PostgreSQL validation.

What passed:

- `python manage.py check` with PostgreSQL: exit 0.
- `python manage.py makemigrations --check --dry-run` with PostgreSQL:
  exit 0; no changes detected.
- `python manage.py migrate` with PostgreSQL: exit 0; all migrations applied.
- `python manage.py migrate --check` with PostgreSQL: exit 0.
- `python manage.py seed_public_content` with PostgreSQL: exit 0; created
  public clinic/doctor/visit type content only.
- `python manage.py seed_booking_demo` with PostgreSQL: exit 0; created booking
  settings and schedules only; reported `patient_count=0`,
  `appointment_count=0`.
- `python manage.py deployment_smoke` with PostgreSQL and LocMem: exit 0;
  `database=postgresql`, `cache=locmem`, 16 pass, 3 expected local warnings.
- `python manage.py production_settings_report` with PostgreSQL and LocMem:
  exit 0; safe report showed `database=postgresql`, `cache=locmem`.
- `python manage.py project_status_report` with PostgreSQL: exit 0; 0 patients,
  0 appointments.

What failed:

- `python manage.py test apps.booking` with PostgreSQL:
  130 tests ran; failed with 24 errors.
- `python manage.py test apps.patients` with PostgreSQL:
  46 tests ran; failed with 7 errors.
- `python manage.py test` with PostgreSQL:
  246 tests ran; failed with 31 errors.

Failure signature:

```text
django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join
```

Observed affected paths:

- Staff appointment operations call `select_for_update()` after
  `select_related("doctor", "patient", "visit_type")` in
  `apps.booking.operations.get_staff_appointment`.
- Patient portal appointment linking calls `select_for_update()` with related
  appointment data in `apps.patients.services.link_appointment_to_user`.

Interpretation:

- Local Docker PostgreSQL connectivity, migration application, and smoke checks
  work.
- The booking/staff/portal PostgreSQL test suite does not pass.
- PostgreSQL readiness cannot be claimed.
- This is a real PostgreSQL compatibility blocker discovered by the local
  Docker harness.
- No code was changed in this evidence-only batch.

## Redis Result

Status: partially passed for local Docker Redis validation.

Initial Redis smoke attempt:

- `python manage.py check` with Redis and SQLite: exit 0.
- `python manage.py deployment_smoke` with Redis and SQLite initially failed
  with `ModuleNotFoundError` in the default cache check.
- `python -c "import redis; print(redis.__version__)"` initially failed with
  `ModuleNotFoundError`.
- `requirements.txt` already contained `redis>=5.0,<6.0`.
- `python -m pip install -r requirements.txt` installed the existing declared
  Redis dependency locally; no dependency files were edited.
- The import check then reported `5.3.1`.

Redis rerun after installing existing requirements:

- `python manage.py deployment_smoke` with Redis and SQLite: exit 0;
  `cache=redis`, default cache set/get/delete passed, 16 pass, 3 expected local
  warnings.
- `python manage.py deployment_smoke --json` with Redis and SQLite: exit 0;
  JSON `cache_backend=redis`, 16 pass, 3 warnings.
- `python manage.py production_settings_report` and `--json` with Redis and
  SQLite: exit 0; safe reports showed `cache=redis`, `database=sqlite`.
- `python manage.py test apps.booking` with Redis and SQLite:
  130 tests ran, OK.
- `python manage.py test apps.patients` with Redis and SQLite:
  46 tests ran, OK.

Full Redis-enabled suite result:

- `python manage.py test` with Redis and SQLite:
  246 tests ran; failed with 1 failure.

The single full-suite failure was
`apps.core.tests.LocalSettingsDefaultTests.test_local_settings_remain_development_oriented`,
which asserts that local default settings use LocMemCache. That assertion is
expected to be false when `CACHE_URL` is intentionally set to Redis for this
validation run.

Redis interpretation:

- Redis service reachability through Django cache passed after installing the
  repository-declared dependency locally.
- Booking and patient portal tests passed with Redis enabled.
- Existing tests cover hashed cache-key behavior for booking and portal
  rate-limit identities.
- The full suite is not clean under an overridden Redis environment because at
  least one core test intentionally verifies the default LocMem local setting.
- Multi-process shared quota behavior remains unproven.
- Redis outage behavior was not tested because no existing documented safe
  outage test was provided.

## Combined PostgreSQL and Redis Result

Status: failed because the PostgreSQL blocker remains.

What passed with both temporary Docker service variables set:

- `python manage.py check`: exit 0.
- `python manage.py makemigrations --check --dry-run`: exit 0; no changes
  detected.
- `python manage.py migrate --check`: exit 0.
- `python manage.py deployment_smoke`: exit 0; `database=postgresql`,
  `cache=redis`, 16 pass, 2 expected local warnings.
- `python manage.py deployment_smoke --json`: exit 0; safe JSON showed
  `database_engine=postgresql`, `cache_backend=redis`, 16 pass, 2 warnings.
- `python manage.py deployment_smoke --strict`: exit 0 under dev settings;
  warning-only, 0 failures, 0 strict blockers.
- `python manage.py production_settings_report`: exit 0; safe report showed
  `database=postgresql`, `cache=redis`, `production_like=False`.
- `python manage.py production_settings_report --json`: exit 0; safe JSON only.
- `python manage.py project_status_report --json`: exit 0; 0 patients and
  0 appointments.
- `python manage.py check --deploy`: exit 0 with 6 expected local-development
  Django security warnings.

What failed with both services set:

- `python manage.py test`: 246 tests ran; failed with 31 PostgreSQL errors and
  1 Redis-environment failure.

Interpretation:

- Combined local Docker service connectivity is proven for Django smoke and
  safe reports.
- Combined full-suite validation failed and cannot be used as readiness
  evidence.
- The PostgreSQL `select_for_update()` blocker must be fixed before local
  Docker PostgreSQL/Redis validation can pass.

## HTTPS, Proxy, and CSRF Status

No HTTPS, reverse proxy, DNS, TLS certificate, browser secure-cookie, or exact
staging host/CSRF-origin validation was performed in Batch 14B.

Local Docker PostgreSQL/Redis validation does not prove:

- real HTTPS redirect through a reverse proxy;
- TLS certificate validity;
- secure session or CSRF cookie behavior over HTTPS;
- real `ALLOWED_HOSTS` behavior for a staging hostname;
- exact HTTPS `CSRF_TRUSTED_ORIGINS`;
- CSRF POST behavior from a real staging origin;
- `SECURE_PROXY_SSL_HEADER` behavior through a proxy that overwrites
  `X-Forwarded-Proto`;
- trusted client IP handling through a proxy that strips client-supplied
  `X-Forwarded-For`;
- browser-level secure-cookie behavior;
- HSTS behavior through a real staging path.

`python manage.py check --deploy` continued to produce the expected local
warnings for HSTS, HTTPS redirect, local placeholder-style secret key, insecure
session cookie, insecure CSRF cookie, and `DEBUG=True`.

## Cleanup

| Command | Result |
| --- | --- |
| `docker compose -f docker-compose.staging-validation.yml down` | Exit 0; stopped and removed the local PostgreSQL/Redis validation containers and compose network. |
| `docker compose -f docker-compose.staging-validation.yml ps` | No services listed. |

Docker Desktop, WSL2, images, and unrelated Docker resources were not removed.

## Blockers Remaining

Critical blockers:

- Local Docker PostgreSQL test validation fails because PostgreSQL rejects the
  current `select_for_update()` query shape involving nullable outer joins.
- Combined PostgreSQL+Redis full-suite validation fails.
- Real restricted staging infrastructure has not been provided or validated.
- Real HTTPS/reverse proxy/exact host/CSRF-origin/browser secure-cookie
  validation remains missing.
- No backup/restore drill evidence exists.
- No monitoring/alerting setup evidence exists.
- No legal/privacy approval is recorded.
- No load/concurrency validation evidence exists.

Redis limitations:

- Redis app-specific booking and patient portal tests passed.
- Full Redis-enabled suite has an environment-assumption failure because a core
  test asserts the default local cache is LocMem.
- Multi-process shared rate-limit behavior remains unproven.
- Redis outage behavior remains untested.
- Production rate-limit tuning remains incomplete.

## Recommended Next Batch

Recommended next batch:

```text
Batch 14B-fix/evidence: fix the PostgreSQL nullable outer-join select_for_update blocker and rerun local Docker PostgreSQL/Redis validation
```

After local Docker PostgreSQL/Redis validation passes, proceed to:

```text
Batch 14C: real restricted HTTPS/proxy/staging-host validation
```

Dashboard implementation should remain deferred until the database/cache and
staging blockers are honestly resolved or explicitly accepted as deferred by
the owner.

## Explicit No-Code Statement

Batch 14B did not modify:

- application code;
- models;
- migrations;
- templates;
- CSS;
- JavaScript;
- settings;
- dependency files;
- CI;
- Docker or compose files;
- deployment files;
- secrets or credentials;
- external infrastructure.

The only environment change was a local installation of dependencies already
declared in `requirements.txt`, needed to run the existing Redis cache backend.

## Exclusions Preserved

Batch 14B did not add:

- real patient data;
- real phone numbers;
- real emails;
- real appointments;
- WhatsApp API sending;
- WhatsApp webhooks;
- uploads;
- private media handling;
- medical records;
- payments;
- deployment;
- DNS/TLS changes;
- external infrastructure;
- secrets or credentials;
- diagnosis automation;
- triage automation;
- treatment automation;
- clinical decision support;
- medical AI;
- Figma work;
- visual design.
