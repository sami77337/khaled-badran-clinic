# Production Blocker Closure Roadmap

## Purpose

This roadmap reconciles the remaining production blockers into an actionable
closure map for Dr. Khaled Badran Clinic.

This is docs/evidence-only. It does not configure providers, change Render
settings, add dependencies, change application code, run restore commands,
submit booking POSTs, create patient data, or approve production launch.

Production-ready status:

```text
no
```

## Closure Map

| Category | Current evidence | Blocker status | Next action | Owner role required | Risk if skipped | Safe evidence required | Forbidden evidence/data | Dependency ordering | Can Codex close without external credentials? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Monitoring provider | Health endpoints, low-frequency GitHub Actions staging checks, monitoring plan, signal matrix, and public GET evidence exist. | Blocked. No external provider is selected, configured, or validated. | Owner selects provider and approves public/private check policy. | Project owner, monitoring owner, technical operator. | Outages or severe slow responses may go undetected or unacknowledged. | Provider check summary, status/latency/final URL only, synthetic alert acknowledgement. | Provider credentials, webhook values, request bodies, patient data, full logs. | Before production go/no-go; before claiming alert readiness. | No. Codex can document requirements and validate local docs only. |
| Alert routing | Severity model and alert-routing requirements exist. | Blocked. No primary or backup route is configured or tested. | Approve primary/backup recipients outside Git and run synthetic alert test. | Monitoring owner, backup operator, project owner, legal/privacy escalation. | Incidents may not reach an accountable human. | Sanitized test alert outcome and acknowledgement timing. | Private contact details, pager/webhook tokens, patient data, full payloads. | After provider selection; before launch. | No. Requires owner-approved route and external provider access. |
| Privacy-safe error reporting | Requirements for scrubbing and retention exist. | Blocked. No provider or scrubbed synthetic event exists. | Select provider only after privacy review; disable request-body capture; review synthetic event. | Legal/privacy reviewer, technical operator, project owner. | Exceptions may expose sensitive data or remain invisible. | Scrubbed configuration summary and synthetic event review without secrets. | DSNs, API keys, cookies, tokens, request bodies, patient identifiers, medical data. | After legal/privacy review; before production error reporting. | No. Codex can update docs but cannot configure provider safely. |
| Latency/cold-start mitigation | OPS-03/OPS-06 documented severe latency; OPS-07 fast bounded checks; post-PR #33 operator evidence showed `/health/` severe latency and `/` fast in same window; OPS-08 extended observation evidence is added separately. | Blocked until root cause is explained or owner accepts mitigation. | Decide runtime class, sleep/cold-start posture, monitoring thresholds, and alerting. | Project owner, Render operator, monitoring owner. | Patient-facing pages may be available but unacceptably slow; HTTP 200 may hide operational degradation. | Public GET status, time, final URL only; provider metrics summarized without secrets if approved. | Response bodies, full Render logs, private endpoints, credentials, patient data. | Before launch; informs monitoring thresholds and hosting choice. | Partially. Codex can collect approved public GET evidence and docs; owner/operator must decide hosting. |
| Render managed PostgreSQL restore drill | Local synthetic logical restore passed; operator approval pack exists. | Blocked. No real Render managed restore executed. | Approve and execute isolated managed restore drill with synthetic/demo data only. | Project owner, Render operator, restore drill owner, legal/privacy reviewer. | Backups may be unusable when needed; recovery promises are untested. | Sanitized restore target, migration, smoke, safe counts, and cleanup summary. | Connection strings, dumps, full logs, real patient rows, appointment details. | After owner approvals and backup/RPO/RTO decision direction; before launch. | No. Requires Render access and owner-approved target. |
| Backup retention/RPO/RTO | Backup plan and decision pack exist. | Blocked. No commitment approved. | Owner chooses retention, RPO, RTO, drill cadence, and backup alert policy. | Project owner, backup owner, legal/privacy reviewer, technical operator. | Data loss and downtime expectations remain undefined. | Signed decision summary outside Git and sanitized policy status in docs. | Prices invented by Codex, legal advice, patient data, provider secrets. | Before production restore acceptance and launch. | No. Codex can prepare decision packs only. |
| Legal/privacy approval | Draft legal/privacy docs and data matrices exist. | Blocked. No formal approval recorded. | Obtain qualified legal/privacy review for patient data, retention, deletion, recovery, monitoring, and communications. | Legal/privacy reviewer, project owner. | Launch may violate privacy, consent, retention, or communication obligations. | Approval status, policy version, and open issues without private data. | Legal privileged details, patient data, private contact details. | Before production launch and before real patient use. | No. Codex cannot provide legal approval. |
| Load/concurrency validation | Local tests pass; no staging load/concurrency evidence. | Blocked. | Approve safe staging test plan using synthetic data and bounded rates. | Technical operator, project owner, Render operator. | Booking, portal, rate limits, or database locks may fail under real traffic. | Aggregate test plan and summarized results only. | Patient data, request bodies, aggressive polling, credentialed private data. | After staging runtime and monitoring path are ready; before launch. | Partially. Codex can draft plan and run local tests, not external load without approval. |
| Production hosting/DNS/TLS | Render staging public HTTPS evidence exists; no production DNS/TLS evidence. | Blocked. | Approve production host, custom domain, TLS, redirects, HSTS/CSP policy, and DNS cutover plan. | Project owner, Render/DNS operator, legal/privacy reviewer if public launch. | Users may see insecure, unavailable, or misconfigured production routes. | Public status/header evidence, DNS/TLS summary, no secrets. | Provider account exports, private DNS credentials, response bodies with private data. | After go/no-go prerequisites; before public launch. | No. Requires owner/operator provider access. |
| Owner assignments | Role-based owners documented; named owners not recorded for several areas. | Blocked. | Assign primary and backup owners outside Git for monitoring, backup, restore, dependency response, incident response, and legal/privacy escalation. | Project owner. | Work can stall during incidents or maintenance windows. | Role assignment status without private contact details. | Real private emails, phone numbers, pager IDs, chat webhooks. | Before alerting, backups, restore drills, and go/no-go. | No. Codex can maintain role templates only. |
| Dependency security owner and GitHub alert settings | `pip-audit` workflow exists and local scan passed; role model exists. | Partial but blocked for owner decisions. | Name response owner/backup, decide GitHub vulnerability and Dependabot alert settings, decide lockfile/hash posture. | Project owner, dependency response owner, maintainer. | High/critical advisories may lack accountability. | Scan result, owner-decision status, alert-settings decision status. | GitHub private settings dumps, tokens, secrets, patient data. | Before release candidate and production launch. | Partially. Codex can run scans and update docs; owner must approve settings/owners. |
| Dashboard/admin polish | Staff appointment operations exist; broader dashboard and access review remain incomplete. | Partial. | Decide whether dashboard polish is launch-blocking or post-launch, and require Figma/design approval for visual changes. | Project owner, doctor/admin representative, design reviewer. | Staff workflows may be inefficient or governance gaps may remain. | Scope decision, access review checklist, design handoff if visual changes. | Real patient records, private staff contact data, unauthorized visual redesigns. | After core launch blockers or explicit owner reprioritization. | Partially. Codex can implement approved code later, not approve scope/design alone. |
| Final production go/no-go | Release scorecard, blockers, plans, and evidence docs exist. | Blocked. Production-ready remains `no`. | Conduct owner-led go/no-go review after all launch blockers are closed or formally risk-accepted. | Project owner with technical, legal/privacy, monitoring, backup, and dependency owners. | Premature launch with unresolved privacy, recovery, monitoring, latency, or infrastructure risk. | Final checklist, sanitized evidence links, owner decision. | Secrets, patient data, logs, dumps, response bodies, private contacts. | Last step after all prerequisite categories. | No. Codex can prepare evidence but cannot approve launch. |

## Dependency Ordering Summary

Recommended closure order:

1. Owner assignment and legal/privacy review path.
2. Monitoring provider and alert routing decision.
3. Latency/cold-start runtime decision and approved thresholds.
4. Backup retention, RPO, and RTO decision.
5. Render managed PostgreSQL restore drill in isolated target.
6. Load/concurrency validation plan and execution.
7. Production hosting, DNS, TLS, and security-header validation.
8. Dependency owner and GitHub alert settings decision.
9. Dashboard/admin polish decision if it remains launch-relevant.
10. Final production go/no-go.

Some items can run in parallel, but production launch should not proceed until
monitoring/alerting, backup/restore, legal/privacy, latency, load, dependency
ownership, and production infrastructure gates are closed or explicitly
accepted by the owner with documented risk.

## Batch 15 OPS-08 Closure Status

Improved in this batch:

- extended public staging observation evidence;
- Render managed PostgreSQL restore drill operator pack;
- backup retention/RPO/RTO approval decision pack;
- production blocker closure roadmap.

Still blocked:

- no real Render managed PostgreSQL restore drill;
- no external monitoring provider;
- no alert routing;
- no privacy-safe error-reporting provider;
- no legal/privacy approval;
- no load/concurrency validation;
- no production DNS/TLS;
- no approved backup retention/RPO/RTO;
- no named owner/backup owner where applicable.
