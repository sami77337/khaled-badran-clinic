# Guest consultations and WhatsApp website links

Guest entry is `/consult/` (Arabic, RTL) or `/en/consult/` (English, LTR).
Registered patients continue to use `/portal/consultations/new/` and its English
equivalent, including the existing protected login return and ownership checks.

## Data and access

Migration `patients.0007_transient_consultations` creates only four tables:
`TransientConsultation`, `TransientConsultationAttachment`,
`TransientConsultationAudioReply`, and `TransientConsultationChallenge`.
`Consultation.patient` remains required. Guest submission never looks up,
creates, attaches, or merges a Patient or user account.

The challenge stores a password-hashed six-digit OTP and an HMAC of a random
browser secret held in the Django session. Correct verification consumes the
OTP, rotates the session key, and activates an expiring database grant. Under a
row lock, submission assigns that entry grant to exactly one consultation.
The same browser can then read that consultation, its reply, and private files.
An entry grant cannot read earlier consultations, even for the same phone.

A UUID link only identifies a consultation. Without its valid browser grant,
the visitor sees a verification screen with only the destination's last three
digits. The verification destination always comes from the consultation's
stored phone; request parameters cannot substitute a different number. Later
verification grants access to that consultation only. Logout/session loss or
grant expiry requires verification again.

Default limits (override in Django settings when necessary):

| Control | Default |
| --- | --- |
| OTP lifetime | 10 minutes |
| OTP attempts per challenge | 5 |
| Send cooldown per normalized phone | 60 seconds |
| Sends per hour, IP / phone | 10 / 5 |
| Verification attempts per hour, IP / phone | 30 / 20 |
| Submission attempts per hour, IP / phone | 10 / 5 |
| Verified grant lifetime | 24 hours |

The setting names begin `GUEST_CONSULTATION_`; see `config/settings/base.py`.
Limits reuse the project's cache counter and trusted client-IP policy. Cache
failure denies the attempt. Use the project's shared cache configuration for
multi-process deployments. Expired grants remain unusable even if their rows
have not been removed.

All guest mutations require CSRF. Guest pages and files return private/no-store
headers, no-referrer, and noindex headers. Templates escape question/reply text.

## Private attachments and staff replies

Both consultation types use the same upload policy methods and private storage:
up to five files, images/PDF up to 10 MiB each, and MP4 up to 50 MiB. Existing
extension, MIME/category, nonempty-file and size validation is retained. These
are the existing byte/type policies, without adding a new media inspection
dependency or changing their duration-validation guarantees.

Storage names are randomized; storage refuses public URLs. The guest attachment
and audio routes check the database grant before opening a file. Staff use
separate staff-authorized routes. Response filenames are opaque safe names.

The existing staff consultation list includes both types with explicit labels.
Guest details reuse the existing reply form, recorder and transaction/storage
handling. Text, private voice replies, replacement/removal and closing are
supported. Guest details have no patient-record relationship. Voice uploads keep
the existing WebM/Ogg/MP4 policy, 15 MiB server limit and five-minute recorder
limit. New/replaced audio cleanup retains the existing transaction behavior.

## Provider-agnostic interfaces

No provider adapter, credentials, provider-specific menu payload, webhook, or
package is selected or installed by this feature.

`apps.whatsapp.actions.entry_actions(language)` returns immutable website action
definitions with `key`, `label`, `url`, and optional `group`. These include
booking, both consultation paths, existing appointments, appointment link and
recovery, clinic location, doctor, and services. A future adapter can map these
to buttons or lists.

Optional environment settings:

```text
GUEST_CONSULTATION_OTP_SENDER=your_package.send_guest_otp
WHATSAPP_CONSULTATION_NOTIFICATION_SENDER=your_package.send_consultation_notice
WHATSAPP_WEBSITE_ORIGIN=https://your-clinic-website.example
WHATSAPP_DEFAULT_LANGUAGE=ar
```

These are dotted Python callable paths; settings overrides may also supply
callables directly. Neither sender is configured by default.

```python
send_guest_otp(phone_e164, code, language)
send_consultation_notice(phone_e164, neutral_message, secure_url, language)
```

`False` or an exception means delivery failure. OTP delivery failure does not
verify the phone. Reply delivery is scheduled with `transaction.on_commit` for
both registered and guest replies. It receives only a destination phone, fixed
neutral text, a protected HTTPS website link, and language. No model instance,
question, reply text, filename, file or recording reaches the sender.

Guest notifications use the submission language. Registered notifications use
`WHATSAPP_DEFAULT_LANGUAGE`, because the existing patient schema has no stored
notification-language preference. Links use the configured HTTPS origin,
never an incoming Host header. Missing/invalid configuration and sender failures
are safely logged without exceptions, phone numbers, tokens or medical content;
they do not roll back the saved reply. Unchanged replies and status-only changes
do not send duplicate alerts. A changed visible text/voice reply schedules a new
neutral alert. Delivery retries/outbox processing are not introduced here.

## Local verification

The guest security suite covers cross-guest denial, forwarded links, OTP expiry,
wrong and replayed OTPs, per-phone/IP limits, expired grants, CSRF, private media,
staff-only routes, patient regression, upload cleanup, and PostgreSQL lock SQL.
Notification tests include real commit boundaries and provider exceptions.

The browser test renders 38 real AR/EN page states at widths 320, 360, 390, 412,
640, 768, 1024, 1280 and 1440, at two heights (684 layout cases). It includes
phone and OTP errors, expiry, throttling, forms, attachment validation, success,
awaiting/answered/closed/empty replies, voice, long text/filenames, re-verification,
and unavailable providers. Optional `KBC_GUEST_QA_DIR` retains representative
screenshots outside the repository.

All tracked tests live under `apps`. Use `python -B manage.py test apps --verbosity 1`
when unrelated workspace directories must be excluded from test discovery.

Verified locally on 2026-09-09, starting at
`c18c6d67a2092b7aa8e4e8937c2a76052dc91625`:

- `python -B manage.py check`: no issues.
- `python -B manage.py makemigrations --check --dry-run`: no changes detected.
- Final focused consultation/security/notification/navigation/browser run:
  82 tests passed, including 684 guest/staff layout cases and the recorder's
  11 lifecycle cases.
- `python -B manage.py test apps --verbosity 1`: all 828 tests passed, no skips,
  in 324.335 seconds. Discovery was explicitly scoped to `apps` to respect the
  owner's excluded workspace directory.
- Existing browser suites also passed: review administration, public/portal
  closeout layouts, phone-picker mobile/landscape checks and notification panels.
- Representative AR/EN screenshots were visually inspected; the guest pages
  suppress the floating WhatsApp shortcut so it cannot overlap form controls.
- `git diff --check` and staged diff whitespace checks passed.

The migration was exercised in isolated test databases. No existing local
patient database was migrated or populated for this work. All test records and
uploads were synthetic. No WhatsApp provider was selected or installed.
