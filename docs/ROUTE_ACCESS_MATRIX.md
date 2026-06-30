# Route Access Matrix

Batch 10 route/access inventory for Dr. Khaled Badran Clinic after Batch 9.

This matrix documents current route behavior. It does not authorize new feature
routes. Figma remains the source of truth for visual design; this document is
security and operational documentation only.

## Route Policy Summary

- Public booking must remain available without login.
- Public appointment success must remain UUID-token based.
- Numeric public appointment success URLs must remain absent.
- Staff appointment numeric IDs are allowed only behind staff-only routes.
- Patient portal appointment details must use UUID `public_token` plus
  authenticated ownership filtering.
- Portal pages must remain no-cache.
- CSRF protection must remain enabled for state-changing POSTs.
- Upload, medical-record, WhatsApp API/webhook, payment, diagnosis, triage,
  treatment automation, and medical AI routes must remain absent.

## Data Exposure Levels

| Level | Meaning |
| --- | --- |
| Public informational | Public clinic, doctor, service, legal, or site metadata. |
| Public booking | Patient-submitted booking form fields and patient-safe confirmation details. |
| Patient-limited | Authenticated patient account or linked appointment details filtered to the logged-in owner. |
| Staff operational | Staff-only appointment operations, audit/status history, operational notes, and internal IDs. |
| Safe operational health | Liveness/readiness status without internals or credentials. |
| Absent/prohibited | Route intentionally not implemented and expected to return 404. |

## Public Arabic/Default Routes

| Route | Method | Auth | Staff | Ownership filtering | CSRF expectation | Cache expectation | Data exposure | Implementation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational | `apps/core/views.py:home` |
| `/doctor/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational | `apps/core/views.py:doctor_profile` |
| `/services/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational | `apps/core/views.py:services` |
| `/contact/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational | `apps/core/views.py:contact` |
| `/privacy/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational legal draft | `apps/core/views.py:privacy` |
| `/terms/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational legal draft | `apps/core/views.py:terms` |
| `/medical-disclaimer/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational legal draft | `apps/core/views.py:medical_disclaimer` |
| `/whatsapp-policy/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational legal draft; no API | `apps/core/views.py:whatsapp_policy` |
| `/robots.txt` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public SEO metadata | `apps/core/views.py:robots_txt` |
| `/sitemap.xml` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public SEO metadata | `apps/core/views.py:sitemap_xml` |

## Public English Routes

| Route | Method | Auth | Staff | Ownership filtering | CSRF expectation | Cache expectation | Data exposure | Implementation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/en/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational | `apps/core/views.py:home` |
| `/en/doctor/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational | `apps/core/views.py:doctor_profile` |
| `/en/services/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational | `apps/core/views.py:services` |
| `/en/contact/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational | `apps/core/views.py:contact` |
| `/en/privacy/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational legal draft | `apps/core/views.py:privacy` |
| `/en/terms/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational legal draft | `apps/core/views.py:terms` |
| `/en/medical-disclaimer/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational legal draft | `apps/core/views.py:medical_disclaimer` |
| `/en/whatsapp-policy/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public informational legal draft; no API | `apps/core/views.py:whatsapp_policy` |

## Booking Routes

| Route | Method | Auth | Staff | Ownership filtering | CSRF expectation | Cache expectation | Data exposure | Implementation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/book/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public booking entry | `apps/booking/views.py:book_start` |
| `/book/visit-type/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public visit types | `apps/booking/views.py:select_visit_type` |
| `/book/slots/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public available slot metadata | `apps/booking/views.py:select_slot` |
| `/book/confirm/` | GET, POST | None | No | Not applicable | POST protected by Django CSRF middleware and template token | `never_cache` | Public booking form; creates patient/appointment only on valid POST | `apps/booking/views.py:confirm_booking` |
| `/en/book/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public booking entry | `apps/booking/views.py:book_start` |
| `/en/book/visit-type/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public visit types | `apps/booking/views.py:select_visit_type` |
| `/en/book/slots/` | GET intended | None | No | Not applicable | No state-changing form | Public cache policy not finalized | Public available slot metadata | `apps/booking/views.py:select_slot` |
| `/en/book/confirm/` | GET, POST | None | No | Not applicable | POST protected by Django CSRF middleware and template token | `never_cache` | Public booking form; creates patient/appointment only on valid POST | `apps/booking/views.py:confirm_booking` |

## Booking Success Routes

| Route | Method | Auth | Staff | Ownership filtering | CSRF expectation | Cache expectation | Data exposure | Implementation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/book/success/<uuid:public_token>/` | GET intended | None | No | Lookup by non-enumerable UUID `public_token` | No state-changing form | `never_cache` | Patient-safe confirmation details only | `apps/booking/views.py:booking_success` |
| `/en/book/success/<uuid:public_token>/` | GET intended | None | No | Lookup by non-enumerable UUID `public_token` | No state-changing form | `never_cache` | Patient-safe confirmation details only | `apps/booking/views.py:booking_success` |
| `/book/success/<numeric-id>/` | Not routed | None | No | Not applicable | Not applicable | 404 | Absent/prohibited numeric public success | `config/urls.py` has no numeric pattern |
| `/en/book/success/<numeric-id>/` | Not routed | None | No | Not applicable | Not applicable | 404 | Absent/prohibited numeric public success | `config/urls.py` has no numeric pattern |

Current UUID-only behavior:

- The only public success URL pattern uses `<uuid:public_token>`.
- Invalid UUID strings return 404 at URL resolution.
- Valid UUIDs that do not match an appointment return 404 through
  `get_object_or_404`.
- Public success templates show a short confirmation reference derived from the
  UUID, not the database ID.

## Staff Appointment Operation Routes

| Route | Method | Auth | Staff | Ownership filtering | CSRF expectation | Cache expectation | Data exposure | Implementation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/staff/appointments/` | GET intended | Required | Required | Staff-only queryset | No state-changing form | `never_cache` | Staff operational | `apps/booking/views.py:staff_appointment_list` |
| `/staff/appointments/<appointment-id>/` | GET intended | Required | Required | Staff-only queryset | No state-changing form | `never_cache` | Staff operational | `apps/booking/views.py:staff_appointment_detail` |
| `/staff/appointments/<appointment-id>/cancel/` | POST only after staff auth | Required | Required | Staff-only appointment lookup | POST protected by Django CSRF middleware | `never_cache` | Staff operational status change | `apps/booking/views.py:staff_appointment_cancel` |
| `/staff/appointments/<appointment-id>/reschedule/` | POST only after staff auth | Required | Required | Staff-only appointment lookup | POST protected by Django CSRF middleware | `never_cache` | Staff operational status/time change | `apps/booking/views.py:staff_appointment_reschedule` |
| `/staff/appointments/<appointment-id>/arrived/` | POST only after staff auth | Required | Required | Staff-only appointment lookup | POST protected by Django CSRF middleware | `never_cache` | Staff operational status change | `apps/booking/views.py:staff_appointment_arrived` |
| `/staff/appointments/<appointment-id>/complete/` | POST only after staff auth | Required | Required | Staff-only appointment lookup | POST protected by Django CSRF middleware | `never_cache` | Staff operational status change | `apps/booking/views.py:staff_appointment_complete` |
| `/staff/appointments/<appointment-id>/no-show/` | POST only after staff auth | Required | Required | Staff-only appointment lookup | POST protected by Django CSRF middleware | `never_cache` | Staff operational status change | `apps/booking/views.py:staff_appointment_no_show` |

Staff route behavior:

- Anonymous users are redirected to Django admin login.
- Authenticated non-staff users receive `403`.
- Staff operations reject non-POST requests with `405` after staff
  authorization.
- Staff numeric appointment IDs are not linked from patient portal pages.

## Patient Portal Arabic/Default Routes

| Route | Method | Auth | Staff | Ownership filtering | CSRF expectation | Cache expectation | Data exposure | Implementation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/portal/` | GET intended | Required | No | Appointments filtered to `patient__user=request.user` | No state-changing form | `never_cache` | Patient-limited dashboard | `apps/patients/views.py:portal_dashboard` |
| `/portal/login/` | GET, POST | Anonymous or redirect if already authenticated | No | Not applicable | POST protected by Django CSRF middleware and template token | `never_cache` | Account login form | `apps/patients/views.py:portal_login` |
| `/portal/logout/` | POST only | Auth optional at view level | No | Current session only | POST protected by Django CSRF middleware and template token | `never_cache` | Session termination only | `apps/patients/views.py:portal_logout` |
| `/portal/register/` | GET, POST | Anonymous or redirect if already authenticated | No | Not applicable | POST protected by Django CSRF middleware and template token | `never_cache` | Account registration form | `apps/patients/views.py:portal_register` |
| `/portal/account/` | GET intended | Required | No | Current authenticated user | No state-changing form | `never_cache` | Patient-limited account summary | `apps/patients/views.py:portal_account` |
| `/portal/password/change/` | GET, POST | Required | No | Current authenticated user | POST protected by Django CSRF middleware and template token | `never_cache` | Password change form; sensitive parameters hidden | `apps/patients/views.py:portal_password_change` |
| `/portal/account-recovery/` | GET only | None | No | Not applicable | POST rejected by `require_GET` | `never_cache` | Static recovery policy only | `apps/patients/views.py:portal_account_recovery` |
| `/portal/link-appointment/` | GET, POST | Required | No | Link requires UUID token plus matching booking phone | POST protected by Django CSRF middleware and template token | `never_cache` | Appointment linking form | `apps/patients/views.py:portal_link_appointment` |
| `/portal/appointments/` | GET intended | Required | No | Appointments filtered to `patient__user=request.user` | No state-changing form | `never_cache` | Patient-limited appointment list | `apps/patients/views.py:portal_appointment_list` |
| `/portal/appointments/<uuid:public_token>/` | GET intended | Required | No | `public_token` and `patient__user=request.user` | No state-changing form | `never_cache` | Patient-limited appointment detail | `apps/patients/views.py:portal_appointment_detail` |
| `/portal/appointments/<numeric-id>/` | Not routed | Required if any portal route existed | No | Not applicable | Not applicable | 404 | Absent/prohibited numeric patient appointment detail | `config/urls.py` has no numeric pattern |

## Patient Portal English Routes

| Route | Method | Auth | Staff | Ownership filtering | CSRF expectation | Cache expectation | Data exposure | Implementation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/en/portal/` | GET intended | Required | No | Appointments filtered to `patient__user=request.user` | No state-changing form | `never_cache` | Patient-limited dashboard | `apps/patients/views.py:portal_dashboard` |
| `/en/portal/login/` | GET, POST | Anonymous or redirect if already authenticated | No | Not applicable | POST protected by Django CSRF middleware and template token | `never_cache` | Account login form | `apps/patients/views.py:portal_login` |
| `/en/portal/logout/` | POST only | Auth optional at view level | No | Current session only | POST protected by Django CSRF middleware and template token | `never_cache` | Session termination only | `apps/patients/views.py:portal_logout` |
| `/en/portal/register/` | GET, POST | Anonymous or redirect if already authenticated | No | Not applicable | POST protected by Django CSRF middleware and template token | `never_cache` | Account registration form | `apps/patients/views.py:portal_register` |
| `/en/portal/account/` | GET intended | Required | No | Current authenticated user | No state-changing form | `never_cache` | Patient-limited account summary | `apps/patients/views.py:portal_account` |
| `/en/portal/password/change/` | GET, POST | Required | No | Current authenticated user | POST protected by Django CSRF middleware and template token | `never_cache` | Password change form; sensitive parameters hidden | `apps/patients/views.py:portal_password_change` |
| `/en/portal/account-recovery/` | GET only | None | No | Not applicable | POST rejected by `require_GET` | `never_cache` | Static recovery policy only | `apps/patients/views.py:portal_account_recovery` |
| `/en/portal/link-appointment/` | GET, POST | Required | No | Link requires UUID token plus matching booking phone | POST protected by Django CSRF middleware and template token | `never_cache` | Appointment linking form | `apps/patients/views.py:portal_link_appointment` |
| `/en/portal/appointments/` | GET intended | Required | No | Appointments filtered to `patient__user=request.user` | No state-changing form | `never_cache` | Patient-limited appointment list | `apps/patients/views.py:portal_appointment_list` |
| `/en/portal/appointments/<uuid:public_token>/` | GET intended | Required | No | `public_token` and `patient__user=request.user` | No state-changing form | `never_cache` | Patient-limited appointment detail | `apps/patients/views.py:portal_appointment_detail` |
| `/en/portal/appointments/<numeric-id>/` | Not routed | Required if any portal route existed | No | Not applicable | Not applicable | 404 | Absent/prohibited numeric patient appointment detail | `config/urls.py` has no numeric pattern |

## Account-Security Routes

Account-security routes are also included in the portal tables above. Their
security expectations are repeated here because they are launch-sensitive:

| Route | Method | Auth | CSRF expectation | Cache expectation | Security notes |
| --- | --- | --- | --- | --- | --- |
| `/portal/login/`, `/en/portal/login/` | GET, POST | Anonymous or redirect if authenticated | POST protected | `never_cache` | Generic login error; rate limited by hashed IP/phone identities. |
| `/portal/register/`, `/en/portal/register/` | GET, POST | Anonymous or redirect if authenticated | POST protected | `never_cache` | Uses Django password validation/hashing; rate limited by hashed IP/phone identities. |
| `/portal/logout/`, `/en/portal/logout/` | POST only | Current session | POST protected | `never_cache` | GET returns 405; no logout link should use GET. |
| `/portal/password/change/`, `/en/portal/password/change/` | GET, POST | Required | POST protected | `never_cache` | Uses `PasswordChangeForm`, Django hashing, and session hash refresh. |
| `/portal/account-recovery/`, `/en/portal/account-recovery/` | GET only | None | POST rejected | `never_cache` | Static informational policy; does not collect phone/email or disclose account existence. |

## Health and Readiness Routes

| Route | Method | Auth | Staff | Ownership filtering | CSRF expectation | Cache expectation | Data exposure | Implementation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/health/` | GET only | None | No | Not applicable | Unsafe methods rejected by `require_GET` | `never_cache` | Safe operational health | `apps/core/views.py:health_check` |
| `/health/ready/` | GET only | None at Django route level; intended private/internal | No | Not applicable | Unsafe methods rejected by `require_GET` | `never_cache` | Safe readiness status only | `apps/core/views.py:readiness_check` |

Readiness behavior:

- Checks database connectivity.
- Returns only `{"status": "ok"}` or `{"status": "unavailable"}`.
- Does not expose database engine, exception text, credentials, hostnames,
  settings, or stack traces.

## Framework/Admin Route

| Route | Method | Auth | Staff | Ownership filtering | CSRF expectation | Cache expectation | Data exposure | Implementation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/admin/` | Django admin methods | Required | Staff/admin permissions through Django admin | Django admin permissions | Django admin CSRF protections | Django admin defaults | Admin/staff data according to model admin permissions | `django.contrib.admin.site.urls` |

The public route matrix does not treat Django admin as a patient-facing feature.
Admin/staff account provisioning and least-privilege review remain pre-launch
requirements.

## Absent and Prohibited Routes

These routes must stay absent unless a future approved batch explicitly designs,
implements, and tests them with privacy/security review:

| Route | Method | Auth | Staff | Ownership filtering | CSRF expectation | Cache expectation | Data exposure | Current implementation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/uploads/` | Not routed | Not applicable | Not applicable | Not applicable | Not applicable | 404 | Absent/prohibited uploads | No URL pattern |
| `/portal/uploads/` | Not routed | Not applicable | Not applicable | Not applicable | Not applicable | 404 | Absent/prohibited uploads | No URL pattern |
| `/whatsapp/webhook/` | Not routed | Not applicable | Not applicable | Not applicable | Not applicable | 404 | Absent/prohibited WhatsApp webhook | No URL pattern |
| `/api/whatsapp/` | Not routed | Not applicable | Not applicable | Not applicable | Not applicable | 404 | Absent/prohibited WhatsApp API | No URL pattern |
| `/whatsapp/api/` | Not routed | Not applicable | Not applicable | Not applicable | Not applicable | 404 | Absent/prohibited WhatsApp API | No URL pattern |
| `/records/` | Not routed | Not applicable | Not applicable | Not applicable | Not applicable | 404 | Absent/prohibited records | No URL pattern |
| `/medical-records/` | Not routed | Not applicable | Not applicable | Not applicable | Not applicable | 404 | Absent/prohibited medical records | No URL pattern |
| `/portal/medical-records/` | Not routed | Not applicable | Not applicable | Not applicable | Not applicable | 404 | Absent/prohibited medical records | No URL pattern |
| `/payments/` | Not routed | Not applicable | Not applicable | Not applicable | Not applicable | 404 | Absent/prohibited payments | No URL pattern |
| `/portal/payments/` | Not routed | Not applicable | Not applicable | Not applicable | Not applicable | 404 | Absent/prohibited payments | No URL pattern |

## Route Parity Notes

- Public site routes have Arabic/default and English equivalents.
- Booking routes have Arabic/default and English equivalents.
- Booking success routes are UUID-token based in both languages.
- Portal routes have Arabic/default and English equivalents.
- Staff appointment routes currently exist once, outside the public language
  prefixes, and use English operational copy.
- Prohibited upload, medical-record, WhatsApp API/webhook, and payment routes
  are absent in both public and portal namespaces.
