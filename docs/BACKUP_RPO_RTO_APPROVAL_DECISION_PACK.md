# Backup Retention, RPO, and RTO Approval Decision Pack

## Current Status

Status:

```text
owner approval required
```

No backup retention, RPO, or RTO commitment is approved until owner signs off.

Production-ready status:

```text
no
```

## Decisions Needed

Backup retention decision needed:

- how many daily backups to retain;
- whether weekly/monthly retention is required;
- whether point-in-time recovery is required if the provider plan supports it;
- how deletion requests and legal holds interact with backup retention;
- how long restore-test artifacts may exist after drills.

RPO decision needed:

- maximum acceptable data-loss window for the clinic;
- whether booking/portal data requires shorter recovery windows than general
  site content;
- whether future private media changes the recovery objective.

RTO decision needed:

- maximum acceptable time to restore the application after data loss or
  corruption;
- whether the target differs for staging and production;
- whether the target changes during clinic operating hours.

## Owner Approval Roles

The approval package requires named roles outside Git:

| Role | Decision area |
| --- | --- |
| Project owner/operator | Accepts backup retention, RPO, RTO, cost, and operational tradeoffs. |
| Technical operator | Confirms feasibility with the selected Render/database plan. |
| Restore drill owner | Confirms restore procedure and evidence requirements. |
| Legal/privacy reviewer | Reviews retention, deletion, legal hold, and patient-data handling. |
| Monitoring owner | Confirms backup success/failure and missing-backup alert requirements. |
| Backup owner | Owns backup access, review cadence, and drill schedule. |
| Backup owner backup | Covers absence and escalation continuity. |

Do not record private contact details in this repository.

## Proposed Options

| Option | Description | Cost/complexity tradeoff | Suitable when |
| --- | --- | --- | --- |
| Minimal staging-only | Keep current repository evidence plus staging-only synthetic restore planning. No production commitment. | Lowest immediate cost and complexity; does not support production launch. | The service remains pre-launch and owner is still evaluating production operations. |
| Small clinic baseline | Provider-managed PostgreSQL backups enabled, daily review expectation, pre-launch synthetic managed restore drill, approved retention window, approved RPO/RTO, backup failure alert, and named backup owners. | Moderate operational overhead; requires owner decisions and provider configuration outside Git. | The clinic wants a practical production baseline without over-engineering. |
| Stronger production posture | Shorter recovery windows where supported, point-in-time recovery if available, regular restore drills, backup access reviews, alert routing, and documented legal/privacy retention process. | Highest operational rigor and complexity; may require higher provider capability and more owner/operator time. | The owner requires stronger resilience, shorter recovery windows, or higher assurance before launch. |

No prices are invented in this document. The owner/operator must review the
actual provider plan, clinic risk tolerance, support availability, and legal
requirements before approving a posture.

## Evidence Required Before Approval

Required safe evidence:

- selected provider plan capability summary without secret values;
- backup schedule category;
- retention window decision;
- RPO decision;
- RTO decision;
- named backup owner and backup owner backup recorded outside Git;
- backup success/failure alert route approved and tested;
- missing-backup alert policy approved;
- Render managed PostgreSQL restore drill completed in an isolated target;
- sanitized restore verification summary;
- legal/privacy review of retention and deletion boundaries;
- cleanup confirmation for restore-test targets.

## What Remains Blocked

Blocked until owner/operator approval:

- production backup policy;
- production RPO;
- production RTO;
- backup retention;
- backup failure alerting;
- missing-backup alerting;
- managed PostgreSQL restore acceptance;
- restore drill cadence;
- backup access review cadence;
- legal hold and deletion interaction;
- production launch readiness.

## Safety Boundaries

This decision pack does not:

- configure backups;
- change Render settings;
- use Render credentials;
- run restore commands;
- create database dumps;
- inspect production data;
- create patient data;
- store logs;
- expose connection strings;
- approve production launch.

Policy/category labels may be mentioned, but secret values and patient data
must not be included in Git, pull requests, chat, or shared docs.

## Recommended Decision Gate

Before production promotion, the owner should choose one of:

- defer launch until the small clinic baseline or stronger posture is approved
  and validated;
- explicitly remain staging-only with production-ready still `no`;
- document a qualified risk acceptance outside Git only after legal/privacy and
  technical operators review the consequences.

Repository documentation can support the decision, but it cannot substitute for
owner approval.
