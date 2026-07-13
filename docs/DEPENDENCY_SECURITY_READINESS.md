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
requires recurring vulnerability scan review and an approved update response
process.

Risks:

- version ranges can admit newer minor/patch versions with regressions,
- unreviewed dependency updates may affect security behavior,
- recurring scan evidence still needs accountable owner review before launch,
- GitHub vulnerability/Dependabot alert settings still need an owner decision,
- no named owner is assigned for high/critical dependency response.

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

- `python --version` reported Python 3.14.2 in the active local environment.
- `python -m pip --version` reported pip 26.1 in the active local environment.
- `python -m pip check` exited successfully with no broken requirements.
- `python manage.py check --deploy` exited 0 with 6 expected
  local-development Django security warnings under `config.settings.dev`.
- `python manage.py deployment_smoke --strict` exited 0 under local dev
  settings with 16 pass, 4 expected local warnings, 0 failures, and 0 strict
  blockers.
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

## Batch 15-OPS-05 Advisory Scan Workflow

BATCH-15-OPS-05 adds repository-supported advisory-backed dependency scanning
with `pip-audit`.

Scanner:

```text
pip-audit
```

Manifest scanned:

```text
requirements.txt
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

- `pip-audit 2.10.1` completed successfully in the active local environment.
- No known advisories were returned for `requirements.txt` at scan time.
- This is not a guarantee that the application or dependency set is
  vulnerability-free.
- No dependency packages were upgraded.
- No lockfile was generated.
- No Render settings were changed.
- No patient data was used.

CI workflow:

- `.github/workflows/dependency-audit.yml`
- workflow name: `Dependency audit`
- runs on pull requests, manual dispatch, and a low-frequency weekly schedule
- installs `pip-audit` as CI tooling only
- runs `pip-audit -r requirements.txt --progress-spinner off`
- fails on scanner failure or real vulnerability findings
- does not modify dependencies or lockfiles
- does not use secrets, Render access, external app endpoints, response
  bodies, or patient data

Detailed workflow evidence is recorded in
`docs/DEPENDENCY_AUDIT_WORKFLOW_EVIDENCE.md`.

## Batch 15-OPS-09 Governance Decision Pack

BATCH-15-OPS-09 adds:

- `docs/DEPENDENCY_SECURITY_GOVERNANCE_DECISION_PACK.md`
- `docs/OPS_GOVERNANCE_CLOSURE_MATRIX.md`

The governance decision pack records that the `pip-audit` workflow exists and
that current scan evidence returned no known vulnerabilities at scan time, but
it explicitly keeps dependency security governance incomplete until these owner
decisions are made:

- dependency response owner;
- dependency response backup;
- GitHub vulnerability alerts setting;
- Dependabot alerts setting;
- Dependabot update strategy;
- bounded-ranges versus lockfile/hash workflow;
- advisory severity response SLA.

No GitHub repository security setting was changed by OPS-09. No dependency
package was upgraded and no lockfile was generated.

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

- A named human dependency response owner and backup owner are not recorded in
  the repository.
- GitHub vulnerability alerts still need an owner decision if they are not
  enabled.
- GitHub Dependabot alerts still need an owner decision if they are not
  enabled.
- Requirements use bounded ranges rather than exact pins or a committed
  lockfile.
- The lockfile/hash workflow decision remains open.

## Repository pip-audit Scanner

`pip-audit` is the repository-supported Python dependency vulnerability scanner
added by BATCH-15-OPS-05.

Local and CI command:

```bash
pip-audit -r requirements.txt --progress-spinner off
```

CI installs `pip-audit` as tooling only. Do not add scanner credentials. Do not
upgrade dependencies or generate a lockfile inside the scan workflow. Ensure
failures are reviewed by a maintainer and the accountable dependency response
owner.

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

BATCH-15-OPS-05 adds a `pip-audit` workflow and records a successful local
advisory-backed scan of `requirements.txt` with no known advisories returned at
scan time.

BATCH-15-OPS-09 adds the dependency security governance decision pack and
closure matrix. Dependency security readiness remains partial until a named
response owner and backup owner are approved, GitHub vulnerability and
Dependabot alert settings receive owner decisions, the update strategy is
approved, the severity response SLA is approved, and the bounded-ranges versus
lockfile/hash workflow decision is closed.

Design status: No design work performed by Codex.
