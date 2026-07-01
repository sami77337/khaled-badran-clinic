# Dependency Security Readiness

Batch 11 dependency and supply-chain readiness for Dr. Khaled Badran Clinic.

This document does not add paid services, credentials, or auto-merge behavior.

## Current Dependency Management

Python runtime dependencies are declared in:

- `requirements.txt`

Current runtime dependencies:

- Django
- dj-database-url
- python-dotenv
- psycopg binary package
- redis

CI dependencies are installed from `requirements.txt` in:

- `.github/workflows/django.yml`

GitHub Actions used by CI:

- `actions/checkout`
- `actions/setup-python`

## Current Risk Profile

Current dependency management is simple and reviewable, but launch readiness
requires vulnerability scanning and an update review process.

Risks:

- version ranges can admit newer minor/patch versions with regressions,
- unreviewed dependency updates may affect security behavior,
- no recurring vulnerability scan result is currently required before launch,
- no owner is assigned for high/critical dependency response.

## pip-audit Option

`pip-audit` is an open-source option for Python dependency vulnerability
scanning.

Possible future local/CI command:

```bash
python -m pip install pip-audit
python -m pip_audit -r requirements.txt
```

Do not add scanning credentials. If a scanner is added to CI later, keep it
bounded and ensure failures are reviewed by a maintainer.

## Safety Option

Safety is another dependency scanning option. Some Safety features may require
accounts or paid services.

If considered later:

- do not commit API keys,
- do not add paid services without owner approval,
- document the command and expected output,
- keep patient data and secrets out of scan logs.

## GitHub Dependabot

Batch 11 may use GitHub Dependabot for:

- Python package updates from `pip`,
- GitHub Actions updates.

Dependabot must:

- not include secrets,
- not enable auto-merge,
- not target broad ecosystems not used by the repository,
- keep pull request volume bounded,
- require human review and tests.

## Review Process for Vulnerability Updates

For each dependency/security update:

1. Read the advisory and affected versions.
2. Confirm whether the project uses the affected code path.
3. Review changelog and migration notes.
4. Apply the smallest safe update.
5. Run:
   - `python manage.py makemigrations --check --dry-run`
   - `python manage.py check`
   - `python manage.py deployment_smoke`
   - `python manage.py project_status_report`
   - `python manage.py test`
6. For staging/production-like updates, run:
   - `python manage.py check --deploy`
   - `python manage.py deployment_smoke --strict`
   - `python manage.py production_settings_report`
7. Confirm no prohibited features or route changes were introduced.
8. Do not auto-merge.

## High/Critical Vulnerability Response

For high or critical vulnerabilities:

- assign an owner,
- determine exposure,
- prioritize patch or mitigation,
- review whether secrets or patient data could be affected,
- run the security regression checklist,
- validate staging before production promotion,
- record the decision and evidence outside Git if it contains sensitive data.

If active exploitation is suspected, follow `docs/INCIDENT_RESPONSE_RUNBOOK.md`.

## Pinned and Unpinned Dependency Risk

Current requirements use bounded ranges rather than exact pins.

Benefits:

- easier patch adoption,
- less manual churn for minor compatible updates.

Risks:

- builds can change over time,
- a new compatible release can introduce behavior changes,
- reproducibility is weaker than lockfile-based workflows.

Before launch, decide whether to:

- keep bounded ranges with Dependabot and CI,
- add a generated lockfile,
- use hashes,
- use provider-specific build caching.

Do not add broad lockfile or packaging changes without a focused batch.

## Current Batch 11 Status

Batch 11 documents dependency readiness and adds a bounded Dependabot config for
Python and GitHub Actions.

Dependency security readiness remains partial until vulnerability scanning is
run and a response owner/process is approved.

Design status: No design work performed by Codex.
