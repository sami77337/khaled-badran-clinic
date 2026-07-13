# Render Managed PostgreSQL Restore Drill Operator Pack

## Current Status

Status:

```text
not executed
```

No Render managed PostgreSQL restore drill was executed in this batch.

This document is an operator approval pack. It is not a record of a completed
restore, and it does not authorize any destructive action by itself.

Production-ready status:

```text
no
```

## Why The Real Managed Restore Drill Is Still Blocked

A real Render managed PostgreSQL restore drill remains blocked because it
requires owner/operator actions outside this repository:

- approved Render operator access;
- approved isolated restore target;
- approved backup source and recovery point;
- approved backup retention, RPO, and RTO policy;
- approved privacy and patient-data boundaries;
- approved evidence handling rules;
- named drill owner, backup operator, and legal/privacy escalation role;
- provider-safe execution window;
- rollback and cleanup authority.

Codex did not use Render credentials, inspect Render environment values, open a
Render shell, run provider backup commands, run provider restore commands, or
change Render settings.

## Secret Boundaries

The drill package must never include:

- database connection strings;
- cache connection strings;
- provider environment dumps;
- passwords;
- token values;
- secret key values;
- private keys;
- cookies;
- session identifiers;
- CSRF token values;
- raw provider logs;
- backup artifacts;
- database dumps.

Category labels may be referenced in policy text, but values must stay outside
Git, pull requests, chat, tickets, and shared documents unless the approved
secure evidence channel explicitly permits them.

## Patient-Data Boundaries

Pre-launch restore drills must use synthetic or public/demo data only.

The drill must not collect, create, restore, expose, or document:

- real patient names;
- real patient emails;
- real patient phone numbers;
- appointment details;
- medical notes;
- medical reports;
- uploaded files;
- payment data;
- private portal data;
- message contents.

If real patient data is discovered in a source or restore target, the drill
must stop and the incident response runbook must be followed.

## Required Owner Approvals

Before any real managed restore drill, record approvals outside Git for:

- project owner approval to run the drill;
- Render operator approval for source backup access;
- restore drill owner;
- backup operator;
- restore target owner;
- legal/privacy reviewer;
- evidence reviewer;
- cleanup approver;
- incident escalation owner.

The approval record should include the planned drill date, target environment,
expected data class, approved recovery point, expected downtime if any, and
rollback authority. Do not include credentials or connection values.

## Safe Evidence That May Be Collected

Safe evidence for repository docs or a PR may include:

- drill status as planned, blocked, started, completed, or aborted;
- approved environment category, such as isolated restore target;
- command categories, not full command lines with secrets;
- application revision or Git commit SHA;
- migration status summary;
- public/demo row counts only;
- zero-count confirmations for patient and appointment tables when using a
  demo-only target;
- `deployment_smoke --strict` pass/fail summary;
- safe settings report categories only;
- public GET status, total time, and final URL only;
- cleanup status;
- incident criteria triggered or not triggered.

## Forbidden Evidence

Do not collect or paste:

- provider console screenshots that show secrets or private metadata;
- full Render logs;
- full command transcripts containing environment values;
- database dumps;
- backup object paths containing sensitive identifiers;
- connection strings;
- raw query output with patient or appointment rows;
- request bodies;
- cookies;
- session identifiers;
- CSRF token values;
- real contact details;
- appointment dates, notes, or medical content.

## Pre-Drill Checklist

Complete before execution:

- confirm the drill is synthetic/demo-only or otherwise legally approved;
- confirm source backup and recovery point are approved;
- confirm the restore target is isolated from active staging and production;
- confirm no active public route points at the restore target;
- confirm credentials are available only to approved operators outside Git;
- confirm the application revision is known;
- confirm migrations expected at that revision are known;
- confirm evidence channel and redaction rules;
- confirm rollback/cleanup authority;
- confirm incident escalation route;
- confirm the drill will not submit booking POSTs or create patient data;
- confirm response bodies will not be saved.

## Drill Execution Roles

Recommended roles:

| Role | Responsibility |
| --- | --- |
| Project owner | Approves drill, accepts schedule, and receives outcome. |
| Render operator | Uses provider access to create or select backup and restore target. |
| Restore drill owner | Coordinates steps, evidence boundaries, and stop/go decisions. |
| Repository maintainer | Runs safe application validation when given an approved environment. |
| Legal/privacy reviewer | Confirms patient-data, retention, deletion, and notification boundaries. |
| Evidence reviewer | Confirms shared evidence is sanitized before it enters Git or a PR. |
| Cleanup approver | Confirms restored resources and artifacts are removed or retained under policy. |

## Proposed Drill Environment Isolation

The restore target should be:

- separate from production;
- separate from active staging if staging is serving validation traffic;
- reachable only by approved operators;
- connected to an approved temporary application clone or trusted shell;
- configured with environment values outside Git;
- destroyed after review unless the owner approves retention;
- monitored during the drill for unexpected public exposure.

Do not overwrite active production. Do not overwrite active staging unless the
owner explicitly approves a maintenance window and rollback plan.

## Backup Source Requirements

The backup source must have:

- approved source environment;
- approved recovery point;
- known application revision;
- known migration state;
- confirmed data classification;
- provider-managed backup status or approved logical backup status;
- access restricted to named operators;
- evidence that the backup can be selected without exposing secret values.

For pre-launch drill use, prefer a source containing only public/demo data. If
any non-demo data may exist, legal/privacy review is required before using it.

## Restore Target Requirements

The restore target must have:

- isolated database;
- no production traffic;
- no public patient or appointment exposure;
- approved application clone or trusted shell for validation;
- safe cache behavior documented;
- migrations checked after restore;
- cleanup plan;
- evidence channel that excludes secrets and real patient data.

## Command Categories

Allowed documentation may name command categories only:

- provider-managed backup selection;
- provider-managed restore into isolated target;
- logical dump export when approved by the operator;
- logical restore into isolated target when approved by the operator;
- Django migration check;
- Django system check;
- strict deployment smoke;
- safe production settings report;
- safe project status report;
- public GET smoke checks.

Do not document real connection values, provider environment values, command
lines that contain secrets, or full provider logs.

## Verification Categories

Post-restore verification must cover:

- migrations applied;
- migration state clean;
- Django system checks pass;
- strict deployment smoke passes;
- safe public/demo data counts only;
- zero patient rows if using a demo-only target;
- zero appointment rows if using a demo-only target;
- no appointment/private data exposure;
- no upload, medical-record, WhatsApp, payment, AI, diagnosis, triage, or
  treatment automation surfaces unexpectedly enabled;
- application smoke checks for safe public GET routes only;
- production settings report categories match the approved restore target;
- cache behavior is known and documented;
- no response bodies, logs, dumps, credentials, or patient data are retained in
  Git.

## Rollback And Cleanup Checklist

After validation or abort:

- disconnect the application clone from the restore target;
- destroy the restore target if it is no longer needed;
- remove temporary backup artifacts if any were created;
- revoke temporary access if any was issued;
- confirm no restored target is public;
- confirm no patient data or secrets were copied into Git;
- record sanitized pass/fail outcome;
- record follow-up owner for any failure;
- escalate if incident criteria were triggered.

## Incident Criteria

Stop the drill and follow the incident response runbook if:

- real patient data appears in an unapproved target;
- a connection value, password, token, private key, cookie, or session value is
  exposed;
- a restore points active traffic at the wrong database;
- migrations fail and data integrity is uncertain;
- strict smoke fails in a way that indicates application/data mismatch;
- public routes expose private appointment or patient data;
- cleanup cannot be verified;
- the drill produces raw logs or dumps that cannot be safely handled.

## Acceptance Criteria

A real Render managed PostgreSQL restore drill can be accepted only when:

- owner/operator approval is recorded outside Git;
- the restore target is isolated;
- approved backup source and recovery point are used;
- evidence confirms migration state and strict smoke success;
- public/demo counts are safe and expected;
- zero patient and zero appointment rows are confirmed for demo-only targets;
- no appointment/private data exposure occurs;
- cleanup is complete;
- sanitized evidence is reviewed before entering Git;
- backup retention, RPO, and RTO decisions are either approved or clearly
  recorded as remaining blockers.

## Batch 15 OPS-08 Statement

No Render managed PostgreSQL restore drill was executed in this batch.

This pack improves operator readiness only. It does not prove provider-managed
backup behavior, restore behavior, production readiness, backup retention, RPO,
RTO, alerting, legal/privacy approval, or launch readiness.
