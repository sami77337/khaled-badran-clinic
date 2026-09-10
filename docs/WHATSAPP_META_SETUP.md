# Meta WhatsApp Cloud API operations

Repository-local test results and compatibility fixes are recorded in
[the validation note](WHATSAPP_META_VALIDATION.md).

This adapter implements issue #45. It reuses the existing public booking,
registered consultation, guest consultation and patient-account routes. No
dependency or database migration is required. It does not create Meta templates,
register a phone number, subscribe an app, or make test calls to Meta automatically.

## Operator configuration

Create/configure the clinic's Meta business portfolio, WABA, app and registered
business phone number. Assign the required messaging permissions to an operator
managed system-user access token. Subscribe the app to the WABA's `messages`
webhook field. Keep tokens, app secret, verification token and account identifiers
in the deployment secret store, never Git, tickets, screenshots or log output.

| Setting | Purpose |
| --- | --- |
| `WHATSAPP_META_ENABLED` | Explicit opt-in, default `false` |
| `WHATSAPP_META_ACCESS_TOKEN` | Bearer token for sending |
| `WHATSAPP_META_PHONE_NUMBER_ID` | Registered business sender ID, not its phone number |
| `WHATSAPP_META_WABA_ID` | Expected inbound business account |
| `WHATSAPP_META_APP_SECRET` | HMAC signature verification secret |
| `WHATSAPP_META_VERIFY_TOKEN` | Random operator-defined webhook verification token |
| `WHATSAPP_META_GRAPH_VERSION` | Supported Graph version selected by the operator; no version default |
| `WHATSAPP_WEBSITE_ORIGIN` | Exact clinic HTTPS origin without a path, query or credentials |
| `WHATSAPP_META_OTP_TEMPLATE` | Approved authentication template name |
| `WHATSAPP_META_CONSULTATION_REPLY_TEMPLATE` | Approved reply-notification template name |
| `WHATSAPP_META_BOOKING_CONFIRMATION_TEMPLATE` | Approved confirmation template name |
| `WHATSAPP_META_APPOINTMENT_REMINDER_TEMPLATE` | Approved reminder template name |
| `WHATSAPP_META_LOCATION_TEMPLATE` | Arabic location template preserving the exact approved button label |
| `WHATSAPP_META_TEMPLATE_LANGUAGE_AR` / `_EN` | Approved locale codes, default `ar` / `en_US` |
| `WHATSAPP_DEFAULT_LANGUAGE` | Default menu and appointment-reminder language, default `ar` |
| `WHATSAPP_HANDOFF_TTL_SECONDS` | Bot suppression, default 24 hours, bounded to 60 seconds–7 days |

Keep the existing sender contracts configured as follows:

```text
GUEST_CONSULTATION_OTP_SENDER=apps.whatsapp.meta.send_guest_otp
WHATSAPP_CONSULTATION_NOTIFICATION_SENDER=apps.whatsapp.meta.send_consultation_notification
```

When enabled, `manage.py check` reports `whatsapp.E001` for missing/invalid
configuration or sender paths. Diagnostics contain setting names, never values.
Production additionally requires PostgreSQL and a supported Django shared cache:
`RedisCache`, `PyMemcacheCache`, or `PyLibMCCache`. The environment's `CACHE_URL`
configuration uses Django's built-in `RedisCache`. Cache options that suppress
errors are rejected. The website origin rejects credentials, paths, malformed
ports, whitespace and control characters; the default language must be `ar` or `en`.
All web workers and scheduler
jobs must share the same database, cache/key prefix, Django secret and Meta settings.
Development and CI work without Meta access; sends return `False` when disabled
or unavailable, OTP challenges remain unverified, and saved replies/bookings remain intact.

## Templates to create and approve in Meta

Use the same configured template name with Arabic and English translations,
except the location template, which needs Arabic only. The adapter selects the
configured locale. No actual template names, IDs or credentials are prescribed here.
Submit utility categories to Meta review; approval/category assignment is external.
Template body and button copy are stored in Meta and must match this specification.

1. **Guest OTP — AUTHENTICATION.** Use the standardized verification-code body
   and the OTP **COPY_CODE** button. Set `add_security_recommendation=false` so
   the optional recommendation sentence is absent. Set the expiration footer to
   10 minutes, matching the existing OTP lifetime. Body parameter 1 is the six-digit
   code; the button at index 0 receives the same code as a `url` button parameter,
   following Meta's authentication send schema. Do not use a URL-login or free-text
   OTP message. Button copy: `نسخ الرمز` / `Copy Code`.

2. **Consultation reply — UTILITY.** No body variables or attachments.
   Arabic: `تم إضافة رد جديد من عيادة الدكتور خالد بدران على استشارتك.`
   English: `Dr. Khaled Badran Clinic has added a new reply to your consultation.`
   URL button at index 0: `عرض الرد` / `View Reply`.
   Configure the URL as the exact website origin followed by `/{{1}}`.
   The parameter is the existing localized consultation-detail path without its
   leading slash. This accommodates both registered and guest UUID routes; all
   website ownership, login and guest OTP/grant checks remain required.

3. **Booking confirmation — UTILITY.**
   Arabic: `تم تأكيد موعدك في عيادة الدكتور خالد بدران بتاريخ {{1}} الساعة {{2}}.`
   English: `Your appointment at Dr. Khaled Badran Clinic is confirmed for {{1}} at {{2}}.`
   Body variables are clinic-local date (`YYYY-MM-DD`) and time (`HH:MM`) only.
   No patient name, consultation/service text, booking notes, references or links.

4. **Appointment reminder — UTILITY.**
   Arabic: `تذكير بموعدك في عيادة الدكتور خالد بدران بتاريخ {{1}} الساعة {{2}}.`
   English: `Reminder: your appointment at Dr. Khaled Badran Clinic is on {{1}} at {{2}}.`
   Same two date/time parameters as confirmation, without attachments or links.

5. **Arabic location — requested location information.**
   Body: `موقع عيادة الدكتور خالد بدران.`
   URL button at index 0: `افتح الموقع على الخريطة`.
   URL pattern: exact website origin followed by `/{{1}}`; runtime parameter is
   the existing Arabic contact/location route. That page contains the approved map.
   This additional template preserves the 23-character approved label using a
   template URL button's 25-character allowance. Interactive URL button labels
   are limited to 20 characters. English uses the interactive `Open Map` CTA.

Patient-facing custom copy must not contain `آمن`, `آمنة`, `الأمان`, `secure`,
`security`, or `secure link`. Keep the actual authentication and privacy controls.
Review the rendered Meta template translations before enabling production sends.

## Webhook and menu

Register the HTTPS callback path `/integrations/whatsapp/webhook/`.
GET accepts `hub.mode=subscribe`, uses a constant-time token comparison, and
returns only the supplied challenge on success. Invalid verification returns 403.
POST requires `X-Hub-Signature-256`, HMAC-SHA256 over the exact raw request bytes
using the app secret, compared with `hmac.compare_digest`. Signatures are checked
before parsing. Only the configured WABA and phone-number ID are accepted.
Only this integration route is CSRF-exempt; other routes retain CSRF protection.
All callback responses carry private/no-store cache headers. Invalid timestamp
types and oversized numeric timestamps return 400 without processing message text.

Ordinary inbound text opens the Arabic-first five-row Interactive List:
`kbc_book`, `kbc_consult`, `kbc_portal`, `kbc_location`, `kbc_staff`.
The consultation submenu has `kbc_consult_registered` and `kbc_consult_guest`.
Routing uses these IDs, never visible labels, and destinations come from
`apps.whatsapp.actions.entry_actions()`. Booking remains login-free. The account
CTA uses the existing dashboard/login redirect; consultation CTAs use the existing
registered or guest entry. URLs are button destinations, not visible body text.

`English` and `العربية` explicitly select a language; only the language code is
cached for 24 hours. Staff handoff sends the approved acknowledgement and suppresses
further bot responses for the configured TTL. A literal `menu`, `القائمة`,
`English` or `العربية` explicitly resumes automation. The adapter does not provide
a staff inbox: operators must connect the business number to their supported
staff conversation tool and verify staff can receive/reply before launch.

The callback ignores media, documents, voice, reactions and delivery statuses.
It never downloads media or copies messages into consultations/records. Patient
text is transiently parsed only for the literal menu/language commands; otherwise
it is discarded. It is never reflected to the provider or persisted. Meta itself
may receive unsolicited messages sent by a user; this integration cannot prevent
that at the WhatsApp service, but does not ingest those contents into website data.

## Delivery, retries and scheduled reminders

Webhook receipts are cached for seven days after successful handling. Keys use
keyed SHA-256 hashes; values contain only booleans, language codes or receipt hashes.
A 60-second per-conversation cache lock serializes concurrent callbacks. Busy
locks, cache errors and failed sends return 503 for retry. Accepted events return
200, including ignored media/status events. Events older than the 24-hour response
window are ignored. Callback processing is bounded per batch and resumes via retries.

The standard-library HTTPS transport uses a fixed Graph host, TLS validation,
an eight-second socket timeout, no redirect following and no immediate automatic
HTTP retry. It requires a successful response containing a message acceptance ID;
it reads at most 16 KiB and never logs response bodies, headers, tokens or numbers.
Provider acceptance is not a guarantee of delivery; delivery-status events are
acknowledged but not persisted by this adapter.

Booking confirmation is scheduled after the booking transaction commits, using
the booking page language. Failed delivery retains the booking and emits a neutral
warning. A seven-day cache receipt prevents repeated confirmation callbacks.
No background confirmation/reply outbox is introduced. A failed confirmation can
be retried by calling `apps.whatsapp.booking.send_booking_confirmation` with the
appointment identifier and language in an authorized operator session; no public
retry endpoint exists. Consultation reply notifications retain their existing
after-commit behavior and do not roll back the doctor's saved reply on failure.

Schedule this command against the production PostgreSQL database, for example
every minute using the hosting provider's scheduled-job facility:

```text
python -B manage.py send_whatsapp_reminders --limit 100
```

Preview without sending or updating records:

```text
python -B manage.py send_whatsapp_reminders --dry-run
```

Eligibility requires a future confirmed/rescheduled appointment, enabled reminders,
no `reminder_sent_at`, and `starts_at - reminder_offset <= now`. Arrived, cancelled,
completed, no-show, past, not-yet-due and previously notified appointments are skipped.
Each row is rechecked under a PostgreSQL lock held through the send and timestamp
save; `SKIP LOCKED` prevents overlapping scheduler jobs selecting the same row.
Only provider acceptance records `reminder_sent_at`. A failed send leaves it null;
the command reports aggregate counts and exits nonzero when a send/save fails.
SQLite supports dry-run and mocked service tests; actual dispatch requires row locks.
Reminders use `WHATSAPP_DEFAULT_LANGUAGE` because Appointment has no persisted
language preference. Existing sent timestamps remain authoritative on rescheduling.

No external API and local database can be committed atomically. A timeout after
Meta acceptance, process termination before saving, or a cache loss can cause a
duplicate on retry. Row locks and receipts prevent ordinary overlapping delivery,
but do not claim exactly-once transport. Investigate ambiguous failures before
manual retries; never copy provider payloads into application logs.

## Logging and launch checks

The Django console filter suppresses callback access-log records because GET
verification uses a token in the query. Configure the reverse proxy, hosting access
logs, APM and staff tooling to exclude callback query strings, request/response
bodies and Authorization/signature headers too; application settings cannot control
external logging systems. All application diagnostics use neutral messages/counts.

Run Django checks and the synthetic test suites before configuring real credentials.
The focused suite is `python manage.py test apps.whatsapp --noinput`. To exercise
real coordination, run it with PostgreSQL and an isolated Redis `CACHE_URL`:
the concurrency tests use separate database connections for overlapping reminder
workers and a separate Python process for webhook locks and completed receipts.
Those two tests skip under the default SQLite/LocMem configuration. The suite clears
its Redis database, so never point test settings at a shared operational cache.

CI uses mocked HTTP only; its invented Graph version and reserved fictional phone
fixtures are not operator examples. With operator-provided credentials, approved
templates, staff tooling and scheduler configured, perform a controlled authorized
end-to-end acceptance check outside CI. Confirm Arabic/English template rendering,
verification, patient/guest routing, saved-reply retention, reminder eligibility and
staff handoff. Do not store real recipient data or screenshots in Git.

References: [Meta Cloud API collection](https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api),
[Meta authentication template example](https://www.postman.com/meta/whatsapp-business-platform/request/6vkv46u/create-authentication-template-w-otp-copy-code-button),
[Meta webhook verification reference](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/webhooks/start/),
[Meta interactive CTA reference](https://developers.facebook.com/docs/whatsapp/cloud-api/messages/interactive-cta-url-messages/).
