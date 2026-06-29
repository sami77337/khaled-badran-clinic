# Backup and Restore Runbook

This runbook defines expectations for future staging and production operators. It does not configure a provider, create backups, restore data, or store credentials.

## Scope

Covered:

- PostgreSQL logical backups for application data.
- Restore drills for staging and production-like validation.
- Pre-migration and post-migration safety steps.
- Backup encryption, access control, and retention placeholders.
- Future private media backup expectations before uploads are implemented.

Not covered:

- Provider-specific backup products.
- Real credentials, keys, database URLs, or patient data.
- Public file uploads or private media implementation.

## Backup Inventory

Required before launch:

- PostgreSQL application database.
- Deployment configuration stored outside Git.
- Static release artifact or source revision reference.
- Future private media storage, once uploads are implemented.

Do not back up into Git:

- `.env` files.
- Database dumps.
- Real credentials.
- Patient data exports.
- Medical uploads, reports, images, videos, or audio files.
- Logs containing sensitive operational or patient information.

## PostgreSQL Logical Backup Expectations

Use PostgreSQL logical backups for portable restore drills. A future operator may use provider-managed backups as the primary mechanism, but at least one logical backup and restore drill should be tested before launch.

Generic example only, not a provider-specific instruction:

```bash
pg_dump --format=custom --file=backup-file.dump database-name
```

Requirements:

- Run backups from a trusted operator environment.
- Store backup files outside the application repository.
- Encrypt backups at rest.
- Limit backup access to authorized operators.
- Monitor backup job success and failure.
- Record backup timestamp, source environment, application revision, and schema migration state.

## Restore Drill Schedule

Before public launch:

- Complete one full restore drill from the latest backup into an isolated staging or restore-test database.
- Confirm the restored app starts with production-like settings.
- Run smoke checks against the restored database.

Recurring schedule placeholder:

- Restore drill frequency: `TBD`.
- Restore drill owner: `TBD`.
- Evidence location: `TBD, outside Git if it contains sensitive data`.

## Pre-Migration Backup

Before any production migration that changes important tables:

1. Confirm the release artifact and migration files are reviewed.
2. Confirm a rollback plan exists.
3. Confirm no destructive seed command will run.
4. Take a fresh backup or verify a recent backup within the accepted recovery window.
5. Record backup identifier, time, operator, and source revision.
6. Confirm backup encryption and access controls.
7. Confirm restore instructions are available to the deployment operator.

For staging, use synthetic or demo data only. Staging must not contain real patient data.

## Migration Execution Expectations

Migrations should be a controlled deployment step, not a side effect of application process startup.

Recommended validation sequence:

```bash
python manage.py migrate --check
python manage.py check
python manage.py check --deploy
python manage.py deployment_smoke --strict
```

If the Django version or deployment target does not support `migrate --check`, use a reviewed equivalent migration-plan check.

## Post-Migration Validation

After migration:

- Run `python manage.py deployment_smoke --strict`.
- Verify `/health/` through the intended public route.
- Verify `/health/ready/` through the private/internal monitoring path.
- Verify public booking pages render.
- Verify staff appointment pages still require staff authentication.
- Verify no patient portal, upload, WhatsApp webhook, payment, medical-record, or medical automation route was introduced by the release unless explicitly approved in a later batch.
- Review application logs for migration, startup, and request errors.

## Backup Encryption

Backups must be encrypted at rest. Encryption keys must be stored outside Git and restricted to authorized operators.

Key handling requirements:

- Do not store encryption keys beside backup files.
- Do not paste keys into tickets, docs, chat, or commit messages.
- Rotate keys according to the future operations policy.
- Record who can decrypt backups.

## Access Control

Backup access should follow least privilege.

Required controls:

- Named operator accounts only.
- No shared admin accounts.
- Access review schedule: `TBD`.
- Offboarding procedure: `TBD`.
- Backup download/export audit trail: `TBD`.

## Retention Policy Placeholder

Retention must be approved by the project owner and reviewed with legal/privacy counsel before launch.

Placeholder:

- Daily backup retention: `TBD`.
- Weekly backup retention: `TBD`.
- Monthly backup retention: `TBD`.
- Legal hold process: `TBD`.
- Deletion verification process: `TBD`.

Do not invent or assume legal retention obligations. Legal/privacy counsel review is required.

## Future Private Media Backup Strategy

Uploads are not implemented yet. Before uploads are added:

- Design private storage with authenticated access checks.
- Ensure medical files are not served from public static or media URLs.
- Define private media backup scope.
- Test restore of both database rows and private media objects together.
- Define malware/content-type scanning expectations.
- Define media retention and deletion-review policy.
- Prevent public caching of sensitive medical files.

Until that design exists, no upload feature should be implemented.

## Emergency Restore Outline

Use this outline only after the incident owner approves a restore.

1. Declare incident severity and assign an incident owner.
2. Stop or restrict writes if continuing writes could worsen data loss.
3. Preserve evidence and current database state when safe.
4. Identify the restore target time and backup identifier.
5. Restore into an isolated environment first when feasible.
6. Validate schema, application startup, health, readiness, and smoke checks.
7. Decide whether to restore in place, create a new database, or roll back the release.
8. Rotate credentials if compromise is suspected.
9. Communicate status through the approved incident channel.
10. Record final recovery time, data-loss estimate, and follow-up actions.

## RPO and RTO Placeholders

These values must be approved before launch:

- Recovery Point Objective (maximum acceptable data loss): `TBD`.
- Recovery Time Objective (maximum acceptable downtime): `TBD`.
- Restore drill target duration: `TBD`.
- Backup verification owner: `TBD`.

## Validation Commands

Run these only against a safe environment:

```bash
python manage.py check
python manage.py check --deploy
python manage.py deployment_smoke --strict
```

Do not claim production or staging restore readiness until a real restore drill has been completed and recorded.
