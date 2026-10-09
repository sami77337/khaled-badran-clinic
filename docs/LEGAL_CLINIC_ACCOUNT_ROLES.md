# Doctor / Clinic Staff — two safe Django account roles

Implementation requested by owner on 2026-10-09 as part of legal/privacy
least-privilege closeout. This uses Django's existing `User`, `Group` and
model permissions. No parallel auth system, registration route, extra user
data table, new passwords, or new public form is introduced.

## Exactly two clinic operational account types

| Type | Django Group | Intended access |
| --- | --- | --- |
| Doctor / طبيب | `KBC Doctor` | Existing appointment/dashboard access; registered and guest clinical reply writes through `patients.change_consultation` and `patients.change_transientconsultation`; clinical records once their separate role-to-action gates are approved |
| Clinic Staff / طاقم العيادة | `KBC Clinic Staff` | Existing administrative appointment and clinic workflow access; **no clinical reply change permission** supplied by this role |

Both types use the same existing staff login and must have `is_staff=True`.
Patient registration cannot assign either group or set staff privileges.
Django `is_superuser` remains an exceptional technical/admin capability;
never use it for reception staff. A person must belong to exactly one KBC
clinic role; both/none are classified as *unassigned* by the role helper.

## Provisioning & non-destructive migration

`patients.0010_clinic_doctor_staff_groups` creates only two Django Group
definitions and the two existing native consultation change permissions
(if needed on a fresh database) and grants them to `KBC Doctor`. `KBC
Clinic Staff` gains no model permissions by default. It does **not**
enumerate or alter existing staff accounts, patient profiles, appointments,
group memberships, passwords or superuser flags. Rollback does not delete
previously used group assignments.

To classify an **existing verified account**, a trusted operator may use
`python manage.py assign_clinic_role --user-id <INTERNAL_ID> --role doctor`
for a dry run, then explicitly repeat with `--apply`. Use
`--role staff` for the clinic team. It is safe/idempotent to reassign
the same role or switch between the two. The command changes the two role
groups only, keeps other group memberships, requires a pre-existing
`is_staff=True` account, rejects patient-linked/unverified/inactive
accounts and refuses assigning a superuser as administrative-only staff. It never prints usernames or
credentials. A superuser can alternatively assign groups through Django
Admin, ensuring `is_staff` and the exclusive-group rule.

## Deployment sequencing — keep the doctor working

1. Deploy this group-provisioning PR first; it creates **no real accounts**
   or runtime access change. Verify migration, CI and read-only group state.
2. **Before merging PR #118**, privately identify the treating doctor's real
   staff account and assign `KBC Doctor`; identify admin-only staff and
   assign `KBC Clinic Staff` (not superuser). Confirm the doctor's
   `has_perm('patients.change_consultation')` and
   `has_perm('patients.change_transientconsultation')` both return true,
   and receptionist accounts have neither. No usernames, private
   screenshots, credentials or patient data in Git/chat.
3. Update PR #118 to require **Doctor** classification as well as the
   existing scoped model permission, run direct-service, POST, AR/EN and
   audio regression tests. Merge and deploy only once the real-account
   assignment is verified, to avoid locking out legitimate clinicians.
4. Clinical notes, patient records and private media read/write currently
   include staff-only routes. Separate role-to-action checks require
   case-specific authorization without breaking agreed administrative tasks.
   Their existing privacy boundaries continue unchanged until then.

The hosted Render Postgres connector cannot currently query production
accounts because the database is deliberately private. Do not modify the
IP allowlist just to inspect usernames or account permissions.

This role infrastructure does not constitute medical licensure, service
consent, approval to access every patient file, or final legal compliance.
