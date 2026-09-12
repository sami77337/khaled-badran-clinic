# حزمة تسليم الطبيب — Commercial Delivery v1

هذه الوثيقة هي حزمة التسليم التجارية للطبيب/العيادة بعد إغلاق Commercial Delivery v1 وإقفال تصحيحات الـcloseout المعتمدة.

> هذه الحزمة **Commercial-ready** وليست تصريحًا بأن جميع بنود Production Readiness الخارجية مكتملة. مسار Production Readiness منفصل.

## حالة التسليم

- Repository: `sami77337/khaled-badran-clinic`
- Commercial Delivery الأساسي: PR #44 — merged.
- Post-closeout defect/brand corrections: PR #50 + PR #52 + PR #51 — merged.
- Application delivery head بعد آخر تصحيح: `81255edefca92adf83eb15d5d407aff07a9cc03c`.
- Production deploy: `dep-dai9eq0ae00c73domseg` — LIVE.
- العربية هي اللغة الافتراضية، مع دعم English / LTR.
- Final Figma-to-Django visual implementation وResponsive QA مغلقان ضمن النطاق المعتمد.

## ما تم تسليمه

### الموقع العام والهوية

- Home / Doctor / Services / Reviews / Cases / Contact & Location.
- Responsive على phone / tablet / laptop / desktop.
- Arabic RTL + English LTR.
- خريطة العيادة المصورة المعتمدة مع بقاء رابط الاتجاهات الحقيقي عبر `clinic.map_url`.
- لا توجد صور Google reviewer/profile داخل التعليقات.
- تم تثبيت ملفات الهوية النهائية المعتمدة byte-for-byte عبر PR #52:
  - web/in-page logo.
  - favicon.
  - Apple touch icon.
  - PWA 192×192 و512×512.
- asset-integrity SHA256 contract مغطى بالاختبارات ولا يتم توليد/قص/تلوين الملفات داخل المشروع.

### الحجز

- الحجز العام لا يتطلب تسجيل دخول.
- حالات success/error آمنة وواضحة للمريض.
- إدارة الجداول والمواعيد تبقى من لوحة الطبيب/الموظفين وفق الصلاحيات الحالية.

### التقييمات

- المريض المسجل يستطيع إنشاء/تعديل/حذف تقييمه فقط.
- تقييم المريض يبدأ Pending ولا يصبح عامًا إلا بعد موافقة الطبيب/الموظف المخوّل.
- تعديل تقييم مريض منشور يعيده إلى Pending ويزيل Featured تلقائيًا.
- الطبيب/الموظف يستطيع approve/unapprove وactivate/deactivate وfeature/order/delete، بدون تعديل نص المريض نفسه.
- الجمهور يرى فقط `approved + active`.
- Google/external rating-only reviews مدعومة حتى لو لم يوجد نص.
- Average Rating ديناميكي ويُحسب من جميع `PublicReview` المنشورة والفعالة، بغض النظر عن المصدر، بما فيها rating-only reviews.
- العرض يستخدم منزلتين عشريتين.

### بيانات Google Reviews المعتمدة

بيانات المالك المعتمدة محمّلة حاليًا في Production:

- 57 تقييمًا.
- المتوسط المنشور: `4.93 / 5`.

Dataset المصدرية تبقى خارج Git عمدًا. لا حاجة لإعادة تشغيل import كجزء من closeout. إذا احتاجت بيئة أخرى إلى التحميل مستقبلًا، يستخدم الأمر المعتمد مع ملف المالك فقط:

```bash
python manage.py import_public_reviews <owner-approved-json> --approve
```

الاستيراد Idempotent؛ تكرار تشغيله على نفس البيانات لا يفترض أن ينشئ duplicates.

### Patient Portal والسجل الطبي

- المريض يرى بياناته المصرّح بها فقط.
- Medical record content يبقى read-only للمريض في v1.
- الطبيب/الموظف يحدد ما يصبح مرئيًا للمريض.
- private media لا تُكشف عبر direct public URLs.

### Public Cases

- النشر العام يتطلب `approved_public_case + consent_confirmed + active`.
- patient identity والبيانات السريرية الخاصة لا تُعرض في الصفحة العامة.
- الوصول للوسائط العامة يتم عبر controlled media routes، وليس روابط private storage مباشرة.

### Consultations وOTP behavior

- Registered consultation flow يبقى خاصًا ومملوكًا للمريض.
- Guest/transient consultation flow موجود داخل الموقع مع authorization مبني على OTP/session وليس UUID وحده.
- رد الطبيب يمكن أن يكون Text أو Voice داخل المسار الآمن للموقع.
- PR #51 أصلح حالة فشل مزود OTP: لا ينتقل المستخدم إلى verification stage وهمي إذا لم يتم إرسال الرمز، وتظهر رسالة AR/EN محايدة بدون كشف provider details أو PII.
- Meta WhatsApp Cloud API plumbing موجود كمسار Production منفصل، لكن live Meta onboarding/configuration لم يُغلق بعد وهو متابع في issue #45.
- Live Meta activation ليست blocker لـCommercial Delivery v1 حسب Scope Lock؛ WhatsApp v1 التجاري يبقى quick-link boundary ما لم يُعامل العمل كProduction scope منفصل.

### Login behavior

- PR #50 أغلق إعادة إرسال Failed Login POST عند refresh باستخدام Post/Redirect/Get مع الحفاظ على الرسائل الآمنة، اللغة، `next` الآمن، rate limits وCSRF/auth boundaries.

## قواعد التشغيل اليومية للطبيب/العيادة

1. استخدم Dashboard لإدارة المواعيد، السجلات، حالات النشر، التقييمات، والحالات العامة ضمن الصلاحيات الموجودة.
2. لا تنشر أي Patient Case قبل التأكد من consent وحالة `approved_public_case`.
3. لا ترسل private medical media كرابط عام مباشر.
4. راجع Patient Reviews قبل الموافقة على نشرها.
5. أي تعديل من المريض على Review منشور يعيده تلقائيًا إلى Pending ويحتاج مراجعة جديدة.
6. أبقِ WhatsApp ضمن الحدود التشغيلية المعتمدة إلى أن يكتمل Production Meta activation بشكل منفصل.
7. لا تحفظ كلمات المرور أو tokens أو patient data في docs/screenshots/chat handoff artifacts.

## Security / Privacy boundaries المحفوظة

- لا يوجد real patient data في tests/docs/screenshots داخل Git.
- Patient ownership isolation محفوظة.
- private media access control محفوظ.
- public cases consent-gated.
- CSRF/auth boundaries محفوظة.
- لا يوجد public patient PII.
- لا توجد direct private medical media URLs.
- لا يوجد Medical AI / diagnosis / treatment automation.
- OTP/provider failure messaging لا يكشف account existence أو provider exception details.

## Evidence النهائي

أحدث evidence بعد تصحيحات الـcloseout:

- GitHub Dependency audit — PASS.
- GitHub Django checks — PASS.
- `python manage.py makemigrations --check --dry-run` — PASS.
- `python manage.py check` — PASS.
- `python manage.py deployment_smoke` — `13 pass / 7 local-development warnings / 0 failure / 0 strict blocker` في CI.
- Full Django suite على merge candidate: `962 PASS`, `5 skipped`.
- responsive/layout regression suites ضمن full CI — PASS.
- approved brand asset hash verification — PASS للملفات الخمسة المعتمدة.
- Production deploy `dep-dai9eq0ae00c73domseg` — LIVE على application head `81255edefca92adf83eb15d5d407aff07a9cc03c`.
- فحص Render بعد deploy لم يُظهر production HTTP 5xx في العينة اللاحقة للنشر.

تحذيرات `check --deploy` وdeployment smoke التي تظهر تحت `config.settings.dev` تخص بيئة CI/local development ولا تُستخدم وحدها كحكم على إعداد Production.

## Credential handoff

قبل تسليم بيانات الدخول النهائية للطبيب:

- دوّر كلمة مرور حساب الطبيب بشكل خاص.
- سلّمها بقناة خاصة خارج Git/docs/screenshots.
- لا تُدرج password أو token أو OTP أو secret في هذه الحزمة.

هذه خطوة credential hygiene نهائية، وليست Feature جديدة ولا إعادة فتح لـCommercial Delivery.

## ما لا يزال خارج Commercial Delivery v1

هذه البنود لا تمنع التسليم التجاري الحالي، لكنها تبقى ضمن Production Readiness أو Operations حسب الحاجة:

- إكمال Meta WhatsApp Cloud API live onboarding/configuration والقوالب والاشتراك بالـwebhook وexisting-number coexistence verification — issue #45.
- legal/privacy production approval.
- managed database backup/restore evidence.
- monitoring provider + alert routing.
- privacy-safe error reporting.
- load/concurrency validation.
- final production go/no-go.

## تعريف الإغلاق

Commercial Delivery v1 يعتبر مكتملًا من جهة الكود والواجهات والـQA، مع دمج ونشر تصحيحات الـcloseout الأخيرة. أي عمل لاحق يجب أن يُصنّف بوضوح كأحد الآتي:

- Production readiness.
- Deployment/data operation.
- Defect correction.
- Owner-approved new scope.

ولا يجوز إعادة فتح Features مكتملة أو توسيع النطاق بدون قرار واضح من المالك.