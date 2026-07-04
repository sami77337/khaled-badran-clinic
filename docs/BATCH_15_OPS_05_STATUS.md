# Batch 15 OPS 05 Status - Advisory-Backed Dependency Scanning

## Scope

BATCH-15-OPS-05 adds repository-supported advisory-backed dependency
vulnerability scanning for Dr. Khaled Badran Clinic using `pip-audit` against
`requirements.txt`.

This batch did not add product features, routes, models, migrations,
templates, settings, dependency-file changes, lockfiles, Render changes,
secrets, patient data, uploads, medical records, payments, WhatsApp behavior,
or medical automation.

No dependency package was upgraded. No lockfile was generated. No Render
setting was changed. No patient data was used.

Production-ready status:

```text
no
```

## Branch and Base

- Working branch:
  `codex/batch-15-ops-05-dependency-scan-workflow`
- Base branch: `main`
- Verified base commit:
  `d55524bfc472872d35a9f63f97c5da9647aeccfa`
- Base subject:
  `Merge PR #30: refresh dependency scan ownership evidence`
- Repository remote:
  `sami77337/khaled-badran-clinic`
- Evidence date:
  `2026-07-04` local Asia/Amman workstation date

## Documents and Automation Inspected

- `requirements.txt`
- `.github/dependabot.yml`
- `.github/workflows/django.yml`
- `.github/workflows/staging-uptime.yml`
- `docs/BATCH_15_OPS_04_STATUS.md`
- `docs/DEPENDENCY_SECURITY_READINESS.md`
- `docs/DEPENDENCY_VULNERABILITY_SCAN_EVIDENCE.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/SECURITY_REGRESSION_CHECKLIST.md`

## Repository State Commands

| Command | Result |
| --- | --- |
| `git fetch origin main` | Exit 0. |
| `git status -sb` before branching | Clean `main` tracking `origin/main`; no local operator note file was present. |
| `git branch --show-current` before branching | `main`. |
| `git rev-parse HEAD` before branching | `d55524bfc472872d35a9f63f97c5da9647aeccfa`. |
| `git rev-parse origin/main` before branching | `d55524bfc472872d35a9f63f97c5da9647aeccfa`. |
| `git switch -c codex/batch-15-ops-05-dependency-scan-workflow origin/main` | Exit 0. |

## Safe Local Baseline Commands

The active workstation shell initially pointed Django at
`config.settings.test`, which is not present in this repository. The first
unqualified `python manage.py check` therefore exited before validation. The
safe local baseline below was rerun with explicit
`DJANGO_SETTINGS_MODULE=config.settings.dev`, matching the existing repository
local-evidence convention.

| Command | Result |
| --- | --- |
| `python --version` | Exit 0; Python 3.14.2 in the active local environment. |
| `python -m pip --version` | Exit 0; pip 26.1 in the active local environment. |
| `python manage.py check` | Exit 0 under `config.settings.dev`; no system check issues. |
| `python manage.py makemigrations --check --dry-run` | Exit 0 under `config.settings.dev`; no changes detected. |
| `python manage.py deployment_smoke` | Exit 0 under `config.settings.dev`; 16 pass, 4 expected local warnings, 0 failures, 0 strict blockers. |
| `python manage.py deployment_smoke --strict` | Exit 0 under `config.settings.dev`; 16 pass, 4 expected local warnings, 0 failures, 0 strict blockers. |
| `python manage.py production_settings_report` | Exit 0 under `config.settings.dev`; safe local report only. |
| `python manage.py project_status_report` | Exit 0 under `config.settings.dev`; safe counts only; 0 patients and 0 appointments. |
| `python manage.py test` | Exit 0 under `config.settings.dev`; 246 tests ran, OK. |
| `python -m pip check` | Exit 0; no broken requirements found. |

Expected local warnings remain:

- `DEBUG=True`
- SQLite instead of PostgreSQL
- LocMemCache instead of Redis/shared cache
- HTTPS redirect disabled locally

These warnings remain unacceptable for production launch.

## Advisory-Backed Dependency Scan

Scanner used:

```text
pip-audit
```

Manifest scanned:

```text
requirements.txt
```

Local scanner version:

```text
pip-audit 2.10.1
```

Local scan command:

```bash
pip-audit -r requirements.txt --progress-spinner off
```

Local scan result:

```text
No known vulnerabilities found
```

Interpretation:

- The scan completed successfully with exit 0.
- The result means no known advisories were returned by `pip-audit` for
  `requirements.txt` at scan time.
- The result is not a guarantee that the application or dependency set is
  vulnerability-free.
- No dependency packages were upgraded.
- No lockfile was generated.

## CI Workflow Added

Workflow:

- `.github/workflows/dependency-audit.yml`

Behavior:

- runs on pull requests;
- runs through manual `workflow_dispatch`;
- runs weekly on a low-frequency schedule;
- uses read-only repository contents permission;
- uses official GitHub checkout and Python setup actions;
- installs `pip-audit` as a CI tooling dependency only;
- does not modify `requirements.txt`;
- does not upgrade project dependencies;
- does not generate or commit a lockfile;
- runs `pip-audit -r requirements.txt --progress-spinner off`;
- fails on real vulnerabilities or scanner failure;
- prints only scanner output;
- does not use secrets, Render access, external app endpoints, response
  bodies, or patient data.

## Conclusions

Dependency inventory baseline:

```text
documented
```

Local dependency consistency:

```text
passed
```

Advisory-backed vulnerability scan:

```text
passed at scan time; no known advisories returned
```

Repository-supported scan workflow:

```text
added
```

Response ownership:

```text
role model documented; named human owner still blocked
```

Production-ready:

```text
no
```

## Remaining Blockers

- A named human dependency response owner and backup owner still need approval
  and repository documentation.
- GitHub vulnerability and Dependabot alerts still need an owner decision if
  they are not enabled.
- A lockfile/hash workflow decision remains open.
- A full monitoring provider remains incomplete.
- Alert routing remains incomplete.
- Privacy-safe error reporting remains incomplete.
- A Render managed PostgreSQL restore drill remains incomplete.
- Legal/privacy approval remains incomplete.
- Load/concurrency validation remains incomplete.
- Production hosting, DNS, custom domain, and TLS remain incomplete.
- Production-ready remains no.

## Secret and Data Handling

No secrets, tokens, connection strings, private keys, patient names, emails,
phone numbers, appointment details, medical data, database dumps, logs, or
response bodies were recorded.

No active Render staging or production resource was accessed or changed. No
GitHub repository security settings were changed. No dependency files or
lockfiles were changed.
