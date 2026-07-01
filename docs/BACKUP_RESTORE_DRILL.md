# Backup and Restore Drill

Batch 11 synthetic-only backup and restore drill plan for Dr. Khaled Badran
Clinic.

This document does not create backups, restore databases, store credentials, or
handle real patient data. It defines the evidence and commands a future
operator should use in restricted staging.

## Drill Rules

- Synthetic data only.
- PostgreSQL only for the real drill.
- No real patient names, phone numbers, emails, medical notes, reports,
  images, audio, video, WhatsApp messages, or payment data.
- No backup files, database dumps, credentials, private keys, logs, or restore
  output containing sensitive data in Git.
- Evidence that contains operational details must be stored outside Git.
- Restore into an isolated restore-test database first.
- Do not run destructive production actions without owner approval.

## Synthetic Data Setup

Allowed setup:

```bash
python manage.py seed_public_content
python manage.py seed_booking_demo
```

Optional synthetic records may be created only in restricted staging or a
restore-test environment. They must be clearly fake.

Do not use real patient data for backup, restore, screenshots, logs, or drill
evidence.

## PostgreSQL Backup Command Placeholder

Generic placeholder only:

```bash
pg_dump --format=custom --file=<backup-file-outside-git>.dump <database-name>
```

Provider-specific backups may be used, but the operator must still prove a
restore path.

Do not paste real:

- database URL,
- database password,
- hostname,
- user,
- backup storage path,
- encryption key.

## Restore-Test Database Process

1. Create an isolated restore-test database outside production.
2. Restore the backup into that database.
3. Configure a trusted local or staging shell to point at the restore-test
   database using environment values outside Git.
4. Confirm `DJANGO_SETTINGS_MODULE` is production-like if testing staging
   readiness.
5. Confirm `CACHE_URL` points to a safe staging/local shared cache.
6. Run validation commands.
7. Record evidence outside Git.
8. Destroy the restore-test database when the drill is complete and approved.

Generic placeholder:

```bash
pg_restore --dbname=<restore-test-database-name> <backup-file-outside-git>.dump
```

## Post-Restore Validation Commands

Run from the restored environment:

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py check
python manage.py check --deploy
python manage.py deployment_smoke --strict
python manage.py deployment_smoke --json
python manage.py project_status_report
python manage.py project_status_report --json
python manage.py production_settings_report
python manage.py production_settings_report --json
```

Run tests only when the restore-test database is disposable or Django is allowed
to create and destroy a separate test database:

```bash
python manage.py test
```

## Expected Restore Evidence

Record outside Git:

- drill date and time,
- environment name,
- application revision,
- migration state,
- backup identifier,
- restore-test database identifier,
- operator name or role,
- backup start/end time,
- restore start/end time,
- validation command results,
- smoke status,
- settings report backend categories,
- known warnings,
- failure notes,
- cleanup confirmation,
- RPO/RTO observations.

Evidence must not include secrets, connection strings, patient data, raw tokens,
private media, or sensitive logs.

## What Not to Store in Git

Never store:

- `.env`,
- database dumps,
- backup files,
- real `DATABASE_URL`,
- real `CACHE_URL`,
- database passwords,
- encryption keys,
- restore logs with secrets,
- patient exports,
- screenshots with patient data,
- private media,
- provider console output with credentials.

## Rollback Decision Tree

If validation after restore fails:

1. Stop promotion.
2. Identify whether the failure is code, migration, data, database, cache,
   settings, proxy, or secret configuration.
3. If the issue is release code and no migration ran in production, roll back
   code to last known good revision.
4. If migrations ran, decide between forward fix, schema rollback, or database
   restore with owner review.
5. If data integrity is uncertain, preserve evidence and restrict writes before
   additional changes.
6. Re-run validation after any rollback or fix.
7. Do not launch or promote until smoke and settings reports are clean for the
   intended environment.

## Migration Rollback Caution

Migration rollback can be riskier than a forward fix, especially after data
shape changes. Do not reverse production migrations casually.

Before rollback:

- confirm backup availability,
- confirm restore path,
- review migration operations,
- assess data loss,
- involve a database specialist if needed,
- document owner approval.

## RPO and RTO Placeholders

These require owner approval before launch:

- Recovery Point Objective: `TBD`
- Recovery Time Objective: `TBD`
- Restore drill frequency: `TBD`
- Restore drill owner: `TBD`
- Backup retention schedule: `TBD`
- Backup verification owner: `TBD`

Do not invent legal or operational retention obligations without review.

## Failed Restore Incident Checklist

If restore fails:

- assign an incident owner,
- record exact timestamps,
- preserve failed command output with secrets removed,
- verify backup file integrity,
- verify database compatibility,
- verify app revision and migration state,
- verify environment values outside Git,
- try restore into a fresh isolated database if corruption is suspected,
- escalate to the hosting/database provider if needed,
- do not overwrite production data,
- update the incident timeline,
- define a retest owner and due date.

## Current Batch 11 Status

This drill is planned, not executed. Backup/restore readiness remains partial
until a synthetic PostgreSQL restore drill is completed and evidence is reviewed
outside Git.

Design status: No design work performed by Codex.
