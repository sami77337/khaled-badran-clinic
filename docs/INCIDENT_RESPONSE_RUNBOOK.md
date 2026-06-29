# Incident Response Runbook

This runbook is an operational outline for future staging and production use. It does not define legal obligations. Any suspected privacy, patient-data, or regulated-data incident requires legal/privacy counsel review.

## Severity Levels

`SEV-1 Critical`

- Confirmed or likely exposure of patient data, credentials, or private medical files.
- Active compromise of admin/staff access.
- Production outage affecting public booking or staff operations with no workaround.
- Failed migration causing data corruption or significant data loss risk.

`SEV-2 High`

- Suspicious admin activity not yet confirmed as compromise.
- Booking abuse or spam materially affecting clinic operations.
- Redis/cache outage affecting rate limiting in staging or production.
- Error spike affecting key workflows.
- Failed deployment that can be rolled back quickly.

`SEV-3 Medium`

- Degraded public pages, intermittent errors, monitoring gaps, or suspicious traffic below abuse thresholds.
- Staging-only failure that blocks release validation.

`SEV-4 Low`

- Documentation, checklist, or non-urgent operational follow-up.

## First 15 Minutes

1. Assign an incident owner.
2. Start an incident timeline with exact timestamps.
3. Identify affected environment: local, staging, or production.
4. Preserve relevant logs and deployment metadata without copying secrets into Git.
5. Stop the bleeding:
   - disable affected integration if possible,
   - restrict admin/staff access if suspicious,
   - pause deployment if release-related,
   - temporarily disable public booking only if abuse or integrity risk requires it.
6. Avoid destructive cleanup until evidence is preserved.
7. Escalate to legal/privacy counsel if patient data, credentials, private files, or regulated information may be involved.

## Common Incident Types

### Suspected Data Exposure

Containment:

- Restrict affected access paths.
- Rotate credentials if exposure may include secrets.
- Preserve logs, request IDs, deployment revision, and affected time window.
- Do not delete evidence.

Recovery:

- Patch exposure path.
- Verify staff-only and public-token route boundaries.
- Run security regression checklist.
- Run `python manage.py deployment_smoke --strict` in the affected production-like environment.

Review trigger:

- Legal/privacy counsel review is required before external statements or patient notifications.

### Suspicious Admin Access

Containment:

- Disable or lock suspicious accounts.
- Rotate passwords and sessions as appropriate.
- Review superuser and staff account list.
- Rotate application secret only with a planned procedure because sessions and signed data may be invalidated.

Evidence:

- Preserve access logs, admin login events, AuditLog entries, IPs, user agents, and timestamps.
- Do not paste credentials or raw tokens into the incident timeline.

### Booking Abuse or Spam

Containment:

- Confirm whether abuse is per IP, phone number, or distributed.
- Review rate-limit settings and cache backend.
- Confirm `BOOKING_TRUST_X_FORWARDED_FOR` is disabled unless trusted proxy stripping is verified.
- Temporarily reduce booking quotas only after owner approval.

Recovery:

- Confirm cache is shared in production-like environments.
- Verify public booking still uses hashed rate-limit identities.
- Preserve sample request metadata without storing patient medical content.

### Outage

Containment:

- Check application process, database, cache, reverse proxy, DNS, TLS, and static serving.
- Use `/health/` for liveness and `/health/ready/` for private readiness.
- Avoid exposing internal diagnostics publicly.

Recovery:

- Roll back the release if the outage follows deployment and rollback is safer than forward fix.
- Run smoke checks after recovery.

### Failed Deployment

Containment:

- Stop further deploys.
- Identify last known good revision.
- Confirm whether migrations were applied.
- Avoid running seed commands in production unless explicitly approved.

Recovery:

- Roll back code when safe.
- Roll forward only with a reviewed fix.
- Validate with `check --deploy` and `deployment_smoke --strict`.

### Database Migration Failure

Containment:

- Stop writes if data integrity is at risk.
- Preserve current database state and migration output.
- Confirm latest pre-migration backup.
- Do not manually edit migration history without review.

Recovery:

- Restore to a separate environment first when feasible.
- Use a database specialist for partial migration recovery.
- Run post-migration validation before returning traffic.

### Redis or Cache Outage

Containment:

- Confirm whether rate limiting is degraded.
- Keep public booking rate-limit behavior conservative.
- Do not switch production to LocMemCache as a silent workaround.

Recovery:

- Restore shared cache service.
- Confirm `deployment_smoke --strict` passes.
- Test booking IP and phone quotas.

### Error Spike

Containment:

- Identify endpoint, release revision, exception class, and request pattern.
- Confirm no secrets or patient medical content are being logged.
- Disable affected feature only if needed to protect safety or data integrity.

Recovery:

- Patch, roll back, or add defensive validation.
- Add regression tests for the error path.

### Compromised Secret

Containment:

- Revoke or rotate the secret through the provider or secret manager.
- Restart affected app processes.
- Review logs for use of the compromised credential.
- Rotate dependent credentials if reuse is suspected.

Recovery:

- Confirm new secret is not committed.
- Confirm smoke output does not print secret values.
- Document rotation time and affected systems.

### Future WhatsApp Integration Incident Placeholder

No WhatsApp API sending or webhook exists in Batch 7. Before WhatsApp is implemented, incident handling must cover:

- webhook signature verification,
- consent and opt-out handling,
- message logging boundaries,
- cost abuse,
- token rotation,
- provider outage,
- accidental message sends.

### Future Patient Upload Incident Placeholder

No upload route exists in Batch 7. Before uploads are implemented, incident handling must cover:

- malware or unsafe file detection,
- private media access control failure,
- public URL exposure,
- file retention and deletion review,
- backup/restore of private media,
- patient visibility and staff audit trail.

## Communication

Internal communication should include:

- severity,
- owner,
- affected environment,
- current impact,
- containment actions,
- next update time.

Do not include:

- raw credentials,
- patient medical details,
- database URLs,
- cache URLs,
- cookies,
- access tokens,
- private files.

External communication must be reviewed by the project owner and legal/privacy counsel when patient data, credentials, private files, or legal obligations may be involved.

## Evidence Preservation

Preserve:

- deployment revision,
- environment name,
- relevant log excerpts with secrets removed,
- timestamps,
- affected routes,
- impacted accounts or record IDs when necessary,
- screenshots only if they do not expose sensitive patient data.

Do not preserve evidence in Git if it contains secrets, patient data, logs, or private files.

## Recovery Checklist

- Root cause identified or rollback completed.
- Secrets rotated if required.
- Data integrity reviewed if database writes were involved.
- `python manage.py check` passes.
- `python manage.py check --deploy` reviewed in production-like settings.
- `python manage.py deployment_smoke --strict` passes in the affected production-like environment.
- Monitoring is green.
- Staff access reviewed if admin compromise was suspected.
- Legal/privacy counsel review completed if triggered.

## Post-Incident Review

Complete a review after containment and recovery:

- timeline,
- root cause,
- impact,
- what detected the issue,
- what delayed response,
- tests or checks to add,
- documentation updates,
- owner and due date for each follow-up.

Do not close SEV-1 or SEV-2 incidents without owner approval.
