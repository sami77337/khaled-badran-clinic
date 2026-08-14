# KBC MASTER HANDOFF — عيادة الدكتور خالد بدران

هذا الملف هو المرجع التنفيذي الرئيسي لاستكمال المشروع في أي محادثة ChatGPT/Codex جديدة.

## قاعدة المصدر

- GitHub هو مصدر الحقيقة للحالة البرمجية.
- Figma Make هو مصدر الحقيقة للتصميم الجاري.
- هذا الملف يلخص القرارات والنطاق والحالة المعروفة، لكنه لا يثبت أن تغييرًا ما نُفذ ما لم يتم التحقق من المصدر الفعلي.
- Production-ready = NO حاليًا.

## المشروع

- الاسم العربي: عيادة الدكتور خالد بدران
- English: Dr. Khaled Badran Clinic
- الطبيب: د. خالد حسان بدران / Dr. Khaled Hassan Badran
- Repository: `sami77337/khaled-badran-clinic`
- المسار المحلي المعروف: `C:\Users\Abu AL-yazeed\Desktop\khaled-badran-clinic`
- Figma Make: `https://www.figma.com/make/96aFwIc36sBvgpDLoJfAaG/Interactive-Clinic-Website-Prototype`
- Staging: `https://khaled-badran-clinic-staging.onrender.com`

## الحالة البرمجية وقت إنشاء Handoff

- main: `7eb782003eccd686a6cff0a14011dbf09cd1de42`
- آخر Commercial PR مدموج: #41
- آخر Full Test count موثق: 321 tests passed
- تحقق من GitHub Live قبل كل مهمة لأن هذه القيم قد تتغير.

Commercial Delivery PRs المدموجة:
- #36 Scope Lock
- #37 Patient Record Foundation
- #38 Private Media Storage
- #39 Patient Portal Approved Visibility
- #40 Approved Public Cases
- #41 Doctor/Staff Dashboard Record Workflow

## فرع محفوظ

لا تلمس `feat/security-operations-release-evidence` دون أمر صريح من المالك.
Known commit: `f8160bb`.

## Commercial Delivery v1

يشمل:
- Public clinic website
- Final Figma implementation
- Responsive mobile/tablet/laptop/desktop
- Arabic + English، العربية Default
- Home / doctor / services
- Login-free booking
- Automatic booking confirmation if slot available
- Booking success/error states
- Default reminder: 3 hours قبل الموعد، قابل للتعديل
- WhatsApp Quick Link فقط
- Doctor/Staff dashboard
- Simple patient medical record
- Private images and short private videos
- Patient portal
- Doctor-controlled approved visibility
- Patient read-only medical content
- Approved public cases with consent
- Dashboard-managed normal public content قدر الإمكان

خارج v1 ما لم يعتمد لاحقًا:
- WhatsApp Business API/webhooks
- Payments
- AI diagnosis/treatment/triage/recommendations
- Prescription automation
- Full hospital EMR
- PACS/DICOM
- Public private-medical-file sharing

## بيانات الطبيب

الاسم: د. خالد حسان بدران / Dr. Khaled Hassan Badran

اللقب العربي: استشاري الأنف والأذن والحنجرة
English: Consultant Ear, Nose and Throat Surgeon

الوصف العربي المختصر المعتمد:

> استشاري في أمراض وجراحة الأنف والأذن والحنجرة للكبار والأطفال، حاصل على البورد الأوروبي والبورد الأردني، مع خبرة مهنية في مستشفيات المملكة المتحدة واهتمام خاص بجراحة الأنف الوظيفية والتجميلية.

English approved summary:

> Consultant in adult and pediatric ear, nose and throat medicine and surgery, certified by the European and Jordanian Boards, with professional experience in UK hospitals and a special focus on functional and cosmetic rhinoplasty.

يجب أن يأتي هذا الوصف من Central source واحد.

المعلومات المهنية المقدمة من المالك تشمل: European Board، Jordanian Board، FRCSI، MRCSI، GMC، MDU، بكالوريوس الطب والجراحة من الجامعة الأردنية، ماجستير من University of Central Lancashire، خبرة ENT في UK، والعمل في العيادة الخاصة في عمان. تحقق من أسماء واختصارات المؤسسات والجوائز الإنجليزية الدقيقة قبل النشر النهائي.

Languages: العربية، الإنجليزية.

Areas: ENT، Adult ENT، Pediatric ENT، ENT surgery، Rhinoplasty.

لا تضف Claims مثل best/world-class/guaranteed/عدد سنوات غير موثق.

## الموقع

العربية:
عمّان – الشميساني
شارع رفيق العظم 13
مجمع الفيحاء الطبي – الطابق الأول
مقابل مستشفى الشميساني وحديقة الطيور

English:
Al Shmeisani, Amman
Rafiq Al Athem St. 13
Al Fayhaa Medical Complex – First Floor
Opposite Shmeisani Hospital and Bird Garden

Coordinates: `31.970276, 35.8934391`

Map rules:
- real clinic location
- paper/cream appearance preferred
- burgundy pin
- clickable to Google Maps
- no generic Unsplash map substitute
- no invented phone/hours

## Phone inputs

كل Phone field:
- Country selector
- Jordan default
- `+962` default
- digits LTR
- normalized international/E.164 in real implementation
- no duplicate code

ينطبق على booking، portal login/register، patient forms، contact/WhatsApp settings.

## Booking

- No login required
- Automatic confirmation if available
- No payment in v1
- Reminder default = 3 hours
- Services/prices/hours dynamic
- Doctor manages weekly schedule
- Open/Closed
- One or multiple periods
- Holidays / surgery day / exceptions / special hours
- Existing appointment must not disappear because schedule changed
- Calendar should be interactive

## Patient medical record v1

Simple practical clinic record, not hospital EMR.

Includes patient details، phone، age/DOB، gender، appointments، visits، visit reason، doctor notes، manually written diagnosis/plan and follow-up، images، short videos.

Media states:
- `private_only`
- `visible_to_patient`
- `approved_public_case`

Rules:
- private by default
- patient-visible != public
- approved-public-case != patient-visible automatically
- public case requires consent + active
- no direct public private-media URL
- no AI medical generation/analysis

## Backend المنجز حتى PR #41

Records:
- VisitRecord
- ClinicalNote
- RecordMedia

Private media:
- PrivateMediaStorage
- UUID paths
- no public `.url`
- image/short MP4 validation
- staff-only private media route

Patient portal:
- read-only approved medical records
- own patient only
- approved visits/notes/media only
- controlled patient media route

Public cases:
- Arabic/English routes
- controlled public media route by public_id
- approved_public_case + consent_confirmed + active
- sanitized metadata, no patient identity/clinical data

Staff dashboard:
- patient list
- patient record overview
- create visit/note
- upload image/short MP4
- manage visibility/consent/active/public case state

## Dashboard content-management target

Doctor/authorized staff should be able to manage without programmer:
- doctor summary/full bio
- qualifications/memberships/achievements/awards
- add/edit/reorder/hide/archive/publish achievements
- services
- FAQs
- clinic info/location/hours
- schedule exceptions
- cases/featured items
- review visibility
- public section titles/descriptions
- Arabic + English fields
- Draft / Preview / Publish

System-controlled, not free-editable: permissions، security warnings، validation، internal statuses، consent rules، technical routes/keys.

## Reviews

Use only real reviews provided by owner screenshots. Never invent, rewrite, correct, or auto-translate original review text. Visible reviewer name stays complete when known. No reviewer photos. Current design decision: no Google logo/source label.

Arabic default shows Arabic reviews; English default shows English reviews; Home shows 3; All Reviews supports Arabic/English/All while preserving each review's native RTL/LTR.

Known 5-star Arabic reviewers/text:
- Alaa Adham89 — النص الأصلي المقدم من المالك محفوظ في المحادثة السابقة ويجب عدم تغييره.
- Malak Alhinde
- Randa Abdo
- ام ريان ابو علي ابو علي
- FAROUK AIFAROUK

Known English:
- Tareq Krayim
- Zeid Haddadin
- Samia Mushawhar
- Fatma Marii
- WALID AO
- Jjohaina Sameer
- H. Badran (لا توسع الاسم)

## Dynamic rating

Do not hardcode 4.8.
Use visible + active + valid reviews only.
Exclude hidden/archived/deleted/invalid.
Average = sum(ratings) / count(included), rounded to one decimal.
If none, do not show 0.0 as a real rating.
Use one centralized selector/helper across pages.
Doctor can Hide / Restore / Archive reviews. Permanent delete only with deliberate confirmation if implemented. Original review text/rating is immutable.

`4.8` و`174` are legacy external snapshot values, not permanent dynamic source.

## Figma identity

- Burgundy/deep maroon
- Cream
- Warm brown
- Subtle gold/wood
- Calm premium medical look
- Arabic default RTL and naturally written, not literal translation
- English LTR

Doctor CTA:
- `التعرّف على الدكتور`
- `Meet the Doctor`

## Mobile Home below 768px

Order:
1. Header
2. Text-only Hero
3. Doctor Information
4. Cases
5. Reviews
6. Contact & Location
7. Compact Footer

Hide on mobile Home only:
- rotating Hero image
- Services cards section
- FAQ section

Keep Services route/nav/explore button.

Mobile language switch:
- visible outside drawer
- owner requested right side
- no duplicate inside drawer
- active route in drawer uses gold/wood + aria-current

Cases/reviews mobile carousel:
- one full card
- autoplay
- manual swipe
- pagination dots
- pause on interaction
- respect reduced motion
- no duplicated filler items
- natural height/no clipping

Responsive must be fluid; no `transform: scale()` workaround or fixed card sizes causing clipping.

## Desktop Home order

Hero → Doctor → Authorized Cases → Services → remaining sections.
Authorized Cases must remain above Services on desktop.

## Contact & Location

Route: `/contact-location`
Must be reachable from desktop/mobile/footer.
Real clinic map, clickable directions, optional contact rows hidden when unconfigured, no invented hours.

## Dashboard badge

Always visible as `KB`, even in Arabic. Never `خ ب`.

## Current immediate Figma blocker

Latest actual runtime error from owner:

`ReferenceError: Cannot access 'user' before initialization`

File:
`src/app/portal/PortalMainLayout.tsx`

The Error Boundary catches it, but patient portal itself fails.

First Figma task:
- fix declaration order
- initialize auth/user before derived values/effects/context
- no `var` workaround
- no fake user
- no first demoPatient pretending to be authenticated user
- PortalMainLayout and PortalDashboard use one auth/session source
- greeting uses actual signed-in patient
- logout clears session
- refresh preserves correct account
- second account changes identity
- Arabic/English changes display name, not identity

Acceptance verification:
- `/portal`
- refresh
- logout
- second account
- Arabic/English
- `/portal/appointments`
- `/portal/medical-records`
- console has no TDZ/hook/redirect-loop/runtime errors

Never hardcode Ahmad/Sami/Synthetic Patient 001 as greeting fallback.

## Interactivity

Final product is not static screenshots. Required interactions include routing، forms، validation، tabs، filters، drawers، accordions، calendar، carousels، map actions، dashboard management، loading/empty/error states.

No hardcoded patient/rating/schedule/contact data.

## Operations/Staging

Known public staging routes have been reachable, but intermittent severe `/health/` latency was documented: some windows >30s, others fast. Root cause is not proven. Do not claim solved without new evidence.

Partially completed/evidenced:
- local Docker PostgreSQL/Redis validation
- pip-audit workflow
- public uptime observations
- synthetic local PostgreSQL restore drill
- operations decision packs

Still incomplete:
- monitoring provider
- alert routing
- privacy-safe error reporting
- real managed PostgreSQL restore drill
- RPO/RTO/retention approval
- legal/privacy approval
- load/concurrency
- persistent production media storage decision
- DNS/domain/TLS
- final production go/no-go

## Production media warning

Current private-media foundation uses protected local filesystem behavior. Before real production patient uploads, choose persistent protected storage; never rely on ephemeral disk; preserve private-by-default access, backups, retention/deletion policy, privacy/legal approval, and access controls.

## Security/privacy invariants

Never break:
- records private by default
- patient sees own approved content only
- portal medical record read-only in v1
- staff-only notes remain private
- visible_to_patient != public
- public case requires consent
- no direct private file URL
- no public patient PII
- no real patient data in tests/docs/prompts
- no secrets/tokens/connection strings
- no AI medical automation

## Git/Codex procedure

Before code batch:
- inspect status
- switch/pull main
- verify live main SHA and open PRs
- create dedicated branch
- preserve unrelated work

Validation as applicable:
- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- targeted tests
- `python manage.py test`
- `python -m pip check`
- `git diff --check`
- `git diff --cached --check`
- secret/PII scan

Migrations only when intentional.

## Dependabot rule

Known open upgrade PRs include major Actions/dependency changes. Do not merge them casually inside product/UI work. Major upgrades require dedicated compatibility batch.

## Completion path

A. Finish Figma runtime + full responsive/route QA.
B. Freeze final approved Figma.
C. Run Figma-to-Django implementation audit route-by-route.
D. Implement only missing visual/product gaps; do not rebuild backend already completed.
E. Commercial handoff QA across public/booking/dashboard/portal/records/media/cases/Arabic/English/responsive/security.
F. Prepare doctor handoff package.
G. Production-readiness track stays separate.

## Immediate continuation point

START HERE:
Fix `Cannot access 'user' before initialization` in `PortalMainLayout.tsx`, verify the patient session flow end-to-end, then finish Figma QA. After Figma is closed, proceed to Commercial Handoff QA + Figma-to-Django implementation audit.

## Definition of doctor-handoff ready

Commercial handoff ready means final Figma, Django matches approved design, booking works, portal works, records/private media work, dashboard works, consented public cases work, Arabic/English and responsive behavior work, no dangerous demo hardcodes, no known runtime errors, and QA evidence exists.

This does NOT automatically mean Production-ready.
