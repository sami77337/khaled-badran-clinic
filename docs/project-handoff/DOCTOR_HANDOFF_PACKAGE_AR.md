# حزمة تسليم الطبيب — Commercial Delivery v1

هذه الحزمة مخصصة للتشغيل اليومي للعيادة بعد إغلاق **Commercial Delivery v1**.

> هذه الحزمة تعني أن المنتج التجاري المتفق عليه تم تسليمه وإغلاقه. لا تعني أن كل بند خارجي ضمن Production Readiness أو Operations أصبح منتهيًا.

## مرجع التسليم

- الموقع: `https://drkhaledbadran.com`
- Repository: `sami77337/khaled-badran-clinic`
- Final application commit: `f25fcac7d300c6aeb6b472bd4a009341e740f69a`
- Production deploy: `dep-daropq7avr4c73fimu6g` — LIVE
- اللغة الافتراضية: العربية / RTL
- English / LTR مدعوم.
- Final responsive QA: phone / tablet / laptop / desktop.

## 1. Dashboard — الاستخدام اليومي

من Dashboard يمكن للطبيب/الموظف المخوّل إدارة العمل التشغيلي اليومي، بما يشمل:

- المواعيد والجداول.
- الحالات التي تحتاج متابعة/تصنيف.
- Patient records.
- الملاحظات والزيارات.
- الصور والفيديوهات الطبية القصيرة ضمن الصلاحيات.
- Patient Reviews.
- Public Cases.
- Website Content.
- Appointment Messages.
- Reminder controls.

الصلاحيات الحالية هي المرجع؛ لا تستخدم حساب موظف لتنفيذ إجراء غير مخوّل له.

## 2. Scheduling والمواعيد

يمكن إدارة:

- الجدول الأسبوعي.
- أوقات الفتح والإغلاق.
- أكثر من فترة في اليوم حسب النظام الحالي.
- الاستثناءات والأيام الخاصة.
- المواعيد الحالية.

الحجز العام لا يحتاج Login.

تغيير الجدول لا يجب أن يُستخدم لحذف موعد موجود. المواعيد القائمة تبقى سجلات فعلية يجب التعامل معها من Workflow المواعيد.

## 3. Appointment Messages

صفحة **Appointment Messages / رسائل المواعيد** هي مكان إعداد رسائل Arrived / No-show والتحكم بالتذكير التلقائي.

رسائل Arrived / No-show:

- يوجد Default بالعربية والإنجليزية.
- عند فتح Compose يتم إدخال بيانات الموعد المسموحة تلقائيًا.
- الموظف يستطيع إرسال النص كما هو.
- أو تعديله/استبداله.
- أو اختيار No Message.
- التعديل لموعد واحد لا يغيّر الـDefault المحفوظ.
- فتح WhatsApp لا يعني أن النظام سجّل Sent/Delivered.

لا تضع معلومات طبية حساسة غير لازمة داخل رسالة WhatsApp.

## 4. Reminder controls

التذكير التلقائي يعمل عبر Meta-approved WhatsApp template.

من Dashboard يمكن:

- Enable / Disable للتذكير التلقائي.
- تعديل Default lead time بالدقائق.
- القيمة الافتراضية: 180 دقيقة = 3 ساعات.

مهم:

- تغيير الـDefault يطبّق على الحجوزات الجديدة.
- المواعيد الموجودة تحتفظ بالـreminder offset المخزن لديها.
- نص Meta template الأساسي ليس Free-text من Dashboard.
- الـscheduler يعمل تلقائيًا في Production؛ لا يحتاج الطبيب تشغيل command يدويًا.

إذا احتاجت Meta template نفسها إلى تغيير فعلي، فهذا Developer/Admin operation لأنه قد يتطلب موافقة Meta.

## 5. Arrived / No-show / Complete Visit

بعد وقت الموعد، يستخدم الموظف Workflow التصنيف الموجود بدل تعديل الحالات بشكل عشوائي.

- Arrived: يسجل وصول المريض وفق المسار الحالي.
- No-show: يستخدم فقط حسب القواعد الحالية وبعد وقت الموعد.
- No-show reason الداخلي لا يجب نسخه تلقائيًا إلى المريض.
- Complete Visit يستخدم بعد اكتمال الزيارة وفق Workflow الحالي.

لا يوجد automatic status transition يجعل موعدًا Arrived/No-show بدون قرار الموظف.

## 6. Patient records والوسائط

السجل الطبي v1 عملي ومحدود، وليس Hospital EMR.

الطبيب/الموظف المخوّل يمكنه:

- إنشاء/عرض Visit records.
- إضافة ملاحظات ضمن الصلاحيات.
- رفع الصور والفيديوهات القصيرة المدعومة.
- تحديد ما إذا كان المحتوى يبقى private أو يصبح visible to patient.
- إدارة public-case eligibility عبر المسار المخصص.

قواعد ثابتة:

- Private by default.
- visible_to_patient لا تعني Public.
- لا ترسل private media عبر direct storage URL.
- لا تغيّر visibility بدون سبب تشغيلي واضح.

## 7. Public Cases + Consent

لا يجوز نشر Patient Case للعامة إلا عندما تتحقق بوابات النشر الحالية، وأهمها:

- Consent confirmed.
- approved public-case state.
- Active/public eligibility.

الموقع العام لا يجب أن يكشف:

- اسم المريض.
- الهاتف.
- بيانات تعريفية خاصة.
- clinical notes الخاصة.
- private storage paths.

أي حالة لا يوجد لها consent واضح تبقى غير عامة.

## 8. Patient Portal

المريض يستخدم Patient Portal للوصول إلى المحتوى المسموح له فقط.

المبادئ:

- يرى حسابه هو فقط.
- يرى approved/visible content فقط.
- Medical content في v1 read-only للمريض.
- private staff-only content لا يظهر.
- Appointment list/detail/cancel/reschedule تعمل حسب القواعد الحالية.
- Close Account يستخدم safeguards الحالية ولا يعني محو السجلات التي يجب الاحتفاظ بها.

إذا أبلغ مريض عن ظهور بيانات مريض آخر، اعتبر ذلك Security incident ولا تحاول معالجة الموضوع يدويًا من Dashboard.

## 9. Patient Reviews

الموظف المخوّل يستطيع مراجعة وإدارة Visibility/Approval وفق النظام الحالي.

لا تعدّل معنى مراجعة المريض أو تنسب إليه نصًا لم يكتبه.

Public site يعرض فقط المراجعات المؤهلة للنشر حسب الحالة الحالية.

## 10. Website Content

يمكن استخدام Website Content Manager لتعديل المحتوى العام المعتمد ضمن الحقول الموجودة.

لا تستخدمه لاختراع Medical claims جديدة أو وعود علاجية غير معتمدة.

أي تغيير Design System حقيقي — لون جديد، typography جديدة، component style جديد، redesign — يحتاج قرار مالك قبل التنفيذ.

## 11. ما هو تشغيل يومي وما يحتاج Developer/Admin؟

### تشغيل يومي للطبيب/العيادة

- إدارة schedule.
- إدارة appointments.
- تصنيف Arrived / No-show.
- Appointment Messages.
- Reminder enable/disable وlead time.
- Patient records.
- media visibility.
- Reviews moderation.
- Public Cases بعد consent.
- Website Content ضمن الحقول المتاحة.

### Developer/Admin

- تغيير Meta templates أو credentials.
- Render/service/cron settings.
- environment variables/secrets.
- database/storage/backup operations.
- dependency upgrades.
- code/schema changes.
- DNS/TLS/infrastructure.
- security incident remediation.
- إضافة Feature جديدة.

## 12. Security / Privacy rules

يجب الحفاظ دائمًا على:

- لا Public patient PII.
- لا direct private medical media URLs.
- patient ownership isolation.
- private media access control.
- consent-gated public cases.
- CSRF/auth boundaries.
- لا Secrets داخل screenshots/docs/chat.
- لا real patient data في test/demo material.
- لا Medical AI diagnosis/treatment automation.

## 13. Troubleshooting التشغيلي

إذا ظهرت مشكلة:

1. حدّد الشاشة والخطوة التي سبقتها.
2. لا تنسخ Patient data إلى GitHub issue أو screenshot عام.
3. استخدم بيانات Synthetic عند إعادة المشكلة.
4. لا تغيّر DB أو permissions يدويًا كحل سريع.
5. صعّد المشكلة كـDefect للـDeveloper إذا كانت Functional/Security.
6. إذا كانت مرتبطة بـMeta/Render/credentials، تعامل معها كـAdmin/Operations task.

## 14. QA المرجعي

آخر application closeout gate:

- Dependency audit: PASS.
- Django checks: PASS.
- migration check: PASS.
- deployment smoke: PASS.
- Full Django suite: **1249 PASS**.
- responsive AR/EN browser gates: PASS.
- Patient Portal + Privacy/Security: PASS.
- Public Cases / Consent: PASS.
- Public Booking E2E: PASS.
- Messaging + Reminder scheduler: PASS.
- Production deploy: LIVE.

## 15. Credential handoff

كلمات المرور، tokens، OTPs، Meta credentials، Render secrets وأي مفاتيح خاصة:

- لا تحفظ في Git.
- لا توضع في هذه الوثيقة.
- تسلّم عبر قناة خاصة مناسبة.
- تدوير credentials عند الحاجة هو Operations/credential hygiene وليس Feature.

## حالة الإغلاق

**Commercial Delivery v1 = CLOSED / HANDED OFF**

أي عمل لاحق يصنّف بوضوح كواحد من:

- Defect correction.
- Production Readiness / Operations.
- Deployment/data operation.
- Owner-approved new scope.
