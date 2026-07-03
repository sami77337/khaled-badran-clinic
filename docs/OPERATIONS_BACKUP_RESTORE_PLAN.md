# Operations Backup and Restore Plan

## Purpose

This plan defines the production-oriented backup and restore readiness
expectations for Dr. Khaled Badran Clinic after restricted Render staging
became functionally reachable for bounded public GET evidence.

This is a planning document. It does not configure backup jobs, create backup
files, restore databases, change Render settings, store credentials, or approve
production launch.

Production-ready status:

```text
no
```

## Safety Rules

- Use synthetic data only for all drills before launch.
- Do not use real patient names, phone numbers, emails, appointment histories,
  medical notes, reports, images, audio, video, WhatsApp messages, payment
  data, or private files in drills.
- Do not store database dumps, backup files, restore logs, credentials,
  connection strings, private keys, or sensitive provider output in Git.
- Do not run destructive restore actions against active staging or production
  unless the owner explicitly approves the incident or drill procedure.
- Restore into an isolated restore-test database first.
- Keep evidence outside Git when it contains operational details, provider
  identifiers, logs, or sensitive metadata.

No real patient data may be used in backup or restore drills.

## What Must Be Backed Up

Required before launch:

- PostgreSQL application database.
- Deployment revision and release artifact reference.
- Provider configuration inventory stored outside Git.
- Migration state at backup time.
- Backup job configuration and schedule metadata outside Git.
- Future private media storage only after uploads/private media are designed
  and approved.

Do not back up into Git:

- `.env` files;
- database dumps;
- provider console exports;
- application credentials;
- backup encryption keys;
- logs containing sensitive information;
- real patient exports;
- private media;
- screenshots containing patient or credential data.

## PostgreSQL Backup Expectations

PostgreSQL is the authoritative store for the current application data model.
Before launch, operators must prove both backup creation and restore.

Minimum expectations:

- Enable provider-managed PostgreSQL backups where available.
- Use point-in-time recovery if the selected provider plan supports it.
- Keep at least one portable logical backup path for restore drills.
- Encrypt backups at rest.
- Restrict backup access to named authorized operators.
- Record backup timestamp, source environment, application revision, and
  migration state.
- Monitor backup job success and failure.
- Alert if no successful backup exists inside the approved recovery window.
- Test restore into an isolated database before relying on a backup policy.

Generic logical backup placeholder only:

```bash
pg_dump --format=custom --file=<backup-file-outside-git>.dump <database-name>
```

Generic restore placeholder only:

```bash
pg_restore --dbname=<restore-test-database-name> <backup-file-outside-git>.dump
```

Do not paste real hostnames, database URLs, usernames, passwords, storage
paths, or encryption keys into docs, issues, pull requests, chat, or commit
messages.

## Redis and Cache Backup Expectations

Redis/shared cache is not authoritative for the current application.

Current Redis/shared-cache responsibilities:

- Django cache backend;
- booking rate-limit counters;
- portal login, registration, and appointment-link rate-limit counters;
- short-lived cache values used by smoke checks and runtime behavior.

Current recovery position:

- Redis data does not need to be restored as source-of-truth application data.
- A Redis loss may reset or disrupt rate-limit counters.
- A Redis outage can weaken or break booking/portal throttling depending on
  backend behavior and must alert operators.
- Recovery should restore the cache service, verify connectivity, and confirm
  rate-limit behavior rather than restore old cache keys.

Before launch, operators must decide and test Redis outage behavior:

- fail closed;
- fail open only under explicit incident acceptance;
- temporary degraded operation with owner approval.

Do not silently replace production Redis with LocMemCache as a recovery
shortcut. LocMemCache does not provide shared rate limits across app processes.

## Media and Private Uploads Status

Uploads and private media are not implemented in the current release boundary.

Current status:

- no upload routes;
- no medical-record routes;
- no private media workflow;
- `MEDIA_PRIVATE_ROOT` is a placeholder only;
- no media restore drill is required for current implemented behavior.

Future upload/private media work must define before implementation:

- private storage provider;
- authenticated access checks;
- malware/content-type controls;
- no public URLs for sensitive medical files;
- backup scope for both database rows and private media objects;
- restore consistency checks between database rows and media objects;
- retention and deletion process;
- legal/privacy approval.

Until that exists, PostgreSQL is the only authoritative data store requiring a
restore drill for the current bounded application.

## Synthetic Restore Drill Procedure

Run this only in restricted staging or an isolated restore-test environment.

1. Confirm the drill owner, environment, application revision, and planned
   start time.
2. Confirm no real patient data is present in the source staging database.
3. Create or verify synthetic public content only.
4. Take a provider backup or logical PostgreSQL backup from the synthetic
   source database.
5. Store the backup outside Git with encryption at rest.
6. Create an isolated restore-test PostgreSQL database.
7. Restore the backup into the restore-test database.
8. Configure a trusted local shell or staging clone to point at the restore-test
   database using environment values outside Git.
9. Use production-like settings for staging validation where possible.
10. Point cache settings at a safe staging/local shared cache, or document the
    cache limitation if a shared cache is unavailable.
11. Run post-restore verification commands.
12. Record sanitized evidence outside Git.
13. Destroy the restore-test database after evidence is reviewed and cleanup is
    approved.

Do not run the drill against active production data before launch. Do not run
destructive restore commands against active staging while staging is serving
validation traffic unless the owner explicitly approves the test window.

## Post-Restore Verification Criteria

Required commands from the restored environment:

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py check
python manage.py check --deploy
python manage.py deployment_smoke --strict
python manage.py deployment_smoke --json
python manage.py production_settings_report
python manage.py production_settings_report --json
python manage.py project_status_report
python manage.py project_status_report --json
```

Run tests only when the database is disposable or Django is allowed to create
and destroy a separate test database:

```bash
python manage.py test
```

If a restored web service is available, verify by safe GET only:

- `GET /health/`
- `GET /`
- `GET /book/`
- `GET /en/book/`
- private/internal `GET /health/ready/` if the path is available through a
  restricted monitoring route.

Pass criteria:

- Django checks pass.
- Migration state is clean.
- `deployment_smoke --strict` exits successfully in production-like settings.
- Safe JSON reports contain only booleans, counts, categories, and status.
- `production_settings_report` shows PostgreSQL in the intended restore-test
  validation shape.
- Cache backend is Redis/shared cache when validating production-like staging,
  or the limitation is explicitly recorded.
- Public liveness and home routes return HTTP 200.
- Prohibited upload, medical-record, WhatsApp, payment, and medical automation
  surfaces remain absent.
- No command output or evidence includes secrets, connection strings, raw
  tokens, raw phone numbers, patient names, private media, or full logs.
- Any synthetic patients or appointments are clearly fake and approved for the
  drill context.

Stop criteria:

- real patient data is discovered;
- restore output includes secrets or connection strings;
- database integrity is uncertain;
- migrations fail;
- smoke strict fails;
- readiness fails after restore;
- error rate increases during a web-service restore test.

If real patient data is discovered during a drill, stop and follow the incident
response runbook and legal/privacy escalation path.

## Batch 15 OPS 02 Local Synthetic Drill Evidence

BATCH-15-OPS-02 completed a local synthetic PostgreSQL logical backup/restore
drill using the repository-approved local Docker service harness.

Recorded evidence:

- `docs/BATCH_15_OPS_02_STATUS.md`
- `docs/SYNTHETIC_RESTORE_DRILL_EVIDENCE.md`

Result:

```text
local synthetic restore drill passed
```

The drill created a local synthetic source database, applied migrations, seeded
only public/demo setup data, created a logical dump inside the local PostgreSQL
container, restored it into a separate local restore-test database, verified
migration state, smoke checks, safe reports, safe row counts, and the 246-test
suite, then removed the generated artifact and local drill databases.

This evidence proves only the local logical restore procedure concept. It does
not prove provider-managed backup behavior, Render managed PostgreSQL restore
behavior, production-like settings, backup retention, RPO, RTO, legal/privacy
approval, monitoring, alert routing, or production readiness.

## Rollback Boundaries

Rollback and restore are separate decisions.

Use code rollback when:

- the release is faulty;
- no irreversible migration or data corruption occurred;
- the last known good revision can run safely against the current schema.

Use database restore only when:

- data corruption or loss is confirmed or likely;
- forward repair is riskier than restoring;
- a backup within the approved recovery window exists;
- the owner approves the restore target and expected data-loss window.

Do not:

- restore over active production without owner approval;
- manually edit migration history without review;
- run destructive seed commands in production;
- assume migration rollback is safer than a forward fix;
- treat Redis flush or LocMem fallback as a full recovery strategy;
- restore future private media separately from database state once uploads are
  implemented.

If credentials or backup access may be compromised, rotate affected secrets
through the provider or secret manager before declaring recovery complete.

## Owner Checklist

Before launch, assign and record outside Git:

- backup owner;
- restore drill owner;
- backup access approver;
- backup storage location owner;
- backup encryption key owner;
- monitoring owner for backup job success/failure;
- incident owner for failed backup or failed restore;
- legal/privacy reviewer for retention and deletion policy.

Pre-launch checklist:

- automated PostgreSQL backup enabled;
- backup encryption confirmed;
- backup access restricted to named operators;
- backup success/failure alert configured;
- missing-backup alert configured;
- one synthetic PostgreSQL restore drill completed;
- restore evidence reviewed;
- RPO approved;
- RTO approved;
- retention schedule approved;
- deletion and legal hold process approved;
- no real patient data used in drills.

## Frequency Recommendations

These are operational recommendations until the owner and legal/privacy review
approve final policy:

- Automated PostgreSQL backups: at least daily before launch, with shorter
  intervals or point-in-time recovery if available and approved.
- Backup success review: daily during launch preparation.
- Missing backup alert: alert when no successful backup exists inside the
  approved recovery window.
- Restore drill before launch: required at least once using synthetic data.
- Restore drill after launch: repeat at least quarterly, and before high-risk
  migration work when feasible.
- Pre-migration backup: required before production migrations that can affect
  important data.
- Backup access review: at least quarterly and during staff/operator
  offboarding.

Final frequency, retention, RPO, and RTO values require owner approval and
legal/privacy review.

## Retention and Deletion Considerations

Retention remains blocked pending owner and legal/privacy approval.

Policy must define:

- daily backup retention;
- weekly backup retention;
- monthly backup retention;
- point-in-time recovery window, if supported;
- deletion request handling;
- legal hold process;
- backup purge verification;
- encrypted backup disposal;
- operator access audit trail;
- how restored environments are destroyed after drills;
- how future private media deletion aligns with backup retention.

Do not promise deletion timing or legal retention behavior until qualified
review is complete.

## Current Readiness Classification

Backup/restore readiness:

```text
partial, local synthetic drill passed
```

Reasons:

- runbooks and this operations plan exist;
- local validation commands pass under development settings;
- local Docker PostgreSQL/Redis evidence exists from earlier batches;
- local synthetic PostgreSQL logical backup/restore drill evidence exists;
- real Render managed PostgreSQL restore drill evidence does not exist;
- backup retention, RPO, and RTO are not approved;
- backup job monitoring is not configured;
- provider-specific backup and restore evidence is not recorded.

Production launch remains blocked.
