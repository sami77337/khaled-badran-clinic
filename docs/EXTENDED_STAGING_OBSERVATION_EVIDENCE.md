# Extended Staging Observation Evidence

## Purpose

BATCH-15-OPS-08 runs a bounded, low-frequency public staging observation
window for the approved Render staging endpoints. The goal is to add timing
evidence across a longer window without turning the check into aggressive
polling or a keep-alive mechanism.

This document records status, total time, final URL, and curl exit code only.
Response bodies were discarded.

Production-ready status:

```text
no
```

## Approved Endpoints

Only these endpoints were approved:

| Label | URL |
| --- | --- |
| `GET /health/` | `https://khaled-badran-clinic-staging.onrender.com/health/` |
| `GET /` | `https://khaled-badran-clinic-staging.onrender.com/` |

No private, staff, admin, patient, portal-private, readiness-private, booking
POST, or form submission endpoint was used.

## Observation Method

Method:

- 8 rounds total;
- 15 minutes between rounds;
- each round checks `/health/` once and `/` once;
- `curl.exe`;
- redirects followed;
- maximum time 120 seconds;
- response bodies discarded;
- recorded only round, local timestamp, endpoint label, HTTP status,
  `time_total`, final URL, and curl exit code.

Command shape:

```powershell
curl.exe -L -sS -o NUL --max-time 120 -w "%{http_code},%{time_total},%{url_effective}" "$Url/health/"
curl.exe -L -sS -o NUL --max-time 120 -w "%{http_code},%{time_total},%{url_effective}" "$Url/"
```

## Recovery Context

The first observation attempt was interrupted when PowerShell closed. Its
actual completed rows were preserved in
`%TEMP%\batch15_ops08_staging_observation_saved.csv` and were not used to fill
missing final rounds.

Interrupted attempt rows preserved:

| Round | Local timestamp | Endpoint | HTTP status | time_total | Final URL | Curl exit | Classification |
| ---: | --- | --- | ---: | ---: | --- | ---: | --- |
| 1 | 2026-07-13 03:07:33 +03:00 | `GET /health/` | 200 | 0.298842 | `https://khaled-badran-clinic-staging.onrender.com/health/` | 0 | Fast |
| 1 | 2026-07-13 03:07:33 +03:00 | `GET /` | 200 | 0.111871 | `https://khaled-badran-clinic-staging.onrender.com/` | 0 | Fast |
| 2 | 2026-07-13 03:22:33 +03:00 | `GET /health/` | 200 | 32.642334 | `https://khaled-badran-clinic-staging.onrender.com/health/` | 0 | Severe |
| 2 | 2026-07-13 03:23:06 +03:00 | `GET /` | 200 | 0.579227 | `https://khaled-badran-clinic-staging.onrender.com/` | 0 | Fast |
| 3 | 2026-07-13 03:38:06 +03:00 | `GET /health/` | 200 | 22.482062 | `https://khaled-badran-clinic-staging.onrender.com/health/` | 0 | Slow |
| 3 | 2026-07-13 03:38:29 +03:00 | `GET /` | 200 | 0.579988 | `https://khaled-badran-clinic-staging.onrender.com/` | 0 | Fast |

No interrupted or missing rounds were inferred.

## Safety Limits

Safety limits:

- public GET only;
- no response bodies;
- no credentials;
- no cookies copied into evidence;
- no session identifiers;
- no CSRF token values;
- no booking POSTs;
- no patient data creation;
- no private endpoints;
- no Render shell access;
- no Render settings changes;
- no provider logs;
- no database/cache checks;
- no aggressive polling;
- no use as keep-alive.

## Classification

| Classification | Rule |
| --- | --- |
| Fast | Under 1 second. |
| Moderate | 1 second to 5 seconds. |
| Slow | Over 5 seconds. |
| Severe | Over 30 seconds. |
| Timeout/failure | Curl transport failure, timeout, or missing status. |

When a response exceeds 30 seconds, classify it as severe even though it also
exceeds the slow threshold.

## Observation Rounds

The final complete observation ran from 2026-07-13 13:52:46 +03:00 through
2026-07-13 15:37:51 +03:00. Source rows were recorded in
`%TEMP%\batch15_ops08_staging_observation.csv`.

| Round | Local timestamp | Endpoint | HTTP status | time_total | Final URL | Curl exit | Classification |
| ---: | --- | --- | ---: | ---: | --- | ---: | --- |
| 1 | 2026-07-13 13:52:46 +03:00 | `GET /health/` | 200 | 32.537281 | `https://khaled-badran-clinic-staging.onrender.com/health/` | 0 | Severe |
| 1 | 2026-07-13 13:53:19 +03:00 | `GET /` | 200 | 0.995978 | `https://khaled-badran-clinic-staging.onrender.com/` | 0 | Fast |
| 2 | 2026-07-13 14:07:47 +03:00 | `GET /health/` | 200 | 0.312925 | `https://khaled-badran-clinic-staging.onrender.com/health/` | 0 | Fast |
| 2 | 2026-07-13 14:07:47 +03:00 | `GET /` | 200 | 0.313416 | `https://khaled-badran-clinic-staging.onrender.com/` | 0 | Fast |
| 3 | 2026-07-13 14:22:48 +03:00 | `GET /health/` | 200 | 32.762653 | `https://khaled-badran-clinic-staging.onrender.com/health/` | 0 | Severe |
| 3 | 2026-07-13 14:23:20 +03:00 | `GET /` | 200 | 0.728803 | `https://khaled-badran-clinic-staging.onrender.com/` | 0 | Fast |
| 4 | 2026-07-13 14:37:48 +03:00 | `GET /health/` | 200 | 0.369634 | `https://khaled-badran-clinic-staging.onrender.com/health/` | 0 | Fast |
| 4 | 2026-07-13 14:37:49 +03:00 | `GET /` | 200 | 0.159444 | `https://khaled-badran-clinic-staging.onrender.com/` | 0 | Fast |
| 5 | 2026-07-13 14:52:49 +03:00 | `GET /health/` | 200 | 22.898738 | `https://khaled-badran-clinic-staging.onrender.com/health/` | 0 | Slow |
| 5 | 2026-07-13 14:53:12 +03:00 | `GET /` | 200 | 0.684054 | `https://khaled-badran-clinic-staging.onrender.com/` | 0 | Fast |
| 6 | 2026-07-13 15:07:49 +03:00 | `GET /health/` | 200 | 0.430942 | `https://khaled-badran-clinic-staging.onrender.com/health/` | 0 | Fast |
| 6 | 2026-07-13 15:07:50 +03:00 | `GET /` | 200 | 0.365734 | `https://khaled-badran-clinic-staging.onrender.com/` | 0 | Fast |
| 7 | 2026-07-13 15:22:50 +03:00 | `GET /health/` | 200 | 22.538800 | `https://khaled-badran-clinic-staging.onrender.com/health/` | 0 | Slow |
| 7 | 2026-07-13 15:23:13 +03:00 | `GET /` | 200 | 0.713096 | `https://khaled-badran-clinic-staging.onrender.com/` | 0 | Fast |
| 8 | 2026-07-13 15:37:50 +03:00 | `GET /health/` | 200 | 0.598401 | `https://khaled-badran-clinic-staging.onrender.com/health/` | 0 | Fast |
| 8 | 2026-07-13 15:37:51 +03:00 | `GET /` | 200 | 0.159984 | `https://khaled-badran-clinic-staging.onrender.com/` | 0 | Fast |

## Interpretation

All 16 checks returned HTTP 200 with curl exit code 0 and the expected final
URLs.

Endpoint summary:

- `GET /health/`: 8 checks, 8 HTTP 200, 8 curl exit 0. Timing range was
  0.312925 seconds to 32.762653 seconds. Rounds 1 and 3 were severe, rounds 5
  and 7 were slow, and rounds 2, 4, 6, and 8 were fast.
- `GET /`: 8 checks, 8 HTTP 200, 8 curl exit 0. Timing range was 0.159444
  seconds to 0.995978 seconds. Every `/` check was fast.

The result does not show a persistent total outage during this window, but it
does show unresolved intermittent `/health/` latency while `/` stayed fast in
the same observation window. The severe `/health/` responses in rounds 1 and 3
and the slow `/health/` responses in rounds 5 and 7 mean the historical
OPS-03/OPS-06 severe-latency blocker remains open.

HTTP 200 alone is insufficient because a public endpoint can be technically
available while taking long enough to degrade patient-facing or monitoring
behavior. Latency must be evaluated separately from status.

## Limitations

This evidence is limited to:

- public GET checks only;
- one client/network path;
- no production SLA;
- no database readiness proof;
- no cache readiness proof;
- no load or concurrency proof;
- no private `/health/ready/` provider monitoring proof;
- no provider metrics;
- no alert routing;
- no error-reporting provider;
- no legal/privacy approval.

## Decision Gates Before Launch

Production launch remains blocked until:

- severe latency is explained, mitigated, or explicitly risk-accepted by the
  owner with monitoring and alerting in place;
- approved external monitoring records status, latency, and final URL only for
  public endpoints;
- alert routing is configured and tested;
- private readiness monitoring is configured where possible;
- Render managed PostgreSQL restore drill evidence exists;
- backup retention, RPO, and RTO are approved;
- legal/privacy approval is complete;
- load/concurrency validation is complete;
- production DNS/TLS and hosting evidence is complete.
