# Current Execution Queue

## P0 — Current Figma runtime blocker

Fix:
`ReferenceError: Cannot access 'user' before initialization`

File:
`src/app/portal/PortalMainLayout.tsx`

Acceptance:
- `/portal` renders normally
- current authenticated patient comes from one real session/auth source
- no hardcoded Ahmad/Sami/first demo patient
- refresh preserves current user
- logout clears session
- second account changes identity
- Arabic/English keeps same patient identity
- `/portal/appointments` works
- `/portal/medical-records` works
- no TDZ/hook/redirect-loop/runtime console errors

## P1 — Finish Figma QA

Audit all approved routes/screens in Arabic + English:
- Home
- Doctor
- Services
- Cases
- Reviews
- Booking
- Portal login/register
- Portal dashboard
- Appointments
- Medical records
- Contact & Location
- Staff dashboard
- Scheduling
- Content management
- Review management
- Case management

Test phone + tablet/iPad + laptop + desktop, plus loading/empty/error states.

## P2 — Confirm approved design requirements

- Jordan `+962` default country selector on all phone fields
- dynamic overall rating
- full reviewer names
- review hide/restore/archive controls
- doctor-editable normal public content
- achievement management
- configurable weekly schedule/exceptions
- interactive calendar
- `KB` dashboard badge in both languages
- real clickable clinic map
- mobile language switch outside drawer
- gold/wood active mobile menu route
- mobile Home hides rotating image, Services cards, FAQ
- desktop Authorized Cases above Services

## P3 — Figma freeze

After QA passes, stop adding unapproved visual changes. Only bugs or explicit owner requirements.

## P4 — GitHub live audit

Verify current main and open PRs. Keep major Dependabot upgrades separate from product work.

## P5 — Figma-to-Django implementation audit

Compare every final approved Figma route with current Django.
Do not rebuild already implemented backend.

Produce a gap matrix:
- implemented
- partial
- missing
- design-only
- backend-only
- blocker

## P6 — Implement missing product/visual gaps

Use focused Codex batches with real tests and privacy regression coverage.

## P7 — Commercial handoff QA

Verify:
- public website
- booking
- staff dashboard
- patient portal
- medical records/private media
- approved public cases
- Arabic/English
- responsive behavior
- accessibility basics
- security/privacy regression
- clean synthetic/demo state

## P8 — Doctor handoff package

Prepare commercial-ready evidence/documentation. Do not call it Production-ready.

## P9 — Separate production-readiness track

Still requires as applicable:
- legal/privacy approval
- persistent protected media storage
- monitoring provider
- alert routing
- privacy-safe error reporting
- managed PostgreSQL restore evidence
- RPO/RTO/retention approval
- load/concurrency testing
- intermittent staging health latency decision
- production domain/DNS/TLS
- final go/no-go
