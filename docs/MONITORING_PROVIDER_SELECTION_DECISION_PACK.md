# Monitoring Provider Selection Decision Pack

## Current Status

Status:

```text
provider not selected or configured
```

This pack defines provider selection requirements and owner decision options.
It does not endorse a vendor, create an account, configure checks, store
credentials, route alerts, add an SDK, change Render settings, or approve
production launch.

Production-ready status:

```text
no
```

## Candidate Provider Classes

The owner may evaluate provider classes, not vendor endorsements:

| Provider class | Purpose | Current status |
| --- | --- | --- |
| Uptime monitoring provider | Public availability and latency checks for `/health/` and `/`. | Not selected. |
| Error reporting provider | Privacy-safe exception/event aggregation after scrubber review. | Not selected. |
| Observability/APM provider | Broader traces, metrics, latency distribution, and runtime insight. | Not selected. |
| Hosting-provider native alerts | Platform service, deploy, database, cache, and backup alerts where available. | Not configured in repository evidence. |

The repository-native staging uptime workflow remains interim evidence only.
It is not a production monitoring provider and does not provide owner-approved
incident routing.

## Required Capabilities

Before a provider can be considered ready, the selected monitoring approach
must support:

- public uptime check for `GET /health/`;
- public uptime check for `GET /`;
- latency thresholds for slow HTTP 200 responses;
- repeated latency-over-threshold alerting;
- private readiness check support for `GET /health/ready/` where possible;
- incident notification routing to approved primary and backup routes;
- deploy failure visibility or integration;
- database/cache alert ingestion or provider-native alert visibility;
- backup success/failure or missing-backup alert visibility;
- retention controls for events and check history;
- access controls limited to approved operators;
- export or screenshot evidence that can be sanitized before entering Git;
- payload controls that avoid response bodies and sensitive request data.

## Privacy Requirements

Monitoring must follow these requirements:

- public uptime checks must not capture response bodies;
- checks must not submit forms or booking POSTs;
- checks must not create patients or appointments;
- checks must not access private, staff, admin, patient, or portal-private
  endpoints;
- monitoring payloads must not capture patient data;
- monitoring payloads must not capture secret values;
- provider access must be restricted to approved operators;
- event retention must be approved before launch;
- evidence entering Git must be sanitized and limited to status, timing, final
  URL, environment category, and pass/fail summaries.

## Decision Options

| Option | Description | What it can cover | What remains missing |
| --- | --- | --- | --- |
| Minimal external uptime provider only | Select a provider for public `/health/` and `/` status/latency checks. | Public availability and slow-response detection. | Alert routing still needs testing; error reporting, database/cache, backup, and deploy signals may remain separate. |
| Uptime plus alert routing | Add owner-approved primary and backup notification paths and synthetic alert test. | Public checks and incident reachability. | Privacy-safe error reporting and deeper observability remain future decisions. |
| Uptime plus alert routing plus privacy-safe error reporting | Add scrubbed exception/event reporting after privacy review. | Public checks, alert reachability, and application error visibility. | APM/deeper traces may remain deferred; legal/privacy must approve retention and access. |
| Stronger observability later | Add APM/tracing/log metrics after baseline launch blockers close. | Better root-cause and latency distribution insight. | Higher privacy review, cost, and operator overhead. |

The owner may choose a staged approach, but production launch cannot claim
monitoring readiness until the selected baseline is configured, tested, and
approved.

## What Codex Can Do

Codex can:

- document monitoring requirements;
- update safe repository docs;
- inspect repository workflows and plans;
- validate public metadata-only GET evidence when explicitly permitted;
- summarize status, latency, final URL, and pass/fail outcomes without
  response bodies;
- keep production-ready status as `no` while decisions remain open.

## What Codex Cannot Do

Codex cannot:

- sign up for a provider;
- store credentials;
- configure webhooks;
- configure alert destinations;
- approve provider contracts, costs, privacy terms, or retention;
- change Render settings;
- inspect private provider dashboards;
- access private endpoints or protected patient/admin routes;
- add an error-reporting SDK in this docs-only batch;
- approve legal/privacy readiness.

## Acceptance Criteria

Monitoring provider readiness cannot be claimed until all of these are true:

- provider class and provider are selected by the owner outside Git;
- public `/health/` and `/` checks are configured at an approved frequency;
- latency thresholds include slow HTTP 200 alerting;
- private `/health/ready/` monitoring is configured where possible, or the
  limitation is owner-accepted;
- retention and operator access controls are approved;
- alert routing is configured and tested through approved primary and backup
  routes;
- alert payload review confirms no response bodies, patient data, secrets,
  cookies, request bodies, database/cache connection values, provider keys, or
  private contact values are included;
- sanitized evidence is reviewed before entering Git;
- legal/privacy approval is complete for any error-reporting or observability
  event capture beyond public uptime metadata.

Current readiness:

```text
not ready
```
