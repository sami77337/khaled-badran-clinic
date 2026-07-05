# Batch 15 OPS 07 Status - Staging Latency Evidence and Mitigation Decision Pack

## Scope

BATCH-15-OPS-07 records a docs/evidence-only staging latency decision pack for
the existing public Render restricted staging endpoints.

This batch did not change application code, migrations, dependencies,
workflows, Render settings, external provider settings, secrets, credentials,
patient data, logs, or response bodies. It did not submit booking forms or any
other POST request. It used only bounded public GET checks for:

- `GET /health/`
- `GET /`

Production-ready status:

```text
no
```

## Branch and Base

- Working branch:
  `codex/batch-15-ops-07-staging-latency-decision-pack`
- Base branch: `main`
- Verified base commit:
  `e730ab882f678429d31bb8e95cddd9f90b7a9a62`
- Base subject:
  `Merge pull request #32 from sami77337/codex/batch-15-ops-06-monitoring-alerting-error-readiness`
- Repository remote:
  `sami77337/khaled-badran-clinic`
- Evidence date:
  `2026-07-05` local Asia/Amman workstation date
- Render restricted staging URL:
  `https://khaled-badran-clinic-staging.onrender.com`

## Documents and Workflow Inspected

- `docs/BATCH_15_OPS_03_STATUS.md`
- `docs/BATCH_15_OPS_06_STATUS.md`
- `docs/STAGING_UPTIME_LATENCY_MONITORING_EVIDENCE.md`
- `docs/OPERATIONS_MONITORING_ALERTING_PLAN.md`
- `docs/OPERATIONS_SIGNAL_MATRIX.md`
- `docs/MONITORING_ALERTING_READINESS.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/NEXT_BATCH.md`
- `docs/STAGING_VALIDATION_BLOCKERS.md`
- `docs/RELEASE_CHECKLIST.md`
- `.github/workflows/staging-uptime.yml`

## Repository State Commands

| Command | Result |
| --- | --- |
| `git status --short --branch` before branching | Clean `main` tracking `origin/main`. |
| `git rev-parse --verify HEAD` before branching | `e730ab882f678429d31bb8e95cddd9f90b7a9a62` |
| `git branch --show-current` before branching | `main` |
| `gh --version` | Exit 0; GitHub CLI `2.93.0` available. |
| `gh auth status` | Exit 0; authenticated for repository operations. No credential value is recorded here. |
| `git switch -c codex/batch-15-ops-07-staging-latency-decision-pack` | Exit 0. |

## Existing OPS-03 and OPS-06 Latency Evidence Reviewed

BATCH-15-OPS-03 recorded safe public GET evidence:

| Endpoint | HTTP status | Total time | Interpretation |
| --- | ---: | ---: | --- |
| `GET /health/` | 200 | `32.536797` seconds | Severe staging latency evidence. |
| `GET /` | 200 | `0.776475` seconds | Fast public home-page response in that spot check. |

BATCH-15-OPS-03 also documented additional `/health/` observations around
`22.4` seconds and `42.5` seconds, plus recent fast `/` observations around
`0.65` to `0.80` seconds.

BATCH-15-OPS-06 recorded safe public GET evidence:

| Endpoint | HTTP status | Total time | Interpretation |
| --- | ---: | ---: | --- |
| `GET /health/` | 200 | `32.828721` seconds | Severe staging latency evidence. |
| `GET /` | 200 | `31.897716` seconds | Severe staging latency evidence. |

The OPS-06 result matters because both approved public endpoints were slow in
the same spot-check window. That points away from an endpoint-specific
`/health/` implementation issue and toward whole-service or request-path
conditions during that observation.

## Staging Uptime Workflow Reviewed

The existing `.github/workflows/staging-uptime.yml` workflow:

- runs manually and twice daily at low frequency;
- checks only public GET `/health/` and `/`;
- follows redirects;
- discards response bodies;
- records only HTTP status, total response time, and final URL;
- uses `--max-time 75`;
- warns when response time exceeds `10` seconds;
- fails on non-200 status, curl failure, timeout, or response time over `60`
  seconds;
- does not check out the repository;
- does not use secrets or third-party Actions.

BATCH-15-OPS-07 did not modify the workflow.

## Bounded Public GET Checks

Safe public GET checks were repeated in four rounds with 20-second pauses
between rounds. This is enough to compare a first request with follow-up
requests in the same short observation window, while avoiding keep-alive
polling or aggressive traffic.

Response bodies were discarded with `--output NUL`. The command printed only
status, total time, and final URL for the approved endpoints.

Command shape:

```powershell
curl.exe --location --silent --show-error --output NUL --max-time 75 --write-out "status=%{http_code} time_total=%{time_total}s final_url=%{url_effective}`n" "https://khaled-badran-clinic-staging.onrender.com/health/"
curl.exe --location --silent --show-error --output NUL --max-time 75 --write-out "status=%{http_code} time_total=%{time_total}s final_url=%{url_effective}`n" "https://khaled-badran-clinic-staging.onrender.com/"
```

Observed metadata:

| Round | Endpoint | HTTP status | Total time | Final URL |
| ---: | --- | ---: | ---: | --- |
| 1 | `GET /health/` | 200 | `0.243988` seconds | `https://khaled-badran-clinic-staging.onrender.com/health/` |
| 1 | `GET /` | 200 | `0.123764` seconds | `https://khaled-badran-clinic-staging.onrender.com/` |
| 2 | `GET /health/` | 200 | `0.103777` seconds | `https://khaled-badran-clinic-staging.onrender.com/health/` |
| 2 | `GET /` | 200 | `0.116320` seconds | `https://khaled-badran-clinic-staging.onrender.com/` |
| 3 | `GET /health/` | 200 | `0.111525` seconds | `https://khaled-badran-clinic-staging.onrender.com/health/` |
| 3 | `GET /` | 200 | `0.106962` seconds | `https://khaled-badran-clinic-staging.onrender.com/` |
| 4 | `GET /health/` | 200 | `0.108991` seconds | `https://khaled-badran-clinic-staging.onrender.com/health/` |
| 4 | `GET /` | 200 | `0.169094` seconds | `https://khaled-badran-clinic-staging.onrender.com/` |

## Latency Observations

Current BATCH-15-OPS-07 observations:

- all eight approved public GET checks returned HTTP 200;
- all eight checks completed in under `0.25` seconds;
- the first `/health/` check was the slowest at `0.243988` seconds, still well
  below the documented warning threshold;
- follow-up checks did not show persistent slow behavior;
- final URLs stayed on the expected HTTPS staging host.

Comparison with OPS-03 and OPS-06:

- OPS-03 and OPS-06 provide real evidence of intermittent severe staging
  latency, including multiple responses over `30` seconds;
- BATCH-15-OPS-07 did not reproduce severe latency in the bounded four-round
  check;
- the current evidence distinguishes the observed session from persistent
  latency under a warmed or available service;
- it does not disprove future cold starts, platform queuing, deploy/restart
  effects, regional network issues, or runtime stalls.

## Likely Causes

The evidence supports this cautious interpretation:

- severe latency is intermittent, not persistent during the BATCH-15-OPS-07
  observation window;
- Render staging cold start or process wake-up remains a likely cause because
  previous responses were very slow while the current repeated checks were
  fast;
- platform routing, queueing, restart, deploy, low-resource service behavior,
  runtime startup delay, or transient network path delay are also plausible;
- the OPS-06 case where both `/health/` and `/` were slow suggests a
  whole-service or request-path condition rather than a database-heavy route;
- direct database or Redis latency is less likely for public `/health/`
  because that endpoint is public liveness and does not perform a readiness
  database check, but database/cache behavior remains unvalidated for private
  readiness and application workflows;
- an application-code regression causing persistent response slowness is less
  likely based on the fast repeated BATCH-15-OPS-07 results, but cannot be
  ruled out without provider metrics, logs, and production-like runtime
  validation.

No root cause is proven by public GET timing metadata alone.

## Production Impact

The previous `30` second staging responses are not acceptable as normal
production behavior. If similar latency occurred in production, it would:

- degrade patient trust before booking starts;
- make public liveness checks unreliable as user-facing performance evidence;
- risk false confidence if checks only look at HTTP 200 status;
- delay incident detection without latency thresholds and alert routing;
- create a poor clinic operations experience during deploys, restarts, or
  low-traffic periods.

The current fast BATCH-15-OPS-07 window is useful evidence, but it is not a
production SLA. Production launch remains blocked until latency behavior is
measured through approved monitoring, severe spikes are explained or mitigated,
and broader production-like staging validation passes.

## Mitigation Options

Owner/operator options before production launch:

| Option | What it addresses | Tradeoff or decision required |
| --- | --- | --- |
| Keep current staging posture and document the blocker | Accepts that staging latency may be intermittent while launch remains blocked. | Lowest effort; does not solve production cold-start risk. |
| Review Render service plan/runtime behavior | Confirms whether sleep, cold starts, restarts, region, resource limits, or deploy behavior explain the spikes. | Requires operator access outside Git; may require paid or different hosting settings. |
| Move production to a non-sleeping or always-warm runtime class | Reduces cold-start risk for patient-facing production traffic. | Requires owner approval and hosting cost decision; no repository change by itself. |
| Configure an approved external monitoring provider | Captures latency distribution, outage windows, and repeated failure alerts. | Requires provider selection, alert routing, retention, and privacy review. |
| Add tested alert routing for latency and uptime | Ensures slow 200 responses are treated as operational incidents. | Requires named recipients and tested primary/backup route outside Git. |
| Run operator-assisted Render runtime validation | Uses trusted staging shell/provider evidence to check strict smoke, readiness, logs, metrics, and deploy history without exposing secrets. | Requires sanitized evidence and operator access. |
| Tune runtime settings only after evidence | Adjusts worker count, process settings, startup path, or static behavior if metrics show runtime bottlenecks. | Should not be guessed from public GET timing alone. |
| Defer production promotion | Keeps the project in staging/validation until severe latency and monitoring blockers are closed or formally accepted. | Safest launch posture; delays go-live. |

The staging uptime workflow should not be converted into keep-alive polling.
If cold start is unacceptable, choose an explicit hosting/runtime mitigation
rather than hiding the issue with frequent repository checks.

## Decision Gates

Production-ready remains `no` until all of these latency-specific gates are
met or explicitly risk-accepted by the owner with a documented mitigation:

- the owner/operator identifies whether severe staging latency is expected
  cold-start behavior, platform behavior, deploy/restart behavior, network
  behavior, or an application/runtime issue;
- public `/health/` and `/` monitoring records status, total time, and final
  URL only, with no response bodies;
- approved monitoring shows no repeated severe `>30` second responses after
  the selected mitigation;
- owner-approved thresholds exist for warning, critical latency, and repeated
  failures;
- alert routing is configured and tested for slow public liveness/home-page
  responses;
- private readiness monitoring through `/health/ready/` is configured where
  possible without exposing internals;
- staging `deployment_smoke --strict` and production-like checks pass from a
  trusted operator shell;
- Render managed PostgreSQL/Redis, backup/restore, legal/privacy,
  load/concurrency, and production infrastructure blockers remain tracked
  separately and are not bypassed by fast public GET checks.

Suggested launch-blocking latency policy before production promotion:

- any single public response over `30` seconds requires review;
- repeated public responses over `10` seconds require mitigation or owner risk
  acceptance;
- production target thresholds must be lower than the interim staging workflow
  hard threshold of `60` seconds;
- HTTP 200 alone is insufficient for readiness if latency is severe.

## Conclusions

Public staging availability:

```text
observed for GET /health/ and GET /
```

Current BATCH-15-OPS-07 public staging latency:

```text
fast during bounded repeated checks
```

Historical staging latency:

```text
intermittent severe latency remains documented from OPS-03 and OPS-06
```

Likely root cause:

```text
not proven; cold start or platform/runtime/request-path delay is plausible
```

Mitigation decision:

```text
operator/owner decision required before production promotion
```

Production-ready:

```text
no
```

## Final Diff and Safety Checks

| Command | Result |
| --- | --- |
| `git diff --check` | Exit 0; no whitespace errors. Git displayed local line-ending normalization warnings only. |
| `git diff --cached --name-only` | Exit 0; staged files were the nine Markdown documents listed in this status file and companion evidence updates. |
| `git diff --cached --stat` | Exit 0; staged diff was docs-only: 9 files changed, 560 insertions, 35 deletions. |
| `git diff --cached --check` | Exit 0; no whitespace errors. |
| Cached scope check | Exit 0; staged scope was docs Markdown only. No app code, migrations, dependency files, workflow files, or Render configuration files were staged. |
| Cached secret pattern scan | Exit 0; no staged secret value patterns were found. |
| Production-ready affirmative scan | Exit 0; no affirmative production-ready pattern was found in the touched docs. |

The full application test suite was not rerun because this batch changed only
Markdown documentation and public GET evidence. No application code, templates,
models, migrations, settings, dependencies, or workflows changed.

## Remaining Blockers

- Severe staging latency over `30` seconds has been observed historically and
  lacks a proven root cause.
- No owner/operator decision exists for Render cold-start or runtime-class
  mitigation.
- No external monitoring provider is configured.
- No alert routing is configured or tested.
- No privacy-safe error-reporting provider is configured.
- No private `/health/ready/` provider-connected monitoring path is validated.
- No direct safe Render runtime command evidence is archived.
- No Render managed PostgreSQL restore drill has been completed.
- Backup retention, RPO, and RTO remain unapproved.
- Database, cache, backup, deploy, latency, and abuse alerts are not wired to
  a tested route.
- Legal/privacy approval remains incomplete.
- Load/concurrency validation remains incomplete.
- Production hosting, DNS, custom domain, and TLS remain incomplete.
- Production-ready remains no.

## Secret and Data Handling

No secrets, tokens, connection strings, private keys, patient names, emails,
phone numbers, appointment details, medical data, database dumps, logs,
response bodies, cookies, provider environment values, or private contacts were
recorded.

No active Render staging or production setting was changed. No external
monitoring, alerting, or error-reporting provider was configured. No patient,
appointment, upload, medical record, payment, WhatsApp, or automation data was
created.
