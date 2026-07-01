# Next Batch: Final Product Completion Track

This document replaces the stale foundation-stage next-batch note. The project
is past the initial foundation stage. After Batch 11, the current track is final
product completion and professional delivery readiness.

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

## Batch 13 Recommendation

Recommended next batch:

```text
Batch 13: Figma/UX final handoff or final design specification alignment
```

Goal:

- produce or align the final approved Figma/UX specification for the completed
  clinic product;
- preserve existing security, privacy, route, CSRF, no-cache, and ownership
  boundaries;
- avoid code changes unless a later implementation batch explicitly approves
  them.

Must read before Batch 13:

- `README.md`
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

## Ordered Recommended Batches

1. Batch 13: Figma/UX final handoff or final design specification alignment.
2. Batch 14: restricted staging validation with PostgreSQL/Redis/HTTPS/proxy.
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
