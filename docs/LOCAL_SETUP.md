# Local Setup Notes

هذه ملاحظات أولية لتجهيز العمل المحلي قبل تشغيل Codex CLI.

## Clone

```bash
git clone https://github.com/sami77337/khaled-badran-clinic.git
cd khaled-badran-clinic
```

## Suggested Branch

```bash
git checkout -b feat/django-foundation
```

## Python Environment

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
```

## Codex CLI First Step

ابدأ بفحص المستودع قبل تنفيذ أي كود:

```text
Read README.md and all docs. Inspect the repository. Do not modify files yet. Report the safest first implementation batch.
```

## Important

- Do not commit `.env`.
- Use `.env.example` as a template only.
- Do not add real WhatsApp credentials.
- Do not add real patient data.
