# Patient review moderation in the clinic dashboard

Continued on `fix/dashboard-patient-review-moderation`, based on merged main
`d58209e496fa8590c91ad27b998f00c746d5a8be` (PR #67).

## Staff workflow

Open **Patient Reviews / تقييمات المرضى** in the clinic dashboard sidebar or
the mobile More menu. The page is `/dashboard/reviews/`; English uses
`/dashboard/reviews/?lang=en`, following the existing dashboard language scheme.

The page displays patient-submitted reviews, newest first, with a public display
name, review date, rating, text and Visible/Hidden status. There are 20 reviews
per page. The available actions are:

- **Hide / إخفاء:** remove the review from public Home/Reviews pages and the
  published rating/count.
- **Show / إظهار:** restore the review and its contribution to public results,
  including patient reviews deactivated through the old interface.
- **Delete / حذف:** open a separate confirmation page showing the exact review.
  Only its confirmed POST permanently deletes the review. The patient account
  and medical records are not deleted.

Staff cannot rewrite patient-authored content, rating, name, ownership or source,
or edit raw approval, active, featured or display-order fields. Imported
Google/OTHER reviews retain their existing Django admin workflow and cannot be
targeted by these dashboard routes. Patients retain their own edit/delete routes;
a valid patient edit still republishes the review immediately.

The page reuses the existing dashboard shell, record cards, buttons and responsive
styles. No new colors, typography, visual system, dependencies or migrations are
introduced.

## Access and integrity

| Route | Methods | Required access |
| --- | --- | --- |
| `/dashboard/reviews/` | GET | Active staff with review view, change or delete permission. |
| `/dashboard/reviews/<id>/visibility/` | POST | Active staff with review change permission. |
| `/dashboard/reviews/<id>/delete/` | GET, POST | Active staff with review delete permission. |

The sidebar entry follows those permissions. View-only staff cannot moderate;
change permission does not grant delete, and delete permission does not grant
Hide/Show. Anonymous requests redirect to staff login, and non-staff requests
are denied. Dashboard responses use the existing no-store/no-cache wrapper and
noindex template. The page exposes no account phone, email, medical information
or links to patient records.

Mutation requests use CSRF protection and lock the patient-review row inside a
database transaction. A signed token binds the displayed revision and exact
action. Missing, tampered, wrong-review, wrong-action, replayed and stale tokens
fail without a mutation. An edit or moderation from the patient portal or Django
admin invalidates a previously opened dashboard form. Error pages provide a
reload link without issuing replacement action tokens. Delete requires a
delete-specific token from its confirmation page plus `post=yes`.

Successful actions create an `AuditLog` row in the same transaction containing
the actor, review row ID and fixed action label only. Reviewer name, body,
patient account identifiers and object representations are not copied into
the audit entry.

## Validation

All fixtures are synthetic, using development settings and an isolated SQLite
test database with empty `DATABASE_URL` and `CACHE_URL`.

```powershell
python manage.py test apps.dashboard.test_patient_reviews apps.dashboard.test_patient_review_layout apps.core.test_review_moderation apps.patients.test_reviews apps.core.test_review_summary apps.core.test_public_showcase.PublicReviewShowcaseTests --noinput --verbosity 1
python manage.py check
python manage.py makemigrations --check --dry-run
python -m ruff check apps/dashboard/review_forms.py apps/dashboard/review_views.py apps/dashboard/urls.py apps/dashboard/test_patient_reviews.py apps/dashboard/test_patient_review_layout.py
git diff --check
```

The browser fixture uses the existing test browser launcher and checks visible,
hidden, empty, delete-confirmation and stale-form pages in both languages at 15
mobile/tablet/desktop viewports. It checks overflowing text, clipped/covered
actions, action target sizes and document direction. Screenshots can be written
to an ignored local folder by setting `KBC_REVIEW_QA_OUTPUT` for the test run.

Final validation on 2026-09-14 (Windows, Python 3.14.2, Django 5.2.15):

| Check | Result |
| --- | --- |
| Final focused review regressions (the command above without the layout-test label) | 77 tests: 76 passed, one optional owner-data skip, no failures; 2.765 seconds. |
| New dashboard browser fixture | 150 responsive cases passed, including long text and actionable controls. Arabic mobile/desktop screenshots were also inspected. |
| Complete repository suite: `python manage.py test --noinput --verbosity 1` | 1,099 tests: 1,092 passed, six skipped, one pre-existing Windows failure; 446.465 seconds. |
| Existing admin-review, guest/staff, upload and public-surface layout fixtures | Passed as part of the complete suite. |
| Django checks, migration drift, focused Ruff and staged whitespace checks | Passed; no migration changes. |

The full-suite failure is
`ProductionVapidAutoProvisionTests.test_auto_provision_persists_private_key_and_exposes_only_public_key`.
It expects POSIX file mode `0600`; Windows reports `0666`. The identical assertion
was reproduced with the single test on an untouched detached checkout of the
exact base `d58209e496fa8590c91ad27b998f00c746d5a8be`. Web Push implementation and
tests are unchanged. This is not recorded as a complete local suite pass.

SQLite does not validate PostgreSQL row-lock concurrency, no shared Redis was
configured, and Windows cannot run the existing symlink test without OS support.
No Linux CI run is claimed for this branch. No production records, provider
configuration, merge or deployment were changed during this continuation.
