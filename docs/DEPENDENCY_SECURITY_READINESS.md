# Dependency Security Readiness

Batch 11 dependency and supply-chain readiness for Dr. Khaled Badran Clinic.

This document does not add paid services, credentials, or auto-merge behavior.

## Current Dependency Management

Python runtime dependencies are declared in:

- `requirements.txt`

Current runtime dependencies:

- Django
- dj-database-url
- gunicorn
- python-dotenv
- psycopg binary package
- redis
- whitenoise

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

## Batch 15-OPS-04 Scan Baseline

BATCH-15-OPS-04 attempted dependency vulnerability scan evidence using only
available safe local and GitHub tooling. No dependency packages were upgraded,
no lockfile was generated, no scanner was installed, no credentials were
created, and no Render setting was changed.

Inspected dependency and automation sources:

- `requirements.txt`
- `.github/dependabot.yml`
- `.github/workflows/django.yml`
- `.github/workflows/staging-uptime.yml`

Observed manifest scope:

- `requirements.txt` is the only dependency manifest found in the repository.
- No Python lockfile is currently committed.
- No Node, Go, Rust, Ruby, PHP, or JavaScript dependency manifest was found.

Safe local baseline:

- `python -m pip check` exited successfully with no broken requirements.
- The currently installed declared runtime packages were:
  - `Django 5.2.15`
  - `dj-database-url 2.3.0`
  - `gunicorn 23.0.0`
  - `psycopg 3.3.4`
  - `python-dotenv 1.2.2`
  - `redis 5.3.1`
  - `whitenoise 6.12.0`

Vulnerability scan status:

```text
blocked/incomplete
```

Reason:

- `pip-audit` was not installed.
- `safety` was not installed.
- `osv-scanner`, `trivy`, and `grype` were not available locally.
- GitHub vulnerability alerts were disabled for the repository.
- GitHub Dependabot alerts were disabled for the repository.

This is not a clean vulnerability scan. It is evidence that the currently
available safe tooling could not produce an advisory-backed dependency
vulnerability result.

Detailed evidence is recorded in
`docs/DEPENDENCY_VULNERABILITY_SCAN_EVIDENCE.md`.

## Dependency Response Ownership

Until a named person is formally approved outside this repository, the
response model is role-based:

- Accountable owner: project owner/operator.
- Technical triage owner: repository maintainer for dependency PRs and scan
  interpretation.
- Security/privacy escalation owner: legal/privacy reviewer when an advisory
  could affect patient, appointment, portal, staff, auth, logs, or secrets.
- Deployment owner: Render/operator maintainer for staging or production
  rollout, rollback, and environment changes.

Before production launch, record a named accountable dependency response owner
and a backup owner. Do not rely on Codex as the long-term owner.

## Severity Handling

Critical:

- Treat active exploitation, remote code execution, auth bypass, data exposure,
  secret exposure, or patient-data impact as a release blocker and potential
  incident.
- Assign the accountable owner immediately.
- Follow `docs/INCIDENT_RESPONSE_RUNBOOK.md` if exploitation or data exposure
  is suspected.
- Patch, mitigate, disable the affected path, or hold the release before any
  promotion.

High:

- Assign the accountable owner the same business day.
- Confirm whether the affected package and code path are used.
- Apply the smallest safe patch or mitigation.
- Run the security regression checklist, local baseline, and staging validation
  appropriate to the changed dependency.
- Do not merge or deploy without an explicit owner decision.

Medium:

- Triage during the weekly dependency review cadence.
- Patch before the next release candidate unless the owner records a bounded
  risk acceptance.

Low:

- Triage in the normal dependency maintenance cycle.
- Patch with routine dependency updates after tests pass.

Unknown or tool-blocked:

- Do not claim "no vulnerabilities".
- Record the scanner/tooling blocker and schedule a rerun with an approved
  scanner or GitHub alert source.

## Update Cadence

Current configured cadence:

- Dependabot checks Python `pip` dependencies weekly.
- Dependabot checks GitHub Actions weekly.

Required operational cadence before launch:

- Run an advisory-backed dependency vulnerability scan weekly during active
  development.
- Run the scan after any dependency-file change.
- Run the scan before each release candidate and before production promotion.
- Review critical/high advisories immediately when surfaced by GitHub,
  Dependabot, a scanner, vendor notice, or maintainer advisory.
- Keep auto-merge disabled.

## Current Blockers

- No complete advisory-backed vulnerability scan result exists yet.
- GitHub vulnerability alerts are disabled for the repository.
- GitHub Dependabot alerts are disabled for the repository.
- No local scanner is installed or approved in CI.
- No named human dependency response owner is recorded in the repository.
- Requirements use bounded ranges rather than exact pins or a committed
  lockfile.

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

## Current Status

Batch 11 documents dependency readiness and adds a bounded Dependabot config for
Python and GitHub Actions.

BATCH-15-OPS-04 documents dependency inventory, safe local dependency baseline,
scanner/tooling blockers, response ownership roles, severity handling, and
update cadence.

Dependency security readiness remains partial until an advisory-backed
vulnerability scan runs successfully and a named response owner/process is
approved.

Design status: No design work performed by Codex.
