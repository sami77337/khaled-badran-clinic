# Synthetic Restore Drill Evidence

## Evidence Classification

Correct label:

```text
local synthetic PostgreSQL backup/restore drill
```

Incorrect labels:

- real Render managed PostgreSQL restore drill;
- production restore drill;
- real patient-data restore;
- production readiness;
- launch approval.

## Summary

BATCH-15-OPS-02 completed a synthetic-only local PostgreSQL logical
backup/restore rehearsal on `2026-07-03`.

Result:

```text
passed
```

The drill used the repository-approved local Docker PostgreSQL/Redis harness.
It created a synthetic source database, seeded only public/demo setup data,
created a logical dump inside the local PostgreSQL container, restored it into
a separate restore-test database, verified the restored database, then removed
the generated artifact and local drill databases.

No active Render staging or production resource was accessed or changed.

## Safety Boundary

Allowed for this drill:

- local Docker PostgreSQL;
- local Docker Redis for smoke verification;
- local-only source and restore-test databases;
- repository seed commands that create public/demo setup data only;
- safe command outputs with counts, booleans, backend categories, and status
  only.

Not used or not performed:

- real Render database/cache connection values;
- real staging database contents;
- production resources;
- real patient data;
- provider backups;
- provider restore operations;
- Render settings changes;
- generated dump files committed to Git.

## Source Data

The synthetic source database was created locally and migrated from the current
application revision:

```text
a367d017354aedff1434998025c0fb44efb088b1
```

Source setup commands:

```bash
python manage.py migrate --noinput
python manage.py seed_public_content
python manage.py seed_booking_demo
```

The seed commands reported that no patients, appointments, WhatsApp messages,
uploads, secrets, or payments were created.

Safe source counts before dump:

| Category | Count |
| --- | ---: |
| clinic profiles | 1 |
| doctors | 1 |
| visit types | 9 |
| doctor schedules | 5 |
| system settings | 7 |
| patients | 0 |
| appointments | 0 |

## Backup and Restore Steps

PostgreSQL logical backup command category:

```text
pg_dump custom-format logical dump
```

Restore command category:

```text
pg_restore into a separate local restore-test database
```

Generated local artifact:

| Artifact | Result |
| --- | --- |
| Location during drill | local PostgreSQL container `/tmp` |
| Observed size | `67.3K` |
| Stored in repository | no |
| Committed to Git | no |
| Removed during cleanup | yes |

The restore command completed successfully with exit 0.

## Post-Restore Verification

The restored database was checked using local development settings with local
PostgreSQL and local Redis. The restored environment was not production-like,
and the results must not be treated as Render managed service evidence.

| Command | Result |
| --- | --- |
| `python manage.py makemigrations --check --dry-run` | Exit 0; no changes detected. |
| `python manage.py migrate --check` | Exit 0; no unapplied migrations. |
| `python manage.py check` | Exit 0; no system check issues. |
| `python manage.py check --deploy` | Exit 0 with 6 expected local-development deployment warnings. |
| `python manage.py deployment_smoke --strict` | Exit 0; 16 pass, 2 expected local warnings, 0 failures, 0 strict blockers. |
| `python manage.py deployment_smoke --json` | Exit 0; safe JSON only. |
| `python manage.py production_settings_report` | Exit 0; safe report showed PostgreSQL and Redis backend categories under development settings. |
| `python manage.py production_settings_report --json` | Exit 0; safe JSON only. |
| `python manage.py project_status_report` | Exit 0; safe counts showed 0 patients and 0 appointments. |
| `python manage.py project_status_report --json` | Exit 0; safe JSON only. |
| `python manage.py test` | Exit 0; 246 tests ran, OK. |

Expected local warnings:

- `DEBUG=True`;
- HTTPS redirect disabled locally;
- `check --deploy` also reported standard local-development HTTPS, cookie, and
  local secret-quality warnings.

These warnings are expected for this local-only drill and remain unacceptable
for production launch.

## Restored Data Counts

Safe restored counts:

| Category | Count |
| --- | ---: |
| clinic profiles | 1 |
| doctors | 1 |
| visit types | 9 |
| doctor schedules | 5 |
| system settings | 7 |
| patients | 0 |
| appointments | 0 |

The restored counts matched the source counts. No patient or appointment rows
were present before or after restore.

## Cleanup Verification

Cleanup completed after verification:

- generated logical dump removed from the local PostgreSQL container;
- synthetic source database dropped;
- restore-test database dropped;
- local compose containers and network stopped and removed;
- no repository dump or backup artifact created;
- no generated artifact staged for commit.

## Final Conclusions

Local synthetic restore drill:

```text
passed
```

Real Render managed PostgreSQL restore drill:

```text
incomplete
```

Real patient-data restore:

```text
not performed and not allowed
```

Backup retention, RPO, and RTO approval:

```text
blocked
```

Monitoring provider and alert routing:

```text
blocked
```

Legal/privacy approval:

```text
blocked
```

Production-ready:

```text
no
```
