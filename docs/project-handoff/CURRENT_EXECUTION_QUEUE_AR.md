# Current Execution Queue

هذه الوثيقة تعكس الحالة الحالية بعد إغلاق Commercial Delivery v1. لا تعتمد على Queue تاريخية أقدم عند التعارض مع GitHub Live أو قرار المالك.

## P0 — Commercial Delivery v1 — CLOSED

الحالة: **COMPLETE / MERGED**

- PR #44 merged إلى `main`.
- Merge commit: `8d34c198c15442e4092c02513cb3f42596b4db92`.
- Final Figma-to-Django implementation مغلق ضمن النطاق المعتمد.
- Arabic RTL + English LTR verified.
- phone / tablet / laptop / desktop responsive QA complete.
- public booking / patient portal / staff dashboard / records / private media / public cases / reviews / consultation flows verified ضمن Commercial Delivery scope.
- Dependency audit PASS.
- Django checks PASS.
- Full app suite على آخر Commercial head: 852 PASS.

## P1 — Doctor handoff package — COMPLETE

الحزمة الحالية:

`docs/project-handoff/DOCTOR_HANDOFF_PACKAGE_AR.md`

تتضمن:
- ما تم تسليمه.
- طريقة التشغيل اليومية.
- Reviews / Dynamic Average contract.
- privacy/security boundaries.
- final QA evidence.
- الفصل الواضح بين Commercial Delivery وProduction Readiness.

## P2 — Target-environment review data load — PENDING ENVIRONMENT

الـ57 Google reviews المعتمدة من المالك موجودة في Dataset خارجي خارج Git.

تم التحقق من تحميلها محليًا، لكن عند تحديد قاعدة بيانات بيئة التسليم/Production يجب تشغيل:

```bash
python manage.py import_public_reviews <owner-approved-json> --approve
```

هذه Data Load operation وليست Feature أو Code blocker.

## P3 — Production readiness — SEPARATE TRACK

لا يعاد فتح Commercial Delivery بسبب هذه البنود إلا إذا ظهر blocker حقيقي يمنع التسليم المطلوب.

حسب الحاجة قبل Production Launch الكامل:

- legal/privacy approval
- persistent protected media/storage decision
- managed database backup/restore evidence
- monitoring provider
- alert routing
- privacy-safe error reporting
- production domain/DNS/TLS
- load/concurrency validation
- WhatsApp live Meta activation and existing-number coexistence verification
- final production go/no-go

## Current implementation — Meta WhatsApp Cloud API

- Owner-approved scope: [issue #45](https://github.com/sami77337/khaled-badran-clinic/issues/45).
- Implementation review: [PR #46](https://github.com/sami77337/khaled-badran-clinic/pull/46)
  on `feat/production-whatsapp-cloud-api`.
- The adapter, signed webhook, AR/EN routing, guest OTP, neutral reply/booking
  notifications and scheduled reminders are implemented with synthetic tests.
- [Validation evidence](../WHATSAPP_META_VALIDATION.md) records the database/cache
  checks; [operator setup](../WHATSAPP_META_SETUP.md) is the current configuration
  and template reference.
- Live activation still requires operator configuration, approved Meta templates,
  existing-number coexistence verification, webhook subscription, scheduler setup
  and a controlled acceptance check. Issue #45 remains open for that work.
- Preserve the active clinic number, WhatsApp Business app access and chat history
  under the [onboarding requirement](../WHATSAPP_EXISTING_NUMBER_COEXISTENCE.md).

## قاعدة المتابعة

أي عمل جديد بعد هذا الإغلاق يجب أن يكون واحدًا فقط من:

1. Deployment/data-load operation.
2. Production-readiness task.
3. Defect حقيقي على النسخة المسلّمة.
4. Owner-approved new scope.

لا Scope Creep، ولا إعادة بناء Backend مكتمل، ولا إعادة فتح التصميم بدون سبب معتمد.
