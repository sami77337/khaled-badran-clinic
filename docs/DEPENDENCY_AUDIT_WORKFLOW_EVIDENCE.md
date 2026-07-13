# Dependency Audit Workflow Evidence

BATCH-15-OPS-05 adds advisory-backed dependency vulnerability scanning through
`pip-audit` and a dedicated GitHub Actions workflow.

## Scope

The scan scope is the Python runtime manifest:

```text
requirements.txt
```

No dependency packages were upgraded. No lockfile was generated. No Render
settings were changed. No patient data, response bodies, logs, credentials, or
connection strings were used or recorded.

Production-ready status:

```text
no
```

## Local Tooling Evidence

| Command | Result |
| --- | --- |
| `python --version` | Exit 0; Python 3.14.2 in the active local environment. |
| `python -m pip --version` | Exit 0; pip 26.1 in the active local environment. |
| `pip-audit --version` | Exit 0; `pip-audit 2.10.1`. |
| `python -m pip check` | Exit 0; no broken requirements found. |

## Local Advisory Scan

Command:

```bash
pip-audit -r requirements.txt --progress-spinner off
```

Result:

```text
No known vulnerabilities found
```

Interpretation:

- `pip-audit` completed successfully.
- No known advisories were returned for `requirements.txt` at scan time.
- This result is not a guarantee of security or vulnerability-free operation.
- New advisories can be published after the scan.
- The result must be reviewed again after dependency-file changes, before a
  release candidate, and before production promotion.

## GitHub Actions Workflow

Workflow file:

```text
.github/workflows/dependency-audit.yml
```

Workflow behavior:

- name: `Dependency audit`;
- triggers on pull requests;
- supports manual `workflow_dispatch`;
- runs weekly at low frequency;
- uses `permissions: contents: read`;
- checks out the repository;
- uses `actions/setup-python@v5`;
- installs `pip-audit` inside CI as tooling only;
- does not edit, upgrade, or regenerate project dependencies;
- does not generate a lockfile;
- runs:

```bash
python -m pip install --upgrade pip
python -m pip install pip-audit
pip-audit -r requirements.txt --progress-spinner off
```

Expected failure behavior:

- fail if `pip-audit` exits nonzero for scanner failure;
- fail if `pip-audit` reports real vulnerabilities;
- require owner triage before release if critical/high advisories are reported.

Expected output boundary:

- scanner output only;
- no secrets;
- no Render access;
- no external application endpoint calls;
- no response bodies;
- no patient data.

## Operational Use

Run the workflow:

- on every pull request;
- manually after dependency-file edits;
- manually before a release candidate;
- manually before production promotion;
- weekly during active development.

If advisories are found:

- assign the accountable dependency response owner;
- identify affected packages and code paths;
- decide whether to patch, mitigate, hold release, or document bounded risk;
- run the local Django baseline and relevant security regression checks after
  any dependency change;
- do not auto-merge dependency updates.

## Governance Closure Status

BATCH-15-OPS-09 adds:

- `docs/DEPENDENCY_SECURITY_GOVERNANCE_DECISION_PACK.md`
- `docs/OPS_GOVERNANCE_CLOSURE_MATRIX.md`

The workflow provides advisory-backed scan evidence, but it does not by itself
close dependency security governance. Before dependency security governance can
be claimed ready, the owner must approve the dependency response owner and
backup, GitHub vulnerability alert setting decision, Dependabot alert setting
decision, Dependabot update strategy, bounded-ranges versus lockfile/hash
workflow decision, and advisory severity response SLA.

No GitHub repository security setting is changed by documenting this status.

## Remaining Blockers

- A named human dependency response owner and backup owner still need approval
  and repository documentation.
- GitHub vulnerability and Dependabot alerts still need an owner decision if
  they are not enabled.
- A lockfile/hash workflow decision remains open.
- Full monitoring provider setup remains incomplete.
- Alert routing remains incomplete.
- Privacy-safe error reporting remains incomplete.
- Render managed PostgreSQL restore drill evidence remains incomplete.
- Legal/privacy approval remains incomplete.
- Load/concurrency validation remains incomplete.
- Production hosting, DNS, custom domain, and TLS remain incomplete.
- Production-ready remains no.
