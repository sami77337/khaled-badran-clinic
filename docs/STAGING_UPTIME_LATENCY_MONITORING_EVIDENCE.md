# Staging Uptime and Latency Monitoring Evidence

## Evidence Classification

Correct label:

```text
interim repository-native staging uptime and latency evidence
```

Incorrect labels:

- production monitoring provider;
- production SLA;
- alert routing;
- privacy-safe error-reporting integration;
- Render service keep-alive polling;
- production readiness.

## Summary

BATCH-15-OPS-03 adds a lightweight GitHub Actions workflow and manual
PowerShell verification commands for the public Render restricted staging
endpoints:

- `GET /health/`
- `GET /`

The workflow is intentionally low frequency and limited to public GET checks.
It records HTTP status, total response time, and final URL only. It does not
print response bodies, use secrets, submit forms, check private routes, or
change Render settings.

Production-ready status:

```text
no
```

## Safety Boundary

Allowed:

- safe public GET requests to `/health/` and `/`;
- redirect following;
- status, response-time, and final-URL observation;
- warning on slow staging responses;
- failure on non-200 status, timeout, transport failure, or hard latency
  threshold breach.

Not allowed and not performed:

- booking POSTs;
- patient data creation;
- staff, admin, patient-account, portal-private, or private readiness routes;
- response-body logging;
- credentialed requests;
- private Render environment inspection;
- Render setting changes;
- paid external monitoring-provider configuration;
- alert-route setup;
- keep-alive polling.

## GitHub Actions Workflow

Workflow file:

- `.github/workflows/staging-uptime.yml`

Triggers:

- manual `workflow_dispatch`;
- scheduled twice daily at `05:17` and `17:17` UTC.

The schedule is intentionally low frequency. It is evidence collection, not an
attempt to keep the Render service warm.

Implementation:

- uses built-in `curl` on `ubuntu-latest`;
- does not check out repository contents;
- does not use secrets;
- does not use third-party Actions;
- follows redirects with `--location`;
- writes response bodies to `/dev/null`;
- uses `--max-time 75`;
- prints only HTTP status, total response time, and final URL.

Checked endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `https://khaled-badran-clinic-staging.onrender.com/health/` | Public liveness observation. |
| GET | `https://khaled-badran-clinic-staging.onrender.com/` | Public home-page availability observation. |

Workflow interpretation:

| Observation | Workflow result |
| --- | --- |
| HTTP status is `200` and response time is at or below `10` seconds | Pass. |
| HTTP status is `200` and response time is over `10` seconds up to `60` seconds | Pass with warning. |
| HTTP status is `200` and response time is over `60` seconds | Fail. |
| HTTP status is not `200` | Fail. |
| DNS, TLS, connection, timeout, or curl transport failure | Fail. |

The hard `60` second threshold is a staging evidence threshold, not a
production target. A healthy production target should be much lower and must be
defined through the approved monitoring provider and owner/operator review.

## Manual PowerShell Verification

Run these commands from a trusted local PowerShell session when manual
script-free evidence is needed.

Health endpoint:

```powershell
curl.exe --location --silent --show-error --output NUL --max-time 75 --write-out "status=%{http_code} time_total=%{time_total}s final_url=%{url_effective}`n" "https://khaled-badran-clinic-staging.onrender.com/health/"
```

Home page:

```powershell
curl.exe --location --silent --show-error --output NUL --max-time 75 --write-out "status=%{http_code} time_total=%{time_total}s final_url=%{url_effective}`n" "https://khaled-badran-clinic-staging.onrender.com/"
```

These commands do not print response bodies.

Manual interpretation:

| Observation | Meaning |
| --- | --- |
| `status` is not `200` | The public staging endpoint failed the check and needs investigation. |
| `time_total` is over `10` seconds | Slow staging response; record as a warning and compare with recent observations. |
| `time_total` is over `30` seconds | Severe staging latency evidence; likely cold-start or platform/runtime delay, and not acceptable as normal production behavior. |
| Timeout, DNS failure, TLS failure, or connection failure | The endpoint was unavailable from that client at that time. |

Do not repeat these commands aggressively. They are for manual evidence and
diagnosis, not for keeping the staging service awake.

## Latency Observations

Current documented staging examples:

| Endpoint | HTTP status | Observed response time | Interpretation |
| --- | ---: | ---: | --- |
| `GET /health/` | 200 | `32.536797` seconds during BATCH-15-OPS-03 spot check | Severe staging latency evidence. |
| `GET /health/` | 200 | about `22.4` seconds | Slow staging response. |
| `GET /health/` | 200 | about `42.5` seconds | Severe staging latency evidence. |
| `GET /` | 200 | `0.776475` seconds during BATCH-15-OPS-03 spot check | Fast public home-page response in the observed check. |
| `GET /` | 200 | about `0.65` to `0.80` seconds | Recent fast public home-page response range. |
| `GET /health/` | 200 | `32.828721` seconds during BATCH-15-OPS-06 spot check | Severe staging latency evidence. |
| `GET /` | 200 | `31.897716` seconds during BATCH-15-OPS-06 spot check | Severe staging latency evidence for the public home page. |

These are staging observations only. They are not a production SLA and do not
prove root cause.

The repeated slow `/health/` examples matter because `/health/` is a public
liveness endpoint and does not perform a database readiness check. Slow
liveness responses may indicate cold start, worker startup delay, platform
queuing, network latency, process saturation, runtime stalls, or other
staging/runtime conditions. The new workflow records those cases without
hiding them as long as they stay under the hard staging threshold.

## What This Evidence Proves

This evidence proves only that the repository now has:

- a safe public staging GET checker;
- a manual trigger for ad hoc checks;
- a low-frequency scheduled check;
- basic latency warnings;
- a documented hard latency threshold for staging evidence;
- manual PowerShell commands for local verification;
- documentation of recent slow staging liveness observations.

## What This Evidence Does Not Prove

This evidence does not prove:

- production uptime;
- production latency;
- production SLA compliance;
- full monitoring-provider configuration;
- alert routing or paging;
- privacy-safe error-reporting integration;
- database readiness;
- shared-cache readiness;
- Render managed PostgreSQL restore readiness;
- load or concurrency readiness;
- legal/privacy approval;
- production launch readiness.

## Required Conclusions

Repository-native staging uptime workflow:

```text
added
```

Full monitoring provider:

```text
incomplete
```

Alert routing:

```text
incomplete
```

Privacy-safe error reporting:

```text
incomplete
```

Render cold-start/latency:

```text
observed and tracked
```

BATCH-15-OPS-06 spot-check conclusion:

```text
public GET availability observed, but severe staging latency remains
```

Production-ready:

```text
no
```

## Secret and Data Handling

No active Render staging settings were changed. No Render environment dump,
full Render log, credential value, connection string, private key, request
body, cookie value, or operational secret was recorded.

No booking POST was submitted. No patient, appointment, medical, upload,
payment, WhatsApp, or automation data was created. No real patient data was
used.

This document intentionally avoids secret values and connection strings. It may
mention forbidden labels such as `DATABASE_URL`, `CACHE_URL`, `SECRET_KEY`,
password, token, and private key only as categories or policy boundaries. No
values for those labels are recorded.
