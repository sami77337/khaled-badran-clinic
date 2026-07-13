# Clinic Delivery v1 Scope Lock

## Status

- commercial delivery scope: locked for implementation planning
- production-ready: no
- this document is not legal, medical, or production approval

## Official Project Identity

- Arabic name: عيادة الدكتور خالد بدران
- English name: Dr. Khaled Badran Clinic
- Doctor in scope: Dr. Khaled Badran only
- Bilingual Arabic/English
- Arabic default

## Commercial Delivery v1 Scope

Commercial Delivery v1 includes the following product scope for implementation
planning:

- public clinic website
- final Figma design implementation
- responsive desktop/tablet/mobile UI
- bilingual Arabic/English pages
- public home page
- doctor/profile/service content pages where applicable
- appointment booking from website
- booking without required login
- automatic booking confirmation
- success/error states for booking
- default appointment reminder policy: 3 hours before appointment,
  dashboard-adjustable later
- WhatsApp quick link
- structured WhatsApp message/menu concept:
  - حجز موعد جديد
  - معرفة أكثر
  - موقع العيادة
  - مراجعة موعد سابق
  - سؤال الطبيب
- doctor/staff dashboard
- simple patient medical record
- patient portal
- private image uploads
- short private video uploads
- doctor-controlled patient visibility
- patient read-only access to approved record parts
- cases/achievements section for approved public media only
- consent requirement for public case media

This scope is commercial handoff planning scope. It does not close production
launch blockers, authorize live patient use, or approve external operations.

## Patient Medical Record v1

Patient medical record v1 is a practical clinic record for Dr. Khaled Badran
Clinic. It is not a full hospital EMR.

Patient medical record v1 must include:

- patient basic details
- phone
- age or date of birth if available
- gender if available
- appointments
- visits
- visit reason
- doctor notes
- diagnosis/plan only when written manually by doctor
- instructions/follow-up notes only when written manually by doctor
- images
- short videos
- media linked to patient or visit
- media visibility status:
  - private only
  - visible to patient
  - approved for public case display only with consent

The record must not create automated diagnosis, treatment, triage, or medical
recommendations. Doctor-written clinical content remains the responsibility of
the doctor.

## Patient Portal Visibility Model

The patient portal visibility model for v1 is:

- private by default
- patient cannot automatically see all medical notes/media
- doctor/staff must explicitly approve what is visible to patient
- patient portal is read-only for medical record content in v1
- patient may view approved appointments, summaries, notes, images, and short
  videos
- patient must not see private staff-only/doctor-only notes
- patient must not see media not approved for them

Any implementation must preserve staff-only and doctor-only boundaries even
when patient portal accounts already exist.

## Media Rules

Implementation expectations for images and videos:

- private media is not publicly linkable by default
- no public media URLs for medical files
- images and videos must have type/size validation in implementation
- videos are short only
- no video editing in system
- no AI analysis of media
- deletion/hiding must be controlled from dashboard
- public cases use separate approval/consent state

Private medical media must be treated as protected clinic content. Public case
media must use a separate publication approval state and must not be inferred
from patient visibility alone.

## WhatsApp v1

WhatsApp v1 is limited to a website quick link.

Required boundaries:

- v1 uses WhatsApp quick link only
- no WhatsApp Business API in commercial delivery v1 unless separately approved
- no automatic medical content sent through WhatsApp
- future API reminders may be a later phase
- WhatsApp messages must avoid sensitive medical details by default

The structured message/menu concept is a product planning target for patient
entry and navigation, not approval for automated medical messaging.

## Explicitly Out Of v1

The following are out of Commercial Delivery v1 unless separately approved:

- WhatsApp Business API integration
- AI diagnosis
- AI treatment
- AI triage
- automated medical recommendations
- prescription automation
- full hospital EMR
- PACS/DICOM viewer
- public sharing of medical files
- payment system unless separately approved
- production DNS/custom domain/TLS as commercial demo requirement unless
  separately approved
- monitoring provider setup as commercial demo requirement unless separately
  approved

## Medical And Legal Boundaries

Commercial Delivery v1 must respect these boundaries:

- no diagnosis automation
- no treatment automation
- no triage automation
- no system-generated medical recommendation
- doctor remains responsible for medical content
- public case images/videos require consent
- private medical files must not be exposed through public links

This document does not provide legal advice, medical advice, privacy approval,
or launch approval.

## Delivery-Time Interpretation

When estimating remaining work for doctor handoff/payment, the baseline is:

```text
Website + Figma implementation + booking + WhatsApp quick link +
doctor/staff dashboard + patient medical record v1 + private images/videos +
patient portal with doctor-approved visibility.
```

Current planning estimate:

- commercial handoff readiness after Figma completion: approximately 78% to
  84%
- remaining: approximately 16% to 22%
- estimated work: 12 to 18 working days

This estimate is planning-only and must be updated after code inspection and a
Figma implementation audit. It must not be used as production-readiness,
legal/privacy-readiness, operations-readiness, or launch approval.

## Implementation Batch Order

Next implementation batches:

- BATCH-16-DELIVERY-01: Figma implementation audit and UI foundation plan
- BATCH-16-DELIVERY-02: public pages and booking UI implementation
- BATCH-16-DELIVERY-03: dashboard/staff patient record foundation
- BATCH-16-DELIVERY-04: private media upload foundation for patient/visit
  records
- BATCH-16-DELIVERY-05: patient portal read-only approved visibility
- BATCH-16-DELIVERY-06: approved public cases/achievements media section
- BATCH-16-DELIVERY-07: final commercial handoff QA package

Each implementation batch must preserve the safety boundaries in this document
and must not close production blockers unless a later approved production
readiness batch explicitly does so with evidence.

## Acceptance Criteria

This document is the source of truth for Commercial Delivery v1 scope unless
superseded by a later approved scope-lock document.

Acceptance criteria:

- future implementation planning references this scope before adding or
  excluding v1 product work
- patient medical record v1 remains a practical clinic record, not a hospital
  EMR
- patient portal medical content remains read-only and doctor/staff-approved
  for visibility
- private media remains non-public by default
- WhatsApp remains quick-link-only in v1 unless separately approved
- production-ready remains `no` until production blockers are closed through a
  separate approved production-readiness process
