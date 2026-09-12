# Current Execution Queue

هذه الوثيقة تعكس الحالة الحالية بعد إغلاق Commercial Delivery v1 وإقفال تصحيحات الـcloseout الأخيرة. لا تعتمد على Queue تاريخية أقدم عند التعارض مع GitHub Live أو قرار المالك.

## P0 — Commercial Delivery v1 — CLOSED

الحالة: **COMPLETE / MERGED / DEPLOYED**

- Commercial Delivery الأساسي أُغلق ودمج عبر PR #44.
- Final Figma-to-Django implementation مغلق ضمن النطاق المعتمد.
- Arabic RTL + English LTR verified.
- phone / tablet / laptop / desktop responsive QA complete ضمن Commercial Delivery scope.
- public booking / patient portal / staff dashboard / records / private media / public cases / reviews / consultation flows verified ضمن Commercial Delivery scope.
- بعد الإغلاق نُفذت تصحيحات Defect/Brand محدودة فقط، بدون إعادة فتح النطاق:
  - PR #50: منع إعادة إرسال Login POST الفاشل عند refresh مع الحفاظ على رسائل التحقق الآمنة.
  - PR #52: تثبيت ملفات الهوية البصرية النهائية المعتمدة byte-for-byte للـweb logo / favicon / Apple touch / PWA.
  - PR #51: منع إظهار OTP verification stage وهمي عندما يفشل مزود الإرسال، مع رسالة AR/EN محايدة وآمنة.
- Application delivery head بعد هذه التصحيحات: `81255edefca92adf83eb15d5d407aff07a9cc03c`.
- آخر GitHub validation على PR #51: Dependency audit PASS + Django checks PASS + `962` tests PASS، `5` skipped.
- آخر Production deploy لهذه application head: `dep-dai9eq0ae00c73domseg` — **LIVE**.
- لا يوجد Commercial Delivery code blocker مفتوح حاليًا.

## P1 — Doctor handoff package — COMPLETE / SYNCED

الحزمة الحالية:

`docs/project-handoff/DOCTOR_HANDOFF_PACKAGE_AR.md`

تتضمن:
- ما تم تسليمه.
- طريقة التشغيل اليومية.
- Reviews / Dynamic Average contract.
- privacy/security boundaries.
- final QA evidence.
- تصحيحات الـcloseout الأخيرة وحالة Production deploy.
- الفصل الواضح بين Commercial Delivery وProduction Readiness.

ملاحظة تسليم credentials: كلمة مرور حساب الطبيب يجب أن تُدار/تُدوّر بشكل خاص عند التسليم النهائي، ولا تُحفظ في Git أو docs أو screenshots.

## P2 — Production review data — COMPLETE

بيانات Google Reviews المعتمدة من المالك محمّلة في Production:

- `57` review.
- average المنشور: `4.93 / 5`.

لا تعِد تشغيل import لمجرد الإغلاق. أي إعادة تحميل مستقبلية يجب أن تكون Data operation مقصودة باستخدام Dataset المالك المعتمد، مع الحفاظ على idempotency وعدم إنشاء duplicates.

## P3 — Production readiness — SEPARATE TRACK

لا يعاد فتح Commercial Delivery بسبب هذه البنود إلا إذا ظهر blocker حقيقي يمنع التسليم المطلوب.

حسب الحاجة قبل Production Launch الكامل:

- legal/privacy approval
- persistent protected media/storage decision
- managed database backup/restore evidence
- monitoring provider
- alert routing
- privacy-safe error reporting
- final credential rotation/transfer
- load/concurrency validation
- WhatsApp live Meta activation and existing-number coexistence verification
- final production go/no-go

Production domain موجود ومربوط بالخدمة الحالية، لكن أي DNS/TLS operations إضافية تبقى Production Readiness وليست سببًا لإعادة فتح Commercial Delivery.

## Current implementation — Meta WhatsApp Cloud API

- Owner-approved production scope: [issue #45](https://github.com/sami77337/khaled-badran-clinic/issues/45).
- Provider adapter / signed webhook / AR-EN routing / OTP and neutral notification plumbing موجودة في الكود مع synthetic coverage.
- Live activation ما تزال عملية Production منفصلة وتتطلب إكمال Meta operator configuration، approved templates، webhook subscription، access credentials، وexisting-number coexistence verification.
- preserve the active clinic number, WhatsApp Business App access and chat history under the [onboarding requirement](../WHATSAPP_EXISTING_NUMBER_COEXISTENCE.md).
- Meta/WhatsApp live activation **ليست Commercial Delivery v1 blocker**؛ Scope Lock يضع WhatsApp Business API خارج v1 ما لم يُعتمد كمسار منفصل، وهو معتمد حاليًا فقط كـProduction issue #45.

## Remaining closeout actions

1. Final private credential rotation/transfer for the doctor account before handing credentials to the clinic.
2. Optional owner/device visual spot-check بعد تحديث cache للـfavicon / Apple Home Screen / Android-PWA icon؛ لا يغيّر Design أو Backend.
3. العودة إلى issue #45 لإكمال Meta live activation بعد إغلاق باقي التسليم، بدون خلطه مع Commercial Delivery.

## قاعدة المتابعة

أي عمل جديد بعد هذا الإغلاق يجب أن يكون واحدًا فقط من:

1. Deployment/data operation.
2. Production-readiness task.
3. Defect حقيقي على النسخة المسلّمة.
4. Owner-approved new scope.

لا Scope Creep، ولا إعادة بناء Backend مكتمل، ولا إعادة فتح التصميم بدون سبب معتمد.