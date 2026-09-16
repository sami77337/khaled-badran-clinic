# OWNER-UX-01 — doctor / owner experience

Branch: `feat/doctor-owner-closeout`.
Verified batch base and preflight `origin/main`:
`382ff0576ab7669ae2c11adc41e2e89843a33907`.

This batch covers Dashboard password change, public copy management, and PWA
installation guidance. It does not implement Appointment Operations or OTP.
It does not modify WhatsApp reminder code, templates, eligibility, timing,
scheduling, or settings. No deployment or production data operation was run.

## Owner workflow

- **Change Password / تغيير كلمة المرور** is in the Dashboard sidebar footer.
  It accepts the current password and matching replacement fields, uses Django's
  password validators and hashing, and retains the current session.
- **Website Content / محتوى الموقع** replaces the previous Dashboard link to
  raw DoctorPageContent admin. Select Home, Doctor, Services, or Contact to edit
  presentation copy, or Doctor Biography to edit the existing profile fields.
  Blank overrides use approved defaults, shown as field placeholders.
- Doctor sections have Arabic/English titles and text, a numeric order (lower
  first), visibility, and exactly TEXT, LIST, CHIPS, or CARDS presentation.
  Built-in section bodies remain in DoctorPageContent; no owner text is migrated
  or replaced. An explicitly hidden section never renders fallback content.
- Add Section creates a custom **Doctor page** section, initially unpublished.
  Both titles and both content translations are required before publication.
  Lists, chips, and cards use one item per line. Archive removes the section
  from public display; clear Archive and enable visibility to restore it.
- Home retains its fixed layout and ordering. Its doctor preview, cases preview,
  reviews, and FAQ can be hidden. The hero and contact block remain present.
  Hiding a preview does not modify case consent, case publication, or reviews.
- Service category presentation text is editable. VisitType names, duration,
  prices, and instructions retain their existing source. ClinicProfile contact
  data and Doctor name/title/specialty are not duplicated in the editor.
- Legal, consent, security, authentication forms, booking validation, and patient
  portal operational text remain outside the editable-copy allowlist.

Saving updates currently visible content immediately. This is a plain-text
editor, with no HTML, JSON, CSS, template, link, or page-builder interface.
New markup and explicit links are rejected; templates also escape database
content, including legacy values written outside these forms. Public editing
must never be used for patient information.

## Permissions

The existing staff Dashboard boundary and Django model permissions apply.
Superusers already have the required permissions. Authorized staff editors need:

| Surface | Permissions |
| --- | --- |
| Own password | Authenticated staff; always the current user |
| Existing Doctor biography | `core.change_doctorpagecontent` |
| First DoctorPageContent record | `core.add_doctorpagecontent` |
| Built-in section settings | `core.add_doctorpagesection` on first save; `core.change_doctorpagesection` afterward, plus the appropriate DoctorPageContent permission |
| Custom sections | `core.add_doctorpagesection` to create; `core.change_doctorpagesection` to edit/archive/restore |
| Home/Doctor/Services/Contact copy | Both `core.add_publicsitecontent` and `core.change_publicsitecontent` |

View-only users can access the content index without gaining edit access. No
permissions are automatically granted by the migration. Saves use CSRF-protected
POST forms and write content-free AuditLog metadata. Dashboard responses use the
existing private/no-store/no-cache boundary; password fields are marked sensitive.

## Models, migration, and routes

`core.0006_publicsitecontent_doctorpagesection` creates two models:

- `DoctorPageSection`: Doctor relationship, built-in key or custom-section
  identity, bilingual title/custom content, presentation, order, visibility,
  archive flag, and update timestamp. Custom sections have a fixed Doctor-page
  surface. A conditional unique constraint prevents duplicate built-in keys per
  doctor. Built-in bodies remain solely in DoctorPageContent.
- `PublicSiteContent`: allowlisted copy key, bilingual optional override text,
  safe Home-section visibility, and update timestamp.

No data migration or changes to the DoctorPageContent schema are needed. Missing
rows preserve the previous approved content and composition.

Routes (English Dashboard UI uses `?lang=en`):

```text
/dashboard/account/password/
/dashboard/content/
/dashboard/content/copy/<page>/
/dashboard/content/doctor/bio/
/dashboard/content/doctor/sections/new/
/dashboard/content/doctor/sections/<section_key>/
```

Built-in section keys are server controlled; custom section edit keys are
`custom-<id>`. Every edit resolves against the existing active public Doctor.

## Install behavior

The compact Install App action appears in the public footer and Dashboard
sidebar footer. A retained `beforeinstallprompt` event is invoked only on a tap,
consumed once, and handles accepted/dismissed outcomes. Installed/standalone
windows suppress the action. There is no automatic modal or repeated nag.

iPhone and iPad show localized Share → Add to Home Screen → Add instructions,
with a Safari hint. Browsers without a deferred event show a short browser-menu
instruction. Native prompts remain subject to the browser's
[install criteria](https://web.dev/articles/install-criteria).

The existing root `/sw.js` worker is registered without modification. It still
handles push only, with no fetch handler, CacheStorage operations, or private-data
offline store. Installation does not request notification permission or create
a push subscription. The manifest and approved icons are unchanged.

## Validation evidence

Validation uses synthetic fixtures and isolated test databases. Browser QA uses
Django-rendered fixture pages in local headless Chromium; no real patient data,
provider messages, or production account is used. Native installation on a
physical Android/iPhone/iPad remains unverified.

Resumed closeout on 2026-09-16 using Windows, Python 3.14.2, Django 5.2.15,
Node 24.16.0, and local headless Chromium.

The final review corrected the Doctor biography and built-in section editor
placeholders: after an override has been saved, clearing it now shows the actual
approved fallback, including the existing Doctor biography when applicable.
Built-in titles also show their fallback. A regression exercises both languages,
clears saved overrides, and checks that the public page matches the editor hints.
The original `connection`, `ClinicalNote`, and `RecordMediaFolder` imports in
`apps/core/tests.py` were restored exactly from the batch base before delivery.
The final diff retains only the OWNER-UX-01 test changes in that file.

| Check | Result |
| --- | --- |
| `python manage.py test --noinput` | 1,141 tests in 475.932 seconds; 1,134 passed, six skipped, one existing Windows permission failure described below |
| `python manage.py test apps.core apps.dashboard --noinput` after import restoration | 408 tests in 53.647 seconds; 407 passed, one skipped, no failures |
| Owner browser QA included in the affected-app run | 66 AR/EN page/viewport combinations at 390, 768, and 1440 pixels; 12 installation runtime cases passed |
| `python manage.py check` | No issues |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `python manage.py migrate --check` | All local migrations already applied |
| `python manage.py deployment_smoke` | 16 checks passed, four expected local-development warnings, zero failures |
| Earlier Ruff check on changed/new non-migration Python files | Passed before restoring the three original unused imports; those baseline imports are intentionally retained in the final diff |
| Node syntax checks on the install script and owner browser test | Passed |
| `git diff --check` | Passed |
| Added-line secret/credential/PII pattern scan | Zero findings across 35 changed/new files |
| Protected-source scope comparison with the batch base | No changes to WhatsApp, patients, booking, records, notifications, clinic, service worker, manifest, or dependencies |

The full-suite run began before the final placeholder correction and its new
regression were added. The final 408-test affected-app run after import
restoration validates the delivered code, including that regression and browser
QA. The full suite was not repeated for the import restoration; no application
behavior changed in that delivery step.

The optional skipped affected-app check needs an externally supplied owner-approved reviews
fixture. It does not gate the owner UX tests. Smoke warnings concern local DEBUG,
SQLite, LocMemCache, and disabled HTTPS redirect. Screenshots were inspected for
the content index, bilingual mobile forms, password validation, doctor sections,
and iOS installation guidance; generated screenshots stay in ignored `.cache/`.

The existing notification test
`ProductionVapidAutoProvisionTests.test_auto_provision_persists_private_key_and_exposes_only_public_key`
fails on Windows because it expects POSIX mode `0600`, while Windows reports
`0666`. The same failure was reproduced in an isolated, clean checkout of the
unchanged base commit `382ff0576ab7669ae2c11adc41e2e89843a33907` (one of its two
notification auto-provision tests failed). That temporary checkout was removed.
No notification implementation or test was altered to suppress the failure.

This is repository-local validation, not production or physical-device install
verification. No production migration or deployment was performed.

## Files changed

- apps/core/content_validation.py
- apps/core/doctor_sections.py
- apps/core/migrations/0006_publicsitecontent_doctorpagesection.py
- apps/core/models.py
- apps/core/public_copy.py
- apps/core/templatetags/doctor_content.py
- apps/core/templatetags/public_content.py
- apps/core/test_doctor_content.py
- apps/core/tests.py
- apps/dashboard/js_tests/owner_ux_test.js
- apps/dashboard/owner_forms.py
- apps/dashboard/owner_views.py
- apps/dashboard/test_owner_ux.py
- apps/dashboard/test_owner_ux_layout.py
- apps/dashboard/urls.py
- docs/OWNER_UX_01.md
- static/css/dashboard.css
- static/css/install-app.css
- static/css/public-closeout.css
- static/js/install-app.js
- static/js/site.js
- templates/base.html
- templates/core/_doctor_mobile_booking.html
- templates/core/_doctor_section_body.html
- templates/core/_doctor_section_groups.html
- templates/core/contact.html
- templates/core/doctor.html
- templates/core/home.html
- templates/core/services.html
- templates/dashboard/base.html
- templates/dashboard/content_index.html
- templates/dashboard/owner_form.html
- templates/partials/footer.html
- templates/partials/install_app.html
- templates/partials/install_button.html
