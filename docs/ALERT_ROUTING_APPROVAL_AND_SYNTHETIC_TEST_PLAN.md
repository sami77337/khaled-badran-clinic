# Alert Routing Approval And Synthetic Test Plan

## Current Status

Status:

```text
not configured or tested
```

No primary route, backup route, webhook, pager route, chat route, email route,
SMS route, or provider notification destination is configured by this
repository evidence. No real alert was sent in this batch.

Production-ready status:

```text
no
```

## Route Requirements

Primary route requirements:

- approved outside Git by the project owner and alert-routing owner;
- reaches the primary technical operator or approved incident intake path;
- supports SEV-1 and SEV-2 acknowledgement expectations;
- receives only sanitized alert payloads;
- does not expose private contact values in Git.

Backup route requirements:

- approved outside Git before launch;
- independent enough to work if the primary route is unavailable;
- reaches a backup technical operator or owner-approved fallback path;
- tested with a synthetic event;
- does not expose private contact values in Git.

Repository docs may record route status, test event name, severity, timing
summary, and pass/fail outcome. Repository docs must not record route
destinations or contact values.

## Severity Mapping

| Severity | Meaning | Example trigger classes | Expected acknowledgement |
| --- | --- | --- | --- |
| SEV-1 | Critical incident. | Confirmed or likely patient-data exposure, credential exposure, active compromise, production outage with no workaround, data corruption, destructive restore failure. | Immediate acknowledgement by primary route, owner escalation, and incident commander assignment. |
| SEV-2 | High operational risk. | Database readiness failure, Redis/cache outage affecting rate limits, failed deploy requiring rollback, backup job failure inside approved recovery window, significant 5xx spike. | Primary operator acknowledgement within the owner-approved window; backup route if unacknowledged. |
| SEV-3 | Medium degradation or validation blocker. | Severe slow HTTP 200 responses, intermittent errors, staging-only blocker, monitoring gap, non-critical dependency advisory. | Acknowledgement during support window or scheduled review according to policy. |
| SEV-4 | Low follow-up. | Documentation update, checklist task, non-urgent tuning, routine dependency maintenance. | Track as planned work; no immediate escalation unless owner policy says otherwise. |

## Alert Types

Required alert types before production readiness can be claimed:

| Alert type | Initial severity | Notes |
| --- | --- | --- |
| Public outage | SEV-1 or SEV-2 depending on production impact | Public `/health/` or `/` repeated failures. |
| Slow HTTP 200 | SEV-3 by default; SEV-2 if sustained in production | HTTP 200 alone is not readiness when latency is severe. |
| Repeated latency over threshold | SEV-2 or SEV-3 | Thresholds must be owner-approved and provider-configured. |
| Deploy failure | SEV-2 | Includes failed build, failed deploy, migration failure, crash loop, or post-deploy smoke failure. |
| Database/cache alert | SEV-2 by default | Includes readiness failure, database connectivity, cache outage, or rate-limit degradation. |
| Backup failure | SEV-2 by default | Includes failed backup, missing backup inside approved window, or restore drill failure. |
| Dependency critical advisory | SEV-1 or SEV-2 | Depends on exploitation, exposure, and affected code path. |
| Privacy/security incident | SEV-1 by default until triaged | Includes patient-data, credential, private-file, or staff/admin compromise risk. |

## Synthetic Test Plan

Synthetic tests must use safe payloads only. They must not use real incidents,
patient data, provider secrets, private contacts, or response bodies.

| Test event name | Purpose | Allowed payload fields | Forbidden payload fields | Expected acknowledgement | Fallback if primary route fails |
| --- | --- | --- | --- | --- | --- |
| `synthetic-monitoring-route-test` | Prove primary route delivery and acknowledgement. | Environment category, severity, test marker, timestamp, source category, safe check label. | Webhook URLs, emails, phone numbers, patient data, response bodies, cookies, tokens, connection values, private route names. | Primary route acknowledges within approved test window. | Send the same sanitized test marker through the approved backup route and record primary failure as blocker. |
| `synthetic-slow-http-200-test` | Prove slow-response policy routes correctly. | Public endpoint label, safe latency class, threshold category, severity, test marker. | Full URL with private query strings, response body, headers containing cookies, patient identifiers. | Route owner confirms severity and no sensitive fields. | Escalate to backup route and leave slow-response alert readiness blocked. |
| `synthetic-deploy-failure-test` | Prove deploy failure notification path without causing a real deploy failure. | Simulated deploy failure label, environment category, severity, revision category, test marker. | Full logs, environment dumps, secrets, provider account IDs if sensitive. | Technical operator or backup acknowledges and classifies. | Backup route must acknowledge; missing acknowledgement blocks launch. |
| `synthetic-dependency-critical-test` | Prove dependency advisory escalation path. | Public advisory placeholder, package name placeholder, severity, scan source, test marker. | Private GitHub settings dumps, tokens, credentials, patient data. | Dependency response owner or backup acknowledges. | Backup dependency owner route must acknowledge before readiness. |
| `synthetic-privacy-incident-test` | Prove SEV-1 privacy/security escalation without exposing data. | Severity, incident category, affected environment category, test marker, legal/privacy review needed flag. | Actual patient data, credential values, request bodies, raw logs, medical content. | Incident commander and legal/privacy reviewer path acknowledge. | Backup route and project owner escalation are invoked; readiness remains blocked if unacknowledged. |

## Safety Requirements

- No private route destinations in Git.
- No webhook URLs in Git.
- No private emails, phone numbers, pager IDs, or chat destination IDs in Git.
- No patient data in alert payloads.
- No secret values in alert payloads.
- No response bodies in public uptime alerts.
- No cookies, session identifiers, CSRF token values, authorization headers, or
  request bodies in alert payloads.
- No database/cache connection values in alert payloads.
- No provider API keys, DSNs, or tokens in Git.

## Acceptance Criteria

Alert-routing readiness cannot be claimed until:

- owner approves primary route outside Git;
- owner approves backup route outside Git;
- SEV-1 through SEV-4 routing behavior is configured in the selected provider
  or notification system;
- synthetic primary route test is acknowledged;
- synthetic backup route test is acknowledged;
- at least one slow HTTP 200 synthetic policy test is reviewed;
- dependency critical advisory route is reviewed;
- privacy/security incident route is reviewed with legal/privacy escalation
  rules;
- payload review confirms no private contacts, patient data, response bodies,
  secrets, cookies, request bodies, tokens, connection values, private keys, or
  provider credentials are present;
- sanitized test outcome is recorded without destination values.

Current readiness:

```text
not ready
```
