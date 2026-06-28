# Next Batch: Django Foundation

## Branch

Recommended branch:

```bash
git checkout -b feat/django-foundation
```

## Goal

Create the Django foundation only.

## Must Read First

- README.md
- docs/DECISIONS.md
- docs/PROJECT_SPECIFICATION_AR.md
- docs/CODEX_BUILD_PLAN.md

## Expected Output

- Django project structure.
- PostgreSQL-ready settings.
- templates/static structure.
- initial apps package.
- no booking logic yet.
- no WhatsApp logic yet.
- no patient record logic yet.

## Checks

```bash
python manage.py check
python manage.py test
```

## Stop Condition

Stop after the Django foundation runs successfully. Do not continue to models or booking in the same batch.
