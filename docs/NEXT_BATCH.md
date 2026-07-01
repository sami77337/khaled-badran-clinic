# Next Batch: Final Product Completion Track

This document replaces the stale foundation-stage next-batch note. The project
is past the initial foundation stage. After Batch 13, the current track is
final product completion and professional delivery readiness.

## Current Direction

- Final Product Completion Track is now the active planning track.
- DEMO_TRACK is no longer the project priority.
- The project must continue toward a highly professional, smooth, comfortable,
  secure, production-ready clinic system.
- Synthetic demo data and seed commands may remain only for local
  validation/testing. They are not the delivery goal.
- Batch 11 completed repository-local restricted staging validation operations.
- Batch 11 reported 246 tests passing.
- The project is not production launched.
- Real staging infrastructure is not yet validated.
- Legal/privacy approval remains blocked.
- WhatsApp, uploads, medical records, and payments remain outside the current
  implemented scope.
- Batch 12 recorded the final product completion track, dashboard-managed
  configuration principle, and authorized showcase requirements.
- Batch 13 produced final UX/product-flow specifications and design handoff
  requirements. Batch 13 did not create Figma work, visual design, application
  code, templates, CSS, JavaScript, models, migrations, settings, deployment,
  or external infrastructure.

## Batch 14 Recommendation

Recommended next batch:

```text
Batch 14: restricted staging validation with PostgreSQL/Redis/HTTPS/proxy
```

Goal:

- validate the current bounded public site, booking, staff operations, patient
  portal, rate limits, and operational commands against restricted
  production-like staging infrastructure;
- use PostgreSQL, Redis/shared cache, HTTPS, exact host/CSRF settings, and
  reviewed proxy behavior;
- preserve the no-real-patient-data rule and use synthetic data only;
- avoid feature expansion while staging and production-like behavior remain
  unproven.

Why this is safer than starting dashboard implementation planning/authorization
immediately:

- the current booking and portal flows already create and protect operational
  patient/appointment data, so PostgreSQL/Redis/HTTPS/proxy validation is the
  most urgent launch-safety evidence gap;
- dashboard implementation would expand the staff/admin surface before the
  current bounded system has been proven under production-like infrastructure;
- Batch 13 already provides dashboard and flow specifications that can feed a
  later dashboard planning/authorization batch after staging evidence is
  gathered.

Batch 14A remains a valid later planning-only option:

```text
Batch 14A: dashboard implementation planning/authorization
```

Use Batch 14A only if the owner explicitly pauses staging validation to plan
dashboard implementation scope. Do not start dashboard code in Batch 14A unless
a separate implementation batch authorizes it.

Must read before Batch 14:

- `README.md`
- `docs/UX_PRODUCT_FLOW_AUDIT.md`
- `docs/FINAL_UX_PRODUCT_FLOW_SPEC.md`
- `docs/PUBLIC_SITE_UX_SPEC.md`
- `docs/BOOKING_FLOW_UX_SPEC.md`
- `docs/DOCTOR_DASHBOARD_UX_SPEC.md`
- `docs/PATIENT_PORTAL_UX_SPEC.md`
- `docs/BILINGUAL_CONTENT_UX_STANDARD.md`
- `docs/MOBILE_ACCESSIBILITY_UX_CHECKLIST.md`
- `docs/BATCH_13_STATUS.md`
- `docs/FINAL_PRODUCT_COMPLETION_PLAN.md`
- `docs/FINAL_PRODUCT_QUALITY_STANDARD.md`
- `docs/DOCTOR_MANAGED_CONFIGURATION_STANDARD.md`
- `docs/AUTHORIZED_SHOWCASE_REQUIREMENTS.md`
- `docs/FIGMA_DESIGN_HANDOFF.md`
- `docs/PROJECT_RELEASE_SCORECARD.md`
- `docs/ROUTE_ACCESS_MATRIX.md`
- `docs/DATA_EXPOSURE_MATRIX.md`
- `docs/LEGAL_PRIVACY_OPERATIONS.md`
- `docs/STAGING_VALIDATION_PLAN.md`
- `docs/STAGING_GAP_ANALYSIS.md`
- `docs/STAGING_ENVIRONMENT_CONTRACT.md`
- `docs/POSTGRESQL_READINESS.md`
- `docs/REDIS_RATE_LIMIT_READINESS.md`
- `docs/SECURITY_REGRESSION_CHECKLIST.md`

## Ordered Recommended Batches

1. Batch 14: restricted staging validation with PostgreSQL/Redis/HTTPS/proxy.
2. Batch 14A: dashboard implementation planning/authorization, only if the
   owner explicitly chooses planning before dashboard code.
3. Batch 15: backup/restore synthetic drill evidence and
   monitoring/alerting setup plan.
4. Batch 16: legal/privacy/account recovery and patient identity verification
   policy.
5. Batch 17: doctor dashboard workflow completion/polish.
6. Batch 18: patient portal completion/hardening.
7. Batch 19: WhatsApp limited integration design/implementation only after
   privacy gates.
8. Batch 20: approved cases/reviews/media showcase plus private publication
   rules.
9. Batch 21: release candidate hardening.

## Final Quality Goals

Future batches must move toward:

- a professional visual experience approved through Figma/design governance;
- smooth patient booking;
- a comfortable doctor/admin workflow;
- high-quality Arabic and English copy;
- mobile-first behavior;
- privacy and security by default;
- no real launch without staging, legal/privacy, backup/restore, monitoring,
  load, and security evidence.

## Stop Rules

Stop and report instead of continuing if:

- any code change seems needed during a documentation-only batch;
- visual changes are requested without Figma/design approval;
- implementation tries to skip staging, legal, or privacy gates;
- real patient data is requested or provided;
- patient media is requested for publication without explicit publication
  consent;
- WhatsApp, uploads, medical records, payments, deployment, secrets, external
  infrastructure, or dependency changes appear necessary in the same batch.
- Codex is asked to create Figma work, visual design, mockups, colors, spacing,
  typography, animations, shadows, borders, hover effects, or layout density
  without a human/owner-approved design handoff.
