# Operations Governance Closure Matrix

## Purpose

This matrix reconciles the owner, monitoring, alert-routing, dependency,
backup/restore, legal/privacy, business-review, incident-response, and
go/no-go decisions that still block production readiness.

This is docs/evidence-only. It does not assign real people, configure
providers, route alerts, change GitHub settings, change Render settings, add
dependencies, change application code, submit booking forms, create patient
data, or approve launch.

Production-ready status:

```text
no
```

## Closure Matrix

| Category | Current status | Decision needed | Owner role | Safe evidence allowed | Forbidden evidence | Codex closure capability | Remaining blocker | Dependency ordering |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Owner assignments | Role pack created; approval required. | Assign named roles outside Git and record Git-safe status only. | Project owner. | Role status, approval status, owner-held register category. | Private emails, phone numbers, pager IDs, chat destinations, patient data. | No. Codex can document requirements only. | No real owner approvals recorded. | First; needed before alerting, restore, dependency, and go/no-go. |
| Monitoring provider | Selection pack created; no provider selected or configured. | Choose provider class/provider, check policy, retention, access, and evidence rules. | Monitoring owner, project owner, technical operator. | Provider class, status/latency/final URL summary, sanitized readiness status. | Credentials, response bodies, provider keys, private dashboards with sensitive data. | No. Codex can prepare requirements and safe docs only. | No external provider configured or validated. | After owner assignment; before claiming alert or monitoring readiness. |
| Alert routing | Approval/test plan created; no route configured or tested. | Approve primary/backup routes and complete synthetic tests. | Alert-routing owner, monitoring owner, project owner. | Test event name, severity, acknowledgement timing, pass/fail summary. | Webhook URLs, private contacts, payloads with patient data or secrets. | No. Requires owner-approved external route. | No primary or backup route configured/tested. | After provider/route decision; before launch. |
| Privacy-safe error reporting | Requirements exist; no provider configured. | Decide whether to enable provider, scrubbers, retention, access, and synthetic event review. | Legal/privacy reviewer, technical operator, project owner. | Provider class, scrubber checklist, synthetic event review summary. | DSNs, API keys, cookies, request bodies, patient identifiers, medical data. | No. Codex can document requirements only. | No privacy-safe provider or synthetic event review. | After legal/privacy review; before production error reporting. |
| Dependency security governance | `pip-audit` workflow exists; governance pack created. | Assign owner/backup, decide GitHub alert settings, Dependabot alert settings, update strategy, and lockfile/hash posture. | Dependency response owner, project owner, maintainer. | Scan summary, public advisory IDs, PR links, role status. | Tokens, private GitHub settings dumps, credentials, patient data. | Partially. Codex can run scans and docs; owner must decide settings/owners. | No owner/backup, GitHub alert decision, or lockfile/hash decision. | Before release candidate and production launch. |
| Backup/RPO/RTO ownership | Decision pack exists; no policy approved. | Assign backup owner/backup and approve retention, RPO, RTO, backup alert policy. | Backup owner, project owner, legal/privacy reviewer. | Policy status, role status, sanitized backup schedule category. | Backup dumps, storage paths with sensitive identifiers, credentials, patient data. | No. Codex can document decision model only. | No approved backup owners or RPO/RTO commitments. | Before restore acceptance and launch. |
| Render managed restore drill ownership | Operator pack exists; no real drill executed. | Assign restore drill owner, approve isolated target, execute sanitized managed restore drill. | Restore drill owner, Render operator, project owner, legal/privacy reviewer. | Drill status, migration/smoke summary, safe counts, cleanup status. | Connection strings, dumps, full logs, patient rows, provider secrets. | No. Requires Render access and owner-approved target. | No real Render managed PostgreSQL restore drill. | After owner approvals and backup policy direction; before launch. |
| Legal/privacy approval | Draft docs and safety matrices exist; no formal approval. | Approve patient data, retention, deletion, monitoring, recovery, incident, and communications posture. | Legal/privacy reviewer and project owner. | Approval status, policy version, issue categories. | Privileged legal details, patient data, private contacts. | No. Codex cannot provide legal approval. | No formal legal/privacy approval. | Before real patient use, error reporting, and go/no-go. |
| Release/go-no-go | Scorecard and blockers exist; production-ready remains no. | Conduct final owner-led launch decision after all prerequisite gates. | Release/go-no-go approver and project owner. | Checklist status, blocker disposition, sanitized evidence links. | Secrets, patient data, logs, dumps, private contacts. | No. Codex can prepare evidence only. | No production go/no-go approval. | Last step. |
| Dashboard/admin business reviewer | Staff operations exist; business polish scope remains partial. | Decide whether dashboard/admin polish is launch-blocking and review workflow fit. | Doctor/admin business reviewer and project owner. | Scope decision, sanitized workflow review, launch-blocking status. | Real patient records, appointment details, staff private contacts, medical data. | Partially. Codex can implement later if explicitly authorized; cannot approve business fit. | No launch-blocking scope decision. | After core safety blockers or owner reprioritization. |
| Incident response ownership | Runbook exists; no live route/owner coverage approved. | Assign incident commander, backup coverage, escalation path, and drill/test expectations. | Incident commander, alert-routing owner, legal/privacy reviewer. | Role status, incident drill summary, severity mapping. | Raw logs, credentials, patient data, private contacts, webhook values. | No. Codex can maintain runbook only. | No approved live incident owner coverage or alert route. | Before launch and before claiming alert readiness. |

## Dependency Ordering Summary

Recommended ordering:

1. Approve owner assignments outside Git.
2. Approve legal/privacy review path for monitoring, incident, and recovery
   evidence.
3. Select monitoring provider class/provider and public/private check policy.
4. Approve and test alert routing with synthetic safe payloads.
5. Approve dependency response owner/backup and GitHub alert/update strategy.
6. Approve backup owner/backup, retention, RPO, and RTO.
7. Prepare and execute Render managed PostgreSQL restore drill with an
   approved isolated target.
8. Decide privacy-safe error reporting provider and synthetic event review if
   in launch scope.
9. Resolve dashboard/admin business-review launch scope.
10. Complete final release go/no-go only after prerequisite blockers close or
    are formally owner-accepted.

## Closure Conclusion

OPS-09 improves governance documentation, but it does not close production
blockers that require owner/operator decisions or external provider actions.

Production-ready remains:

```text
no
```
