# Release Checklist

This checklist is for future local, staging, and production release validation. It does not deploy anything by itself.

## Environment Command Sequences

### Local Development

```bash
python manage.py check
python manage.py test
python manage.py deployment_smoke
```

Expected local smoke warnings are acceptable when they identify local-only settings such as DEBUG, SQLite, LocMemCache, or disabled HTTPS redirect.

### Staging

Staging must be production-like, restricted, and free of real patient data.

```bash
python manage.py migrate --check
python manage.py check
python manage.py check --deploy
python manage.py deployment_smoke --strict
python manage.py seed_public_content
python manage.py seed_booking_demo
```

Run tests in staging only when the staging database is disposable or the tests use a separate CI clone:

```bash
python manage.py test
```

If `migrate --check` is unavailable in the deployed Django version, use an equivalent reviewed migration-plan check.

### Production

```bash
python manage.py check --deploy
python manage.py deployment_smoke --strict
```

Production migration must happen only with a backup and rollback plan. Do not run destructive seed commands in production unless explicitly approved by the project owner.

## Pre-Merge Checklist

- Scope matches the approved batch.
- No patient portal, uploads, WhatsApp API sending/webhooks, online payments, medical records, or medical automation were added unless the batch explicitly approves them.
- No real secrets, credentials, patient data, logs, private files, or database dumps are committed.
- Public booking success URLs still use UUID `public_token` values.
- Numeric appointment success routes remain absent.
- Staff appointment pages and operations remain staff-only.
- Tests were added for changed behavior.
- `python manage.py makemigrations --check --dry-run` passes.
- `python manage.py check` passes.
- `python manage.py test` passes.

## Pre-Deploy Checklist

- Release revision is identified.
- Environment variables are configured outside Git.
- Staging has its own generated application secret.
- Staging and production use exact allowed hosts.
- CSRF trusted origins are set to HTTPS origins.
- PostgreSQL is configured for staging/production.
- Shared cache such as Redis is configured for staging/production.
- HTTPS and proxy behavior are reviewed.
- `BOOKING_TRUST_X_FORWARDED_FOR` remains false unless trusted proxy stripping is verified.
- Backup and rollback plan exists.
- Monitoring owner is assigned.
- Legal/privacy review status is known.

## Migration Checklist

- Migration files are reviewed.
- Backup is completed or verified within the approved recovery window.
- Restore path is known.
- `python manage.py migrate --check` or equivalent is reviewed before migration.
- Migration is run as a controlled step.
- Post-migration smoke checks run before traffic is considered validated.

## Smoke Checklist

- `python manage.py check` passes.
- `python manage.py check --deploy` is reviewed in production-like settings.
- `python manage.py deployment_smoke --strict` passes in production-like settings.
- `/health/` returns safe liveness.
- `/health/ready/` returns safe readiness through the private/internal path.
- Public booking pages render.
- Staff appointment pages require authentication and staff status.
- Smoke output does not print secrets, database connection strings, cache connection strings, passwords, tokens, cookies, or raw environment dumps.

## Rollback Checklist

- Last known good revision is identified.
- Database migration rollback strategy is reviewed before use.
- Restore from backup is available if data integrity is affected.
- Staff and patient-facing impact is communicated through approved channels.
- Rollback validation includes `check`, `check --deploy`, and `deployment_smoke --strict`.

## Monitoring Checklist

- Application logs are collected.
- Request errors are visible.
- Security warnings are visible.
- Backup failures alert an operator.
- `/health/` uptime monitoring is configured.
- `/health/ready/` private readiness monitoring is configured.
- Error reporting, if added later, has privacy scrubbing before activation.
- Alert routing is tested.

## Post-Deploy Checklist

- Smoke checks passed after deployment.
- Error rate is normal.
- Public pages render.
- Public booking flow loads through confirmation without creating test patient data in production.
- Staff appointment list/detail access rules are intact.
- No unexpected routes are exposed.
- Release notes and incident timeline are updated if anything failed.

## Pre-Portal Safety Gates

- no patient portal until staging smoke passes
- no uploads until private media design exists
- no WhatsApp until consent/logging/cost/security design exists
- no medical records until authorization/audit/patient visibility rules are tested

These gates are intentional blockers for future batches.
