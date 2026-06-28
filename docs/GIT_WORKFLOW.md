# Git Workflow

## Branches

- main: stable base branch.
- feat/django-foundation: Batch 1 foundation branch.
- Future batches should use a new feature branch after Batch 1 is merged.

## Local Commands After Remote Review Commits

If review commits are added remotely, sync local branch before continuing:

```bash
git pull
```

Then verify:

```bash
git status -sb
git log --oneline -5
```

## Commit Discipline

- One batch per branch or clear PR.
- Run checks before pushing.
- Do not commit .env, secrets, real patient data, or uploaded medical files.
