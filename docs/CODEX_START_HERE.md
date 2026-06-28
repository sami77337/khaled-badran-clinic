# Codex Start Here

ابدأ دائمًا بفحص المستودع وقراءة الملفات التالية:

- README.md
- docs/DECISIONS.md
- docs/PROJECT_SPECIFICATION_AR.md
- docs/CODEX_BUILD_PLAN.md

## أول أمر مقترح لـ Codex CLI

انسخ هذا النص داخل Codex CLI من مجلد المشروع المحلي:

```text
Read README.md and all files under docs/.
Inspect the repository structure.
Do not modify files in this step.
Report the current repository state and recommend the safest first implementation batch.
```

## أول دفعة تنفيذ بعد الفحص

Batch 1: Django Foundation.

الهدف:

- إنشاء مشروع Django نظيف.
- تجهيز إعدادات PostgreSQL-ready.
- تجهيز templates/static.
- تجهيز apps empty structure.
- عدم تنفيذ الحجز أو السجلات أو واتساب في هذه الدفعة.

الفحوصات المطلوبة بعد التنفيذ:

```bash
python manage.py check
python manage.py test
```
