# Patient review moderation

Patient reviews can also be managed directly in the clinic dashboard at
`/dashboard/reviews/`. See [Dashboard patient reviews](DASHBOARD_PATIENT_REVIEWS.md)
for that workflow, permissions and validation. The Django admin behavior
documented below remains available.

Base: `335620f289ae174080116c2e9507621a438fa7db` (GitHub `main`, verified by
fetch and `git ls-remote`). Branch: `codex/patient-review-moderation`.

## Staff behavior

For `PATIENT_PORTAL` reviews, open the existing review detail page from
`/admin/core/publicreview/`. Authorized staff see one visibility action and,
when they have delete permission, the existing permanent-delete workflow:

| Current state | Arabic action | English action | Result |
| --- | --- | --- | --- |
| Visible | إخفاء | Hide | Removes the review from public Home/Reviews pages and the published rating/count. |
| Hidden | إظهار | Show | Restores the review and its contribution to the published rating/count. |
| Either | حذف | Delete | Opens Django's existing confirmation page; a confirmed POST permanently deletes the review. |

Show also restores patient reviews deactivated through the legacy interface.
Staff cannot separately change active state, featured state, display order or a
raw approval checkbox for a patient review. Patient-authored name, rating, body,
language, source, source reference, ownership and review date are read-only.
The only editable detail-form field is the hidden signed revision token.

Patient rows in the shared list show a localized visibility status and omit
technical values/controls. Google/OTHER rows retain their existing approval,
active, featured and display-order inline controls, filters, detail form and
save behavior. The common table headers and filters continue to serve those
imported rows. Patient Hide/Show actions run from the detail page; the existing
permission-controlled bulk-delete confirmation remains available.

Patients can still edit and delete their own reviews. A valid patient edit
after Hide immediately republishes the review, following the existing owner
decision. No patient-portal or public aggregation implementation was changed.

## Security boundaries

- Existing revision salt, signed payload, current-row lookup and
  `select_for_update()` check remain in use. Detail saves and imported inline
  saves keep their surrounding database transactions.
- A stale Hide/Show fails after a patient edit or another moderator's action.
  Resubmitting the error page preserves the stale token; reloading and reviewing
  the latest content is required before the action can succeed.
- The patient action is restricted to `hide` or `show`. Missing actions, old
  checkbox payloads, missing/tampered tokens and tokens for another row fail.
- Patient saves allow only publication status, the update timestamp and the
  internal active-state restoration required by Show. Forged content and
  technical fields cannot enter the save. Patient inline forms have no editable
  moderation fields and cannot save a patient action.
- Django's existing staff/model permissions and CSRF middleware protect all
  writes. Change permission does not grant delete; delete permission does not
  grant Hide/Show. GET requests make no review changes.
- Single and bulk permanent deletion of patient reviews require the existing
  confirmation value `post=yes`. No alternate delete endpoint was added.

The form-rendering fix removes only named technical model fields instead of
iterating the admin-generated `Meta.fields`, which also contains the required
`review_version` field. That avoids the previous missing-field server error.

## Validation

All fixtures use synthetic identities and text. Development settings, SQLite
test databases and an empty `DATABASE_URL`/`CACHE_URL` isolate local validation
from production. No owner review dataset was supplied.

Focused review moderation, patient ownership/edit/delete, aggregate and public
page validation:

```sh
python manage.py test apps.core.test_review_moderation apps.patients.test_reviews apps.core.test_review_summary apps.core.test_public_showcase.PublicReviewShowcaseTests --noinput --verbosity 1
python manage.py check
python manage.py makemigrations --check --dry-run
git diff --check
```

The focused selection ran 59 tests: 58 passed, one optional owner-data test
skipped, no failures (2.569 seconds). Django checks found no issues; migration
checks found no changes. Ruff and whitespace checks passed.

The full-suite command is:

```sh
python manage.py test --noinput --verbosity 2
```

Its review-admin layout fixture exercises both visibility buttons, stale forms,
delete confirmation and mixed patient/imported lists in Arabic/English at 15
mobile, tablet and desktop viewports. Exact broader local and Linux CI outcomes
are recorded in the PR verification report.

Local environment: Windows, Python 3.14.2, Django 5.2.15. Docker's Linux engine
is unavailable, so local tests do not demonstrate PostgreSQL row-lock
concurrency or Redis coordination. Existing row-lock code is preserved.

No models, migrations, dependencies, OTP flows, storage, deployment configuration
or production data changed. This branch is for controller review; merging and
deployment are outside this task.
