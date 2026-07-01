# Staff Access Governance

Batch 11 staff/admin access governance plan for Dr. Khaled Badran Clinic.

This document does not create staff accounts, change permissions, add dashboard
features, or approve production access. It defines pre-launch governance
expectations.

## Current Staff-Only Access Model

Current staff appointment routes:

- `GET /staff/appointments/`
- `GET /staff/appointments/<appointment-id>/`
- `POST /staff/appointments/<appointment-id>/cancel/`
- `POST /staff/appointments/<appointment-id>/reschedule/`
- `POST /staff/appointments/<appointment-id>/arrived/`
- `POST /staff/appointments/<appointment-id>/complete/`
- `POST /staff/appointments/<appointment-id>/no-show/`

Current behavior:

- anonymous users redirect to Django admin login,
- authenticated non-staff users receive `403`,
- authenticated active staff users can access bounded appointment operations,
- state-changing staff operations use POST and CSRF,
- staff pages are no-cache,
- staff routes may use internal numeric appointment IDs only behind staff auth,
- public booking success remains UUID-token based.

Existing tests cover anonymous and non-staff access behavior for staff
appointment routes and operations.

## Django Admin Access Risk

Django admin is powerful and must be treated as high-risk.

Risks:

- broad model access,
- accidental exposure of patient/contact data,
- weak passwords,
- shared accounts,
- stale staff accounts after offboarding,
- excessive superuser count,
- lack of audit review.

Django admin must not be treated as a patient portal or public dashboard.

## Least-Privilege Pre-Launch Checklist

Before launch:

- list every staff/admin user,
- remove unused accounts,
- minimize superusers,
- assign staff access only to named individuals,
- verify each staff account has a legitimate role,
- confirm no shared accounts,
- confirm strong passwords,
- confirm offboarding process,
- review model admin permissions,
- confirm staff appointment operations remain bounded,
- confirm audit/status history remain staff-only.

## Staff Onboarding

Before creating a staff account:

1. Confirm role and access need.
2. Create a named account, not a shared account.
3. Require strong password.
4. Grant only required privileges.
5. Record account owner and creation date outside Git.
6. Explain no real patient data may be copied into tickets, docs, screenshots,
   or chat.
7. Confirm staff understands emergency and privacy boundaries.

## Staff Offboarding

When staff access is no longer needed:

1. Disable the account promptly.
2. Remove staff and superuser flags if account retention is required.
3. Rotate shared operational credentials if exposure is possible.
4. Review recent admin/staff activity.
5. Record offboarding date and operator outside Git.
6. Confirm no active sessions remain if the platform supports session review.

## Password Policy Expectations

Before launch:

- keep Django password validators enabled,
- require unique staff passwords,
- prohibit shared passwords,
- avoid sending passwords through chat or email,
- use password reset/onboarding process approved by owner,
- consider MFA through the hosting/admin access layer if available.

The app does not implement a custom staff MFA feature in Batch 11.

## Superuser Minimization

Superusers should be rare.

Before launch:

- identify every superuser,
- justify each one,
- remove superuser status where staff permissions are enough,
- assign an owner for periodic review,
- document emergency superuser creation and removal process.

## Audit Review Process

Current application audit logs record appointment-related operations. They are
not a full infrastructure audit trail.

Before launch:

- define audit review frequency,
- define who reviews staff appointment operations,
- define retention expectations,
- define escalation for suspicious activity,
- keep audit exports outside Git if they contain sensitive data.

## Emergency Access Process

Emergency access should be documented before launch:

- who can approve temporary access,
- how temporary access is created,
- how long it lasts,
- how it is removed,
- what evidence is recorded,
- when legal/privacy escalation is required.

Do not create permanent broad access for temporary incidents.

## No Shared Accounts Policy

Shared staff/admin accounts are prohibited.

Each staff user must have a named account. Shared accounts make audit trails
unreliable and complicate offboarding.

## Current Batch 11 Status

Staff/admin governance is documented. No new staff dashboard features were
implemented. Existing regression tests continue to cover anonymous and non-staff
blocking for staff appointment routes.

Design status: No design work performed by Codex.
