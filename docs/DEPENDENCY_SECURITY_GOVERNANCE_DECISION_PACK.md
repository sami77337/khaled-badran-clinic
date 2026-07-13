# Dependency Security Governance Decision Pack

## Current Status

Status:

```text
scan workflow exists; governance decisions remain blocked
```

Current evidence:

- The repository has a `pip-audit` workflow in
  `.github/workflows/dependency-audit.yml`.
- Local `pip-audit -r requirements.txt --progress-spinner off` evidence says
  no known vulnerabilities were found at scan time.
- This is not a guarantee of security.
- New advisories can appear after any scan.
- A scan result does not replace owner assignment, alert review, patch policy,
  legal/privacy review, or release blocking decisions.

No dependency versions were changed. No lockfile was generated. No GitHub
repository security setting was changed.

Production-ready status:

```text
no
```

## Required Decisions

| Decision | Current status | Owner role |
| --- | --- | --- |
| Dependency response owner | Not approved in Git-safe form. | Project owner and dependency response owner. |
| Dependency response backup | Not approved in Git-safe form. | Project owner and dependency response backup. |
| GitHub vulnerability alerts setting | Owner decision still required if not enabled. | Project owner and repository maintainer. |
| Dependabot alerts setting | Owner decision still required if not enabled. | Project owner and repository maintainer. |
| Dependabot update strategy | Weekly configuration exists; manual review and no auto-merge remain required. | Dependency response owner and maintainer. |
| Bounded-ranges versus lockfile/hash workflow | Open decision. | Project owner, dependency response owner, maintainer. |
| Advisory severity response SLA | Role model exists; owner-approved SLA still required. | Project owner and dependency response owner. |

## Severity Response Model

| Severity | Required response | Release impact |
| --- | --- | --- |
| Critical | Immediate owner assignment, exposure review, patch/mitigation/disable decision, incident response if exploitation or data exposure is suspected. | Blocks release and production promotion until resolved or owner/legal risk acceptance is recorded outside Git. |
| High | Same-business-day triage by owner, affected code-path review, smallest safe patch or mitigation, full local validation, staging validation when relevant. | Blocks release candidate unless owner records bounded risk acceptance outside Git. |
| Medium | Weekly triage or release-candidate review, patch before release candidate unless bounded risk acceptance is approved. | Should block release candidate if untriaged. |
| Low | Routine maintenance after tests pass. | Does not usually block release unless bundled with higher risk or affected critical path. |

If severity is unknown or scanner results are tool-blocked, do not claim a
clean scan. Record the blocker and rerun with an approved advisory source.

## Allowed Safe Evidence

The following evidence may be recorded in Git when sanitized:

- package names;
- public advisory IDs;
- scanner name and version;
- scan command category;
- scan result summary;
- PR link or commit SHA for a dependency fix;
- role status, such as assigned outside Git or owner approval pending;
- severity category;
- pass/fail validation summary;
- decision status without private contact details.

## Forbidden Evidence

Do not record:

- tokens;
- private GitHub settings dumps;
- GitHub credentials;
- provider credentials;
- patient data;
- private emails;
- private phone numbers;
- pager IDs;
- webhook URLs;
- passwords;
- secret values;
- private keys;
- database/cache connection values;
- full logs containing sensitive data.

## Acceptance Criteria

Dependency security governance readiness cannot be claimed until:

- dependency response owner is approved outside Git and represented only by
  Git-safe role status;
- dependency response backup is approved outside Git and represented only by
  Git-safe role status;
- GitHub vulnerability alert setting decision is recorded safely;
- Dependabot alert setting decision is recorded safely;
- Dependabot update strategy is approved, including manual review and no
  auto-merge unless separately approved;
- bounded-ranges versus lockfile/hash workflow decision is approved;
- severity response SLA is approved for critical, high, medium, and low
  advisories;
- `pip-audit` scan is current for the release candidate;
- critical/high advisory response path is tested or reviewed;
- no credentials, private GitHub settings dumps, patient data, or private
  contact details enter Git.

Current readiness:

```text
not ready
```
