# Codex Batch Template — Khaled Badran Clinic

## Task

`BATCH-XX-...: <NAME>`

## Preflight

- `git status --short --branch`
- `git switch main`
- `git pull --ff-only origin main`
- record base SHA
- inspect open PRs
- create dedicated branch

Do not touch:
`feat/security-operations-release-evidence`

Read:
- `docs/CLINIC_DELIVERY_V1_SCOPE_LOCK.md`
- `docs/NEXT_BATCH.md`
- `docs/project-handoff/KBC_MASTER_HANDOFF_AR.md`

## Scope

Implement only:
- <ITEM>
- <ITEM>
- <ITEM>

Do not introduce:
- WhatsApp Business API
- payments
- AI diagnosis/treatment/triage/recommendations
- unrelated dependency upgrades
- unrelated production infrastructure
- real patient data
- public private-media links

## Privacy invariants

- private by default
- own patient approved visibility only
- public case requires consent + active
- no public PII
- no direct private media URL
- no real patient data in tests

## Acceptance criteria

1. <criterion>
2. <criterion>
3. Arabic + English behavior.
4. Responsive behavior where applicable.
5. Loading/empty/error states.
6. No regression to patient/staff/public boundaries.

## Validation

Run as applicable:

- `python --version`
- `python -m pip --version`
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py migrate --check`
- targeted tests
- `python manage.py test`
- `python -m pip check`
- `pip-audit -r requirements.txt --progress-spinner off` when dependency scope applies
- `git diff --check`
- `git diff --cached --check`
- staged secret/PII scan

## Git

One focused batch.
Commit.
Push.
Open Draft PR unless instructed otherwise.
Do not merge major dependency upgrades automatically.

## Required final report

1. branch
2. base SHA
3. final SHA
4. files changed
5. models/migrations
6. routes
7. behavior
8. privacy/security behavior
9. validation commands/results
10. remaining blockers
11. PR URL
12. safety confirmation

Never claim Production-ready unless a dedicated production-readiness batch proves it.
