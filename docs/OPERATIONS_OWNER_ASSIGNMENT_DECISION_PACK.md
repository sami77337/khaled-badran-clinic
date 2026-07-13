# Operations Owner Assignment Decision Pack

## Current Status

Status:

```text
owner approval required
```

This is an owner-role decision pack, not a private contact list. It defines the
roles that must be assigned and approved outside Git before production launch
or live operational readiness can be claimed.

No private emails, private phone numbers, pager IDs, chat handles, alert
destination identifiers, webhook URLs, or personal contact values are recorded
in Git.

Production-ready status:

```text
no
```

## Approval Model

Role assignment happens outside Git through an owner-approved channel.

Repository documentation may record only:

- role name;
- role status, such as unassigned, assigned outside Git, backup required, or
  owner approval pending;
- approval date or review window if the owner permits that metadata;
- evidence location category, such as owner-held operations register;
- sanitized decision summary with no contact values.

Repository documentation must not record:

- private emails;
- private phone numbers;
- pager IDs;
- chat destination IDs;
- webhook URLs;
- personal calendar links;
- private account names;
- credentials;
- provider console exports;
- patient data.

Codex can document role requirements and safe evidence rules, but Codex cannot
assign real humans, approve private contact channels, guarantee availability,
or close an owner-assignment blocker without owner input.

## Required Roles

| Role | Responsibility | Decision authority | Minimum availability expectation | Safe evidence allowed in Git | Forbidden evidence/private data | Can Codex close without owner input? |
| --- | --- | --- | --- | --- | --- | --- |
| Project owner | Owns launch risk, budget, operational posture, and final acceptance. | Can approve or reject production go/no-go, hosting cost, risk acceptance, and owner assignment model. | Available for launch decisions, SEV-1 escalation, and material policy changes. | `project owner assigned outside Git`; approval status; decision date category. | Private contact details, personal accounts, legal privileged notes, patient data. | No. |
| Technical operator | Owns deployed runtime operations, staging/production validation, provider configuration, and rollback coordination. | Can approve technical execution steps inside owner-approved scope. | Available during deploy, restore drill, incident, and monitoring setup windows. | Role status; sanitized execution summary; command category outcomes. | Render credentials, shell transcripts with secrets, private contact values, provider logs. | No. |
| Backup technical operator | Covers the technical operator when unavailable. | Can execute approved operational procedures under the same boundaries. | Available through the approved backup coverage schedule. | Backup role assigned outside Git; coverage status. | Private contact details, pager values, provider account exports. | No. |
| Monitoring owner | Owns provider selection, signal policies, threshold approval, and monitoring review cadence. | Can accept monitoring configuration as ready only after provider and route tests pass. | Available for monitoring setup, warning review, and SEV-1/SEV-2 escalation. | Role status; provider decision status; sanitized threshold approval. | Provider credentials, dashboards with private data, response bodies, private contacts. | No. |
| Alert-routing owner | Owns primary and backup alert route approval, synthetic alert testing, and route failure fallback. | Can approve alert-routing readiness after route tests and payload review. | Available for route test windows and escalation policy review. | Route readiness status; test event name; acknowledgement timing summary. | Webhook URLs, email addresses, phone numbers, pager IDs, chat channel IDs, payloads with sensitive data. | No. |
| Incident commander | Coordinates incident severity, timeline, containment, escalation, and recovery. | Can declare severity and coordinate response inside approved policy. | Available for SEV-1/SEV-2 incidents according to the approved coverage model. | Role status; incident drill status; sanitized timeline template. | Personal contact details, raw logs, credentials, patient data, privileged legal notes. | No. |
| Backup owner | Owns backup policy, backup success review, access review, and restore cadence. | Can approve operational backup tasks after project owner and legal/privacy decisions. | Available for backup failure review and scheduled backup policy review. | Role status; backup policy decision status; review cadence. | Backup object paths with sensitive identifiers, credentials, dumps, private contacts. | No. |
| Backup owner backup | Covers backup owner absence and escalates backup failures. | Can execute owner-approved backup follow-up when primary owner is unavailable. | Available through the approved backup coverage schedule. | Backup coverage status; escalation role status. | Private contact values, backup credentials, storage access metadata. | No. |
| Restore drill owner | Coordinates real managed restore drill approvals, isolation, execution window, evidence, and cleanup. | Can recommend drill pass/fail, but cannot approve destructive action without owner authority. | Available for drill planning, execution, abort decisions, and cleanup verification. | Drill owner status; isolated target category; sanitized pass/fail summary. | Connection strings, dumps, full logs, patient rows, provider secrets, private contacts. | No. |
| Dependency response owner | Owns advisory triage, severity classification, patch/mitigation decision, and release blocking. | Can decide dependency advisory response path inside owner-approved risk policy. | Available for critical/high advisory triage and release-candidate review. | Role status; advisory ID if public; scan summary; PR link. | GitHub tokens, private settings dumps, credentials, patient data, private contacts. | No. |
| Dependency response backup | Covers dependency response when the primary owner is unavailable. | Can triage and escalate critical/high advisories under the same policy. | Available for backup coverage during release and active advisory windows. | Backup role status; escalation coverage status. | Private contact values, private GitHub exports, secret values. | No. |
| Legal/privacy reviewer | Reviews patient data, retention, deletion, monitoring payloads, incident communications, and privacy risk acceptance. | Can approve or block legal/privacy launch posture. | Available before launch, before real patient use, and for suspected privacy incidents. | Review status; policy version; open issue categories. | Legal privileged details, patient data, private contacts, external statements before approval. | No. |
| Release/go-no-go approver | Runs final launch readiness review across technical, legal, monitoring, backup, dependency, and business gates. | Can approve final go/no-go only after prerequisite evidence is complete or formally risk-accepted. | Available for release-candidate review and launch window decisions. | Go/no-go status; checklist completion state; blocker disposition. | Private contacts, credentials, patient data, full logs, provider exports. | No. |
| Doctor/admin business reviewer | Reviews clinic workflow fit, dashboard/admin practicality, content accuracy, and business acceptance. | Can accept or reject business workflow readiness and launch-blocking polish scope. | Available for workflow review before launch and after critical staff-facing changes. | Business review status; scope decision; sanitized workflow notes. | Staff private contact details, real patient cases, appointment details, medical data. | No. |

## Safe Evidence Pattern

Allowed Git evidence should look like:

```text
Role: monitoring owner
Status: assigned outside Git
Evidence: owner-held operations register reviewed
Private contact details recorded in Git: no
Remaining blocker: alert route still untested
```

Do not replace the role status with a private contact value.

## Remaining Blockers

- Project owner has not approved the role assignment register in repository
  evidence.
- Monitoring owner and alert-routing owner are not approved in Git-safe form.
- Backup owner, backup owner backup, and restore drill owner are not approved
  in Git-safe form.
- Dependency response owner and backup are not approved in Git-safe form.
- Legal/privacy reviewer approval remains absent.
- Release/go-no-go approver approval remains absent.
- Doctor/admin business reviewer launch-blocking scope remains undecided.

Production-ready remains:

```text
no
```
